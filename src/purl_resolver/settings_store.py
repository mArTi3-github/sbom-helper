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
    ecosystems_enabled: bool = True
    ecosystems_api_key: str | None = None
    ecosystems_max_requests_per_second: float = Field(default=2.0, ge=0.1, le=100)
    revalidation_cooldown_hours: int = Field(default=24, ge=0, le=720)
    retry_max_attempts: int = Field(default=3, ge=1, le=10)
    retry_base_cooldown_seconds: float = Field(default=5.0, ge=0.5, le=120.0)
    log_level: str = Field(default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")

    def log_level_as_int(self) -> int:
        return getattr(logging, self.log_level.upper(), logging.INFO)

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
