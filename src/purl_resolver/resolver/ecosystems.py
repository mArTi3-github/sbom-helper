from __future__ import annotations

import asyncio
import logging
import time

import httpx

from ..purl_utils import PurlValidationError, validate
from .interface import Resolution, Resolver
from .retry import RetryConfig, RetryHelper

logger = logging.getLogger(__name__)

_API_URL = "https://packages.ecosyste.ms/api/v1/packages/lookup"


def select_repository_url(package_data: dict) -> str | None:
    candidates = [
        package_data.get("repository_url", ""),
        package_data.get("registry_url", ""),
        package_data.get("homepage", ""),
    ]

    for url in candidates:
        if not url or "repos.ecosyste.ms" in url:
            continue
        if "github.com" in url:
            return url

    for url in candidates:
        if url and "repos.ecosyste.ms" not in url:
            return url

    return None


class EcosystemsResolver(Resolver):

    def __init__(
        self,
        api_key: str | None = None,
        timeout: float = 15.0,
        max_requests_per_second: float = 2.0,
        retry_config: RetryConfig | None = None,
    ) -> None:
        self._api_key = api_key
        self._timeout = timeout
        self._client = httpx.AsyncClient(timeout=timeout)
        self._min_interval = 1.0 / max_requests_per_second if max_requests_per_second > 0 else 0
        self._last_request_time = 0.0
        self._retry = RetryHelper(retry_config or RetryConfig())

    @property
    def name(self) -> str:
        return "ecosyste.ms"

    async def resolve(self, purl: str) -> Resolution:
        try:
            validate(purl)
        except PurlValidationError as e:
            return Resolution(purl=purl, warnings=[f"Invalid PURL: {e}"])

        params: dict[str, str] = {"purl": purl}
        if self._api_key:
            params["api_key"] = self._api_key

        await self._rate_limit_wait()

        try:
            response = await self._retry.execute(lambda: self._client.get(_API_URL, params=params))
            response.raise_for_status()
            logger.info("ecosyste.ms resolved %s successfully", purl)
        except httpx.TimeoutException:
            logger.warning("ecosyste.ms request timed out for %s", purl)
            return Resolution(purl=purl, warnings=[f"ecosyste.ms timeout for {purl}"])
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            logger.warning("ecosyste.ms returned %d for %s", status, purl)
            return Resolution(purl=purl, warnings=[f"ecosyste.ms error {status} for {purl}"])
        except httpx.HTTPError as exc:
            logger.warning("ecosyste.ms request failed for %s: %s", purl, exc)
            return Resolution(purl=purl, warnings=[f"ecosyste.ms network error for {purl}: {exc}"])

        data = response.json()
        if not isinstance(data, list) or not data:
            return Resolution(purl=purl, warnings=[f"No package found on ecosyste.ms for {purl}"])

        package = data[0]
        repo_url = select_repository_url(package)
        if not repo_url:
            return Resolution(purl=purl, warnings=[f"No repository URL found on ecosyste.ms for {purl}"])

        ecosystem = package.get("ecosystem", "unknown")
        name = package.get("name", "unknown")

        return Resolution(
            purl=purl,
            repository_url=repo_url,
        )

    async def _rate_limit_wait(self) -> None:
        if self._min_interval <= 0:
            return
        now = time.monotonic()
        elapsed = now - self._last_request_time
        if elapsed < self._min_interval:
            await asyncio.sleep(self._min_interval - elapsed)
        self._last_request_time = time.monotonic()
