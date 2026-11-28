from __future__ import annotations

import html.parser
import ipaddress
import json
import logging
import socket
import ssl
from urllib.parse import urljoin, urlparse

import httpx
from openai import APIError, AsyncOpenAI

from ..purl_utils import PurlValidationError, validate
from .interface import Resolution, Resolver

logger = logging.getLogger(__name__)

_SEARCH_TIMEOUT = 15.0
_FETCH_TIMEOUT = 15.0
_FETCH_MAX_BYTES = 512 * 1024
_FETCH_MAX_TEXT = 8000
_MAX_REDIRECTS = 3
_TOP_K_RESULTS = 5

SYSTEM_PROMPT = (
    "You are a component resolver for SBOM analysis. Your task is to find the source code "
    "repository for a package identified by a Package URL (PURL). Use your web-search and "
    "web-fetch tools to search the web when you do not know the repository offhand.\n"
    "Respond with a single JSON object in exactly the following format:\n"
    '{"purl": "<the PURL you were asked about>", "status": "success|failure", '
    '"repository_url": "<URL of the source code repository or null>"}\n'
    "Rules:\n"
    "- 'status' must be exactly 'success' or 'failure'.\n"
    "- On success, 'repository_url' must be a valid http(s) URL of the package's source code "
    "repository (e.g. GitHub, GitLab, Bitbucket or self-hosted).\n"
    "- If you cannot find a reliable repository, return status 'failure' and "
    "'repository_url': null.\n"
    "- Do not invent URLs. If you are not sure, use failure status.\n"
    "- Output nothing but the JSON object."
)

_RETRY_FEEDBACK = (
    "Your previous answer was rejected because: {reason}. Please try again and return a "
    "valid JSON object in the required format."
)


def _build_ssl_verify(verify_ssl: bool, ca_bundle: str | None) -> bool | ssl.SSLContext:
    if not verify_ssl:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        logger.warning("LLM resolver: TLS certificate verification is disabled")
        return context
    if ca_bundle:
        try:
            return ssl.create_default_context(cafile=ca_bundle)
        except OSError as exc:
            logger.warning(
                "LLM resolver: cannot load CA bundle %s (%s); falling back to default verification",
                ca_bundle,
                exc,
            )
    return True


class _TextExtractor(html.parser.HTMLParser):
    _SKIP = {"script", "style", "head", "title"}

    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip_depth += 1
        elif tag in {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4"}:
            self._parts.append(" ")

    def handle_endtag(self, tag):
        if tag in self._SKIP and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data):
        if self._skip_depth == 0:
            self._parts.append(data)


def _html_to_text(raw: str) -> str:
    parser = _TextExtractor()
    parser.feed(raw)
    return " ".join("".join(parser._parts).split())


def _is_forbidden_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip.split("%")[0])
    except ValueError:
        return True
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


