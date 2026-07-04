from __future__ import annotations

import time
import logging
from diskcache import Cache

logger = logging.getLogger(__name__)


class UrlValidationCache:
    def __init__(self, cache_dir: str) -> None:
        self._cache = Cache(cache_dir)

    def get(self, url: str, max_age_seconds: int) -> str | None:
        raw = self._cache.get(url, default=None)
        if raw is None:
            return None
        if time.time() - raw > max_age_seconds:
            return None
        return url

    def put(self, url: str) -> None:
        self._cache.set(url, time.time())

    def expire(self, max_age_seconds: int) -> None:
        cutoff = time.time() - max_age_seconds
        for key in list(self._cache):
            val = self._cache.get(key)
            if val is not None and val < cutoff:
                del self._cache[key]

    def clear(self) -> None:
        self._cache.clear()