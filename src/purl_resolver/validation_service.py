from __future__ import annotations

import logging

from .settings_store import SettingsStore
from .url_validation_cache import UrlValidationCache
from .url_validator import UrlValidationOutput, UrlValidationResult, validate_url

logger = logging.getLogger(__name__)


class UrlValidationService:
    def __init__(self, settings_store: SettingsStore, cache: UrlValidationCache) -> None:
        self._settings_store = settings_store
        self._cache = cache

    async def validate_url(
        self,
        url: str,
        timeout: int,
    ) -> UrlValidationOutput:
        app_settings = self._settings_store.load()
        if app_settings.validate_db_urls:
            max_age = app_settings.revalidation_cooldown_hours * 3600
            cached = self._cache.get(url, max_age)
            if cached is not None:
                logger.info("Validation cache hit for %s", url)
                return UrlValidationOutput(UrlValidationResult.VALID, final_url=None)

        logger.info("Validation cache miss for %s, performing full validation", url)
        voutput = await validate_url(url, timeout)

        if voutput.result == UrlValidationResult.VALID and app_settings.validate_db_urls:
            logger.debug("Cached validation result for %s", url)
            self._cache.put(url)

        return voutput

    def clear_cache(self) -> None:
        self._cache.clear()
