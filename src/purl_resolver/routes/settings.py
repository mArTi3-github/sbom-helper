from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from typing import Literal

from pydantic import BaseModel, Field

from ..settings_store import SettingsStore
from ..url_validator import validate_github_token
from ..config import settings
from ..resolver.factory import build_resolvers

router = APIRouter()


async def validate_librariesio_key(api_key: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://libraries.io/api/platforms",
                params={"api_key": api_key},
            )
            return response.status_code == 200
    except httpx.HTTPError:
        return True


class SettingsUpdate(BaseModel):
    validate_db_urls: bool | None = None
    url_validation_timeout: int | None = Field(None, ge=1, le=60)
    github_token: str | None = None
    librariesio_enabled: bool | None = None
    librariesio_api_key: str | None = None
    ecosystems_enabled: bool | None = None
    ecosystems_api_key: str | None = None
    ecosystems_max_requests_per_second: float | None = Field(None, ge=0.1, le=100)
    revalidation_cooldown_hours: int | None = Field(None, ge=0, le=720)
    retry_max_attempts: int | None = Field(None, ge=1, le=10)
    retry_base_cooldown_seconds: float | None = Field(None, ge=0.5, le=120.0)
    log_level: str | None = Field(None, pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")
    batch_semaphore_limit: int | None = Field(None, ge=1, le=100)
    connectivity_url: str | None = None
    connectivity_timeout: int | None = Field(None, ge=1, le=30)
    rate_limit_cooldown: int | None = Field(None, ge=1, le=600)
    json_indent: Literal[1, 2, 4] | None = Field(None)


def _rebuild_resolvers(request: Request) -> None:
    store: SettingsStore = request.app.state.settings_store
    app_settings = store.load()
    request.app.state.resolvers = build_resolvers(settings, app_settings)


def _reconfigure_logging(request: Request) -> None:
    store: SettingsStore = request.app.state.settings_store
    app_settings = store.load()
    logging.basicConfig(level=app_settings.log_level_as_int(), force=True)


@router.get("/api/v1/settings")
async def get_settings(request: Request) -> JSONResponse:
    store: SettingsStore = request.app.state.settings_store
    app_settings = store.load()
    return JSONResponse(content={
        "validate_db_urls": app_settings.validate_db_urls,
        "url_validation_timeout": app_settings.url_validation_timeout,
        "revalidation_cooldown_hours": app_settings.revalidation_cooldown_hours,
        "retry_max_attempts": app_settings.retry_max_attempts,
        "retry_base_cooldown_seconds": app_settings.retry_base_cooldown_seconds,
        "log_level": app_settings.log_level,
        "librariesio_enabled": app_settings.librariesio_enabled,
        "ecosystems_enabled": app_settings.ecosystems_enabled,
        "ecosystems_max_requests_per_second": app_settings.ecosystems_max_requests_per_second,
        "batch_semaphore_limit": app_settings.batch_semaphore_limit,
        "connectivity_url": app_settings.connectivity_url,
        "connectivity_timeout": app_settings.connectivity_timeout,
        "rate_limit_cooldown": app_settings.rate_limit_cooldown,
        "json_indent": app_settings.json_indent,
        "token_set": {
            "github_token": app_settings.github_token is not None,
            "librariesio_api_key": app_settings.librariesio_api_key is not None,
            "ecosystems_api_key": app_settings.ecosystems_api_key is not None,
        },
    })


@router.patch("/api/v1/settings")
async def update_settings(body: SettingsUpdate, request: Request) -> JSONResponse:
    store: SettingsStore = request.app.state.settings_store
    current = store.load()
    update_data = body.model_dump(exclude_unset=True)

    if "github_token" in update_data:
        token_value = update_data["github_token"]
        if token_value is None:
            pass
        elif token_value == "":
            del update_data["github_token"]
        else:
            is_valid = await validate_github_token(token_value)
            if not is_valid:
                return JSONResponse(
                    status_code=400,
                    content={"error": "invalid_token", "message": "GitHub token is invalid or expired"},
                )

    if "librariesio_api_key" in update_data:
        key_value = update_data["librariesio_api_key"]
        if key_value is None:
            pass
        elif key_value == "":
            del update_data["librariesio_api_key"]
        else:
            if not await validate_librariesio_key(key_value):
                return JSONResponse(
                    status_code=400,
                    content={"error": "invalid_token", "message": "Libraries.io API key is invalid"},
                )

    if update_data:
        updated = current.model_copy(update=update_data)
        store.save(updated)
    else:
        updated = current

    _rebuild_resolvers(request)
    _reconfigure_logging(request)

    return JSONResponse(content={
        "validate_db_urls": updated.validate_db_urls,
        "url_validation_timeout": updated.url_validation_timeout,
        "revalidation_cooldown_hours": updated.revalidation_cooldown_hours,
        "retry_max_attempts": updated.retry_max_attempts,
        "retry_base_cooldown_seconds": updated.retry_base_cooldown_seconds,
        "log_level": updated.log_level,
        "librariesio_enabled": updated.librariesio_enabled,
        "ecosystems_enabled": updated.ecosystems_enabled,
        "ecosystems_max_requests_per_second": updated.ecosystems_max_requests_per_second,
        "batch_semaphore_limit": updated.batch_semaphore_limit,
        "connectivity_url": updated.connectivity_url,
        "connectivity_timeout": updated.connectivity_timeout,
        "rate_limit_cooldown": updated.rate_limit_cooldown,
        "json_indent": updated.json_indent,
        "token_set": {
            "github_token": updated.github_token is not None,
            "librariesio_api_key": updated.librariesio_api_key is not None,
            "ecosystems_api_key": updated.ecosystems_api_key is not None,
        },
    })
