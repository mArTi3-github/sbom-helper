"""HTTP client with retries, timeouts, and resolver cache support."""

from __future__ import annotations

import time
from typing import Any

import httpx

from purl2repo.errors import MetadataFetchError
from purl2repo.http.retry import backoff_seconds
from purl2repo.models import ResolverSettings
from purl2repo.resolution.cache import ResponseCache

REGISTRY_TTL_SECONDS = 3600
RELEASE_TTL_SECONDS = 900


class HttpClient:
    def __init__(self, settings: ResolverSettings, cache: ResponseCache | None = None) -> None:
        self.settings = settings
        self.cache = cache if settings.use_cache else None
        self._client = httpx.Client(
            timeout=settings.timeout,
            follow_redirects=True,
            headers={"User-Agent": settings.user_agent},
        )

    def close(self) -> None:
        self._client.close()

    def get_json(self, url: str, *, ttl_seconds: int = REGISTRY_TTL_SECONDS) -> dict[str, Any]:
        cached = self._get_cached(url, ttl_seconds)
        if isinstance(cached, dict):
            return cached
        if self.settings.no_network:
            raise MetadataFetchError(f"Network disabled and no cached response for {url}")
        response = self._get(url)
        try:
            data = response.json()
        except ValueError as exc:
            raise MetadataFetchError(f"Invalid JSON response from {url}") from exc
        if not isinstance(data, dict):
            raise MetadataFetchError(f"Expected JSON object response from {url}")
        self._set_cached(url, data)
        return data

    def get_text(self, url: str, *, ttl_seconds: int = REGISTRY_TTL_SECONDS) -> str:
        cached = self._get_cached(url, ttl_seconds)
        if isinstance(cached, str):
            return cached
        if self.settings.no_network:
            raise MetadataFetchError(f"Network disabled and no cached response for {url}")
        response = self._get(url)
        self._set_cached(url, response.text)
        return response.text

    def url_exists(self, url: str, *, ttl_seconds: int = RELEASE_TTL_SECONDS) -> bool:
        cached = self._get_cached(f"exists:{url}", ttl_seconds)
        if isinstance(cached, bool):
            return cached
        if self.settings.no_network:
            raise MetadataFetchError(f"Network disabled and no cached response for {url}")
        if not url.startswith(("https://", "http://")):
            raise MetadataFetchError(f"Refusing to fetch non-web URL: {url}")

        exists = self._url_exists_uncached(url)
        self._set_cached(f"exists:{url}", exists)
        return exists

    def _get(self, url: str) -> httpx.Response:
        if not url.startswith(("https://", "http://")):
            raise MetadataFetchError(f"Refusing to fetch non-web URL: {url}")
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = self._client.get(url)
                if response.status_code in {429, 500, 502, 503, 504} and attempt < 2:
                    time.sleep(backoff_seconds(attempt))
                    continue
                response.raise_for_status()
                return response
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(backoff_seconds(attempt))
                    continue
        raise MetadataFetchError(
            f"Failed to fetch metadata from {url}: {last_error}"
        ) from last_error

    def _url_exists_uncached(self, url: str) -> bool:
        try:
            response = self._client.head(url)
            if response.status_code == 405 or response.status_code >= 400:
                response = self._client.get(url)
            return 200 <= response.status_code < 400
        except httpx.HTTPError as exc:
            raise MetadataFetchError(f"Failed to verify URL {url}: {exc}") from exc

    def _get_cached(self, url: str, ttl_seconds: int) -> Any | None:
        if not self.cache:
            return None
        return self.cache.get(url, ttl_seconds)

    def _set_cached(self, url: str, value: Any) -> None:
        if self.cache:
            self.cache.set(url, value)
