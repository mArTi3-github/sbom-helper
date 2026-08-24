from __future__ import annotations

import json
import logging
from urllib.parse import urlparse

import httpx
from openai import APIError, AsyncOpenAI

from ..purl_utils import PurlValidationError, validate
from .interface import Resolution, Resolver

logger = logging.getLogger(__name__)

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


class LlmResolver(Resolver):

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        attempts_count: int = 2,
        timeout: float = 60.0,
    ) -> None:
        self._base_url = base_url
        self._api_key = api_key
        self._model = model
        self._attempts_count = attempts_count
        self._timeout = timeout
        self._client = AsyncOpenAI(base_url=base_url, api_key=api_key, timeout=timeout)
        self._http_client = httpx.AsyncClient(timeout=timeout, follow_redirects=True)

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
                    'Respond with the JSON object in the required format.'
                ),
            },
        ]

        for attempt in range(1, self._attempts_count + 1):
            logger.info("llm resolving %s (attempt %d/%d)", purl, attempt, self._attempts_count)
            content = await self._request(messages)
            if content is None:
                self._record_failure(warnings, messages, attempt, purl, "LLM request failed")
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
            purl, attempt, self._attempts_count, reason,
        )
        messages.append({"role": "user", "content": _RETRY_FEEDBACK.format(reason=reason)})

    async def _request(self, messages: list[dict[str, str]]) -> str | None:
        try:
            completion = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
            )
            return completion.choices[0].message.content
        except (APIError, httpx.HTTPError) as exc:
            logger.warning("LLM request failed: %s", exc)
            return None

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
                text = text[len("json"):]
            text = text.strip()
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            return json.loads(text[start:end + 1])
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
