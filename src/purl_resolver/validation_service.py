from __future__ import annotations

from .settings_store import SettingsStore
from .url_validator import UrlValidationOutput, validate_url_with_retry


class UrlValidationService:
    """Wraps validate_url_with_retry, injecting settings from SettingsStore."""

    def __init__(self, settings_store: SettingsStore) -> None:
        self._settings_store = settings_store

    async def validate_url(
        self,
        url: str,
        timeout: int,
        github_token: str | None = None,
        skip_connectivity_check: bool = False,
    ) -> UrlValidationOutput:
        return await validate_url_with_retry(
            url, timeout,
            github_token=github_token,
            settings_store=self._settings_store,
            skip_connectivity_check=skip_connectivity_check,
        )
