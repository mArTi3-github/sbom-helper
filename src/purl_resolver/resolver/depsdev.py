from __future__ import annotations

import asyncio
import logging
import time
from urllib.parse import quote, urlparse

import httpx

from ..purl_utils import PurlValidationError, validate
from .interface import Resolution, Resolver
from .retry import RetryConfig, RetryHelper

logger = logging.getLogger(__name__)

_API_BASE = "https://api.deps.dev/v3"

_DEFAULT_MAX_REQUESTS_PER_SECOND = 1.0

_SYSTEMS: dict[str, str] = {
    "maven": "MAVEN",
    "npm": "NPM",
    "golang": "GO",
    "pypi": "PYPI",
    "nuget": "NUGET",
    "cargo": "CARGO",
    "gem": "RUBYGEMS",
}


def build_package_name(purl_type: str, namespace: str | None, name: str) -> str:
    if purl_type == "maven":
        return f"{namespace}:{name}" if namespace else name
    if namespace:
        return f"{namespace}/{name}"
    return name


def normalize_repository_url(url: str) -> str | None:
    u = url.strip()
    lowered = u.lower()
    for prefix in ("scm:git:", "scm:svn:", "scm:hg:", "scm:"):
        if lowered.startswith(prefix):
            u = u[len(prefix):]
            break
    u = u.strip()
    if u.startswith("git://"):
        u = "https://" + u[len("git://"):]
    elif u.startswith("ssh://"):
        rest = u[len("ssh://"):]
        if rest.startswith("git@"):
            rest = rest[len("git@"):]
        if ":" in rest:
            host, _, path = rest.partition(":")
            if path and not path.split("/", 1)[0].isdigit():
                rest = f"{host}/{path}"
        u = "https://" + rest
    elif u.startswith("git@") and ":" in u:
        host, _, path = u.partition(":")
        u = f"https://{host[4:]}/{path}"
    if u.startswith("http://"):
        u = "https://" + u[len("http://"):]
    u = u.rstrip("/")
    lowered_u = u.lower()
    for host in ("github.com", "gitlab.com"):
        marker = f"/{host}/"
        pos = lowered_u.find(marker)
        if pos == -1:
            continue
        rest = u[pos + len(marker):]
        tree_pos = rest.lower().find("/tree/")
        if tree_pos != -1:
            u = u[: pos + len(marker) + tree_pos]
            if u.endswith("/-"):
                u = u[:-2]
        break
    if u.endswith(".git"):
        u = u[:-4]
    if urlparse(u).scheme != "https":
        return None
    return u


def extract_source_repo_url(version_data: dict) -> str | None:
    for link in version_data.get("links", []):
        if link.get("label") == "SOURCE_REPO" and link.get("url"):
            return str(link["url"])
    for project in version_data.get("relatedProjects", []):
        if project.get("relationType") == "SOURCE_REPO":
            project_id = project.get("projectKey", {}).get("id")
            if project_id:
                return f"https://{project_id}"
    return None


class DepsdevResolver(Resolver):

    def __init__(
        self,
        timeout: float = 15.0,
        max_requests_per_second: float = _DEFAULT_MAX_REQUESTS_PER_SECOND,
        retry_config: RetryConfig | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(timeout=timeout)
        self._min_interval = (
            1.0 / max_requests_per_second if max_requests_per_second > 0 else 0
        )
        self._last_request_time = 0.0
        self._retry = RetryHelper(retry_config or RetryConfig())

    @property
    def name(self) -> str:
        return "depsdev"

    async def resolve(self, purl: str) -> Resolution:
        try:
            components = validate(purl)
        except PurlValidationError as e:
            return Resolution(purl=purl, warnings=[f"Invalid PURL: {e}"])

        system = _SYSTEMS.get(components.type)
        if system is None:
            return Resolution(
                purl=purl,
                warnings=[f"Unsupported package type '{components.type}' for deps.dev resolver"],
            )

        package_name = build_package_name(components.type, components.namespace, components.name)
        encoded_name = quote(package_name, safe="")

        version = components.version
        if version is None:
            data, error = await self._get_json(
                purl,
                f"{_API_BASE}/systems/{system}/packages/{encoded_name}",
            )
            if error is not None:
                return Resolution(purl=purl, warnings=[error])
            versions = (data or {}).get("versions") or []
            if not versions:
                return Resolution(purl=purl, warnings=[f"No versions found on deps.dev for {purl}"])
            chosen = next((v for v in versions if v.get("isDefault")), None)
            if chosen is None:
                dated = [v for v in versions if v.get("publishedAt")]
                chosen = max(dated, key=lambda v: v["publishedAt"]) if dated else versions[-1]
            version = chosen.get("versionKey", {}).get("version")
            if not version:
                warning = f"No version key found on deps.dev for {purl}"
                return Resolution(purl=purl, warnings=[warning])

        version_url = (
            f"{_API_BASE}/systems/{system}/packages/{encoded_name}"
            f"/versions/{quote(version, safe='')}"
        )
        version_data, error = await self._get_json(purl, version_url)
        if error is not None:
            return Resolution(purl=purl, warnings=[error])

        repo_url = extract_source_repo_url(version_data or {})
        if not repo_url:
            warning = f"No SOURCE_REPO link found on deps.dev for {purl}"
            return Resolution(purl=purl, warnings=[warning])

        normalized_url = normalize_repository_url(repo_url)
        if normalized_url is None:
            warning = f"Invalid repository URL from deps.dev for {purl}: {repo_url}"
            return Resolution(purl=purl, warnings=[warning])

        logger.info("deps.dev resolved %s to %s", purl, normalized_url)
        return Resolution(purl=purl, repository_url=normalized_url)

    async def _get_json(self, purl: str, url: str) -> tuple[dict | None, str | None]:
        await self._rate_limit_wait()
        try:
            response = await self._retry.execute(lambda: self._client.get(url))
            response.raise_for_status()
            return response.json(), None
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            logger.warning("deps.dev returned %d for %s", status, purl)
            return None, f"deps.dev error {status} for {purl}"
        except httpx.TimeoutException:
            logger.warning("deps.dev request timed out for %s", purl)
            return None, f"deps.dev timeout for {purl}"
        except httpx.HTTPError as exc:
            logger.warning("deps.dev request failed for %s: %s", purl, exc)
            return None, f"deps.dev network error for {purl}: {exc}"
        except ValueError:
            logger.warning("deps.dev returned non-JSON response for %s", purl)
            return None, f"deps.dev invalid response for {purl}"

    async def _rate_limit_wait(self) -> None:
        if self._min_interval <= 0:
            return
        now = time.monotonic()
        elapsed = now - self._last_request_time
        if elapsed < self._min_interval:
            await asyncio.sleep(self._min_interval - elapsed)
        self._last_request_time = time.monotonic()
