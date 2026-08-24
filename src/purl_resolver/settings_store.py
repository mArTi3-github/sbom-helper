from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from typing import Literal

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class AppSettings(BaseModel):
    validate_db_urls: bool = False
    validate_sbom_refs: bool = False
    sbom_multiple_vcs_behavior: str = Field(default="keep-first", pattern="^(keep-first|keep-all)$")
    url_validation_timeout: int = Field(default=5, ge=1, le=60)
    librariesio_enabled: bool = False
    librariesio_api_key: str | None = None
    ecosystems_enabled: bool = True
    ecosystems_api_key: str | None = None
    ecosystems_max_requests_per_second: float = Field(default=2.0, ge=0.1, le=100)
    revalidation_cooldown_hours: int = Field(default=24, ge=0, le=720)
    retry_max_attempts: int = Field(default=3, ge=1, le=10)
    retry_base_cooldown_seconds: float = Field(default=5.0, ge=0.5, le=120.0)
    log_level: str = Field(default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")
    batch_semaphore_limit: int = Field(default=10, ge=1, le=100)
    job_ttl_hours: int = Field(default=24, ge=1, le=720)
    connectivity_url: str = Field(default="https://github.com")
    connectivity_timeout: int = Field(default=2, ge=1, le=30)
    json_indent: Literal[1, 2, 4] = Field(default=4)
    apk_resolver_enabled: bool = True
    llm_resolver_enabled: bool = False
    llm_resolver_base_url: str | None = Field(default=None, pattern=r"^https?://.+")
    llm_resolver_api_key: str | None = None
    llm_resolver_model: str | None = None
    llm_resolver_attempts_count: int = Field(default=2, ge=1, le=10)
    llm_resolver_timeout: float = Field(default=60.0, ge=1, le=600)

    def log_level_as_int(self) -> int:
        return getattr(logging, self.log_level.upper(), logging.INFO)


class SettingsStore:

    def __init__(self, path: str | Path | None = None) -> None:
        if path is None:
            path = os.environ.get("SETTINGS_FILE", "./data/settings.json")
        self._path = Path(path)
        self._cached: AppSettings | None = None

    def load(self) -> AppSettings:
        if self._cached is not None:
            return self._cached
        if not self._path.exists():
            self._ensure_parent()
            defaults = AppSettings()
            self._write(defaults)
            self._cached = defaults
            return defaults

        try:
            raw = self._path.read_text(encoding="utf-8")
            data = json.loads(raw)
            self._cached = AppSettings(**data)
            return self._cached
        except json.JSONDecodeError as exc:
            logger.warning("Corrupt settings file at %s, using defaults: %s", self._path, exc)
            self._cached = AppSettings()
            return self._cached

    def save(self, settings: AppSettings) -> None:
        self._cached = None
        self._ensure_parent()
        self._write(settings)

    def _ensure_parent(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _write(self, settings: AppSettings) -> None:
        self._path.write_text(
            json.dumps(settings.model_dump(), indent=2) + "\n",
            encoding="utf-8",
        )
