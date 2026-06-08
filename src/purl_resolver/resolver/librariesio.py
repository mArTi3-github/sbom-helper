from __future__ import annotations

import asyncio
import logging
import time
from urllib.parse import quote

import httpx

from ..purl_utils import PurlValidationError, validate
from .interface import Resolution, Resolver

logger = logging.getLogger(__name__)

_API_BASE = "https://libraries.io/api"


class LibrariesIoResolver(Resolver):

    ECOSYSTEM_MAP: dict[str, str] = {
        "cargo": "Cargo",
        "composer": "Packagist",
        "conda": "Conda",
        "cpan": "CPAN",
        "cran": "CRAN",
        "gem": "RubyGems",
        "generic": "GitHub",
        "golang": "Go",
        "hackage": "Hackage",
        "hex": "Hex",
        "maven": "Maven",
        "npm": "NPM",
        "nuget": "NuGet",
        "pub": "Pub",
        "pypi": "PyPI",
        "swift": "SwiftPM",
    }

    def __init__(self, api_key: str, timeout: float = 15.0) -> None:
        self._api_key = api_key
        self._timeout = timeout
        self._min_interval = 1.0
        self._last_request_time = 0.0
        self._client = httpx.AsyncClient(timeout=timeout)

    @property
    def name(self) -> str:
        return "libraries.io"

    async def resolve(self, purl: str) -> Resolution:
        try:
            components = validate(purl)
        except PurlValidationError as e:
            return Resolution(purl=purl, warnings=[f"Invalid PURL: {e}"])

        platform = self.ECOSYSTEM_MAP.get(components.type)
        if platform is None:
            return Resolution(
                purl=purl,
                warnings=[f"Unsupported package type '{components.type}' for libraries.io"],
            )

        name = components.name
        await self._rate_limit_wait()

        encoded_name = quote(name, safe="")
        url = f"{_API_BASE}/{platform}/{encoded_name}"
        try:
            response = await self._client.get(url, params={"api_key": self._api_key})
            response.raise_for_status()
        except httpx.TimeoutException:
            logger.warning("libraries.io request timed out for %s/%s", platform, name)
            return Resolution(purl=purl, warnings=[f"libraries.io timeout for {platform}/{name}"])
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            logger.warning("libraries.io returned %d for %s/%s", status, platform, name)
            return Resolution(purl=purl, warnings=[f"libraries.io error {status} for {platform}/{name}"])
        except httpx.HTTPError as exc:
            logger.warning("libraries.io request failed for %s/%s: %s", platform, name, exc)
            return Resolution(purl=purl, warnings=[f"libraries.io network error for {platform}/{name}: {exc}"])

        data = response.json()
        repo_url = data.get("repository_url", "")
        if not repo_url:
            return Resolution(purl=purl, warnings=[f"No repository found on libraries.io for {platform}/{name}"])

        return Resolution(
            purl=purl,
            repository_url=repo_url,
            repository_type=None,
            repository_kind="vcs",
            confidence="medium",
            evidence=[f"libraries.io:{platform}/{name}"],
        )

    async def _rate_limit_wait(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_request_time
        if elapsed < self._min_interval:
            await asyncio.sleep(self._min_interval - elapsed)
        self._last_request_time = time.monotonic()