class LlmResolver(Resolver):
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        attempts_count: int = 2,
        timeout: float = 60.0,
        verify_ssl: bool = True,
        ca_bundle: str | None = None,
        searxng_url: str = "http://searxng:8080",
        max_tool_rounds: int = 3,
    ) -> None:
        self._base_url = base_url
        self._api_key = api_key
        self._model = model
        self._attempts_count = attempts_count
        self._timeout = timeout
        self._verify = _build_ssl_verify(verify_ssl, ca_bundle)
        self._searxng_url = searxng_url.rstrip("/")
        self._max_tool_rounds = max_tool_rounds
        self._client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
            max_retries=0,
            http_client=httpx.AsyncClient(
                verify=self._verify, timeout=timeout, follow_redirects=True
            ),
        )
        self._http_client = httpx.AsyncClient(
            verify=self._verify, timeout=timeout, follow_redirects=True
        )
        self._fetch_client = httpx.AsyncClient(
            verify=True, timeout=_FETCH_TIMEOUT, follow_redirects=False
        )

    @property
    def name(self) -> str:
        return "llm"

    async def resolve(self, purl: str) -> Resolution:
        try:
            validate(purl)
        except PurlValidationError as e:
            return Resolution(purl=purl, warnings=[f"Invalid PURL: {e}"])

        warnings: list[str] = []
        messages: list[dict[str, str]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Find the source code repository for the package with PURL: {purl}\n"
                    "Respond with the JSON object in the required format."
                ),
            },
        ]

        for attempt in range(1, self._attempts_count + 1):
            logger.info("llm resolving %s (attempt %d/%d)", purl, attempt, self._attempts_count)
            content, error = await self._request(messages)
            if content is None:
                self._record_failure(
                    warnings, messages, attempt, purl, error or "LLM request failed"
                )
                continue

            repo_url, error = self._validate_response(content, purl)
            if error is not None:
                self._record_failure(warnings, messages, attempt, purl, error)
                continue

            ok, head_error = await self._check_url(repo_url)
            if not ok:
                self._record_failure(warnings, messages, attempt, purl, head_error)
                continue

            logger.info("llm resolved %s to %s", purl, repo_url)
            return Resolution(purl=purl, repository_url=repo_url)

        return Resolution(purl=purl, warnings=warnings)

    def _record_failure(
        self,
        warnings: list[str],
        messages: list[dict[str, str]],
        attempt: int,
        purl: str,
        reason: str,
    ) -> None:
        warning = f"Attempt {attempt}/{self._attempts_count} failed: {reason}"
        warnings.append(warning)
        logger.warning(
            "llm resolver failed for %s (attempt %d/%d): %s",
            purl,
            attempt,
            self._attempts_count,
            reason,
        )
        messages.append({"role": "user", "content": _RETRY_FEEDBACK.format(reason=reason)})

    async def _request(self, messages: list[dict[str, str]]) -> tuple[str | None, str | None]:
        try:
            completion = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
            )
            return completion.choices[0].message.content, None
        except (APIError, httpx.HTTPError) as exc:
            cause = exc.__cause__ or exc.__context__
            if cause is not None and cause is not exc:
                reason = (
                    f"LLM request failed ({type(exc).__name__}: {exc}; "
                    f"caused by {type(cause).__name__}: {cause})"
                )
            else:
                reason = f"LLM request failed ({type(exc).__name__}: {exc})"
            logger.warning("%s", reason)
            return None, reason

    def _validate_response(self, content: str | None, purl: str) -> tuple[str | None, str | None]:
        if not content:
            return None, "empty LLM response"
        data = self._parse_json(content)
        if not isinstance(data, dict):
            return None, "response is not a JSON object"
        if data.get("purl") != purl:
            return None, f"returned purl '{data.get('purl')}' does not match '{purl}'"
        status = data.get("status")
        if status not in ("success", "failure"):
            return None, f"invalid status '{status}'"
        if status == "failure":
            return None, "LLM reported failure for the purl"
        repo_url = data.get("repository_url")
        if not isinstance(repo_url, str) or not repo_url:
            return None, "repository_url is missing or empty"
        parsed = urlparse(repo_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return None, f"repository_url '{repo_url}' is not a valid http(s) URL"
        return repo_url, None

    @staticmethod
    def _parse_json(content: str) -> object:
        text = content.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[len("json") :]
            text = text.strip()
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None

    async def _check_url(self, url: str) -> tuple[bool, str]:
        try:
            response = await self._http_client.head(url)
        except httpx.HTTPError as exc:
            return False, f"URL check for '{url}' failed: {exc}"
        if response.status_code >= 400:
            return False, f"URL '{url}' returned HTTP {response.status_code}"
        return True, ""

    async def _web_search(self, query: str) -> str:
        if not query.strip():
            return "error: empty query"
        try:
            response = await self._fetch_client.get(
                f"{self._searxng_url}/search",
                params={"q": query, "format": "json"},
                timeout=_SEARCH_TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            return f"error: search failed ({type(exc).__name__}: {exc})"
        results = data.get("results") if isinstance(data, dict) else None
        if not results:
            return "no results"
        lines = []
        for item in results[:_TOP_K_RESULTS]:
            title = str(item.get("title") or "").strip()
            url = str(item.get("url") or "").strip()
            snippet = str(item.get("content") or "").strip()
            lines.append(f"- {title}\n  {url}\n  {snippet}")
        return "\n".join(lines)

    async def _resolves_to_forbidden(self, hostname: str) -> bool:
        try:
            infos = socket.getaddrinfo(hostname, None)
        except socket.gaierror:
            return True
        return any(_is_forbidden_ip(info[4][0]) for info in infos)

    async def _web_fetch(self, url: str) -> str:
        current = url
        for _ in range(_MAX_REDIRECTS + 1):
            parsed = urlparse(current)
            if parsed.scheme not in ("http", "https") or not parsed.hostname:
                return f"error: unsupported URL '{current}'"
            if await self._resolves_to_forbidden(parsed.hostname):
                return f"error: forbidden host '{current}'"
            try:
                async with self._fetch_client.stream("GET", current) as response:
                    if response.is_redirect and response.headers.get("location"):
                        current = urljoin(current, response.headers["location"])
                        continue
                    if response.status_code >= 400:
                        return f"error: HTTP {response.status_code} for '{current}'"
                    charset = response.charset_encoding or "utf-8"
                    body = b""
                    async for chunk in response.aiter_bytes():
                        body += chunk
                        if len(body) >= _FETCH_MAX_BYTES:
                            break
            except httpx.HTTPError as exc:
                return f"error: fetch failed ({type(exc).__name__}: {exc})"
            text = _html_to_text(body[:_FETCH_MAX_BYTES].decode(charset, errors="replace"))
            return text[:_FETCH_MAX_TEXT]
        return "error: too many redirects"
