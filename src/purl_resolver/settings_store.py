from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


@dataclass
class ServiceTokens:
    github_token: str | None = None


class AppSettings(BaseModel):
    validate_db_urls: bool = False
    url_validation_timeout: int = Field(default=5, ge=1, le=60)
    github_token: str | None = None
    librariesio_enabled: bool = False
    librariesio_api_key: str | None = None

    def service_tokens(self) -> ServiceTokens:
        return ServiceTokens(github_token=self.github_token)


class SettingsStore:

    def __init__(self, path: str | Path | None = None) -> None:
        if path is None:
            path = os.environ.get("SETTINGS_FILE", "./data/settings.json")
        self._path = Path(path)

    def load(self) -> AppSettings:
        if not self._path.exists():
            self._ensure_parent()
            defaults = AppSettings()
            self._write(defaults)
            return defaults

        try:
            raw = self._path.read_text(encoding="utf-8")
            data = json.loads(raw)
            return AppSettings(**data)
        except json.JSONDecodeError as exc:
            logger.warning("Corrupt settings file at %s, using defaults: %s", self._path, exc)
            return AppSettings()

    def save(self, settings: AppSettings) -> None:
        self._ensure_parent()
        self._write(settings)

    def _ensure_parent(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _write(self, settings: AppSettings) -> None:
        self._path.write_text(
            json.dumps(settings.model_dump(), indent=2) + "\n",
            encoding="utf-8",
        )
