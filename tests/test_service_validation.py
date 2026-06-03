from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from purl_resolver.schemas import ResolveResponse, ResolveResult
from purl_resolver.service import resolve_purl
from purl_resolver.url_validator import UrlValidationResult


def _cached_response(purl: str = "pkg:pypi/requests", days_ago: int = 0) -> ResolveResponse:
    resolved_at = (datetime.now() - timedelta(days=days_ago)).isoformat()
    return ResolveResponse(
        purl=purl,
        repository_url="https://github.com/psf/requests",
        resolved_at=resolved_at,
    )


@pytest.fixture
def mock_storage():
    storage = AsyncMock()
    storage.lookup = AsyncMock(return_value=None)
    storage.store = AsyncMock()
    storage.delete_purls = AsyncMock(return_value=1)
    return storage


@pytest.fixture
def mock_settings_store():
    store = MagicMock()
    store.load = MagicMock(return_value=MagicMock(validate_db_urls=True, url_validation_timeout=5))
    return store


@pytest.fixture
def resolver():
    r = MagicMock()
    r.resolve = MagicMock(return_value=MagicMock(
        repository_url="https://github.com/new/repo",
        repository_type="git",
        repository_kind="github",
        confidence="high",
        evidence=["test"],
        warnings=[],
        version_reference=None,
    ))
    return r


class TestValidationIntegration:
    @pytest.mark.asyncio
    async def test_valid_url_updates_resolved_at(self, mock_storage, mock_settings_store):
        mock_storage.lookup.return_value = _cached_response(days_ago=3)
        with patch("purl_resolver.service.validate_url", new_callable=AsyncMock, return_value=UrlValidationResult.VALID):
            result = await resolve_purl(
                "pkg:pypi/requests", mock_storage, [],
                settings_store=mock_settings_store,
            )
            assert result.response is not None
            mock_storage.store.assert_called_once()
            mock_storage.delete_purls.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_url_deletes_and_falls_through(self, mock_storage, mock_settings_store, resolver):
        mock_storage.lookup.return_value = _cached_response(days_ago=3)
        with patch("purl_resolver.service.validate_url", new_callable=AsyncMock, return_value=UrlValidationResult.INVALID):
            result = await resolve_purl(
                "pkg:pypi/requests", mock_storage, [resolver],
                settings_store=mock_settings_store,
            )
            mock_storage.delete_purls.assert_called_once_with(["pkg:pypi/requests"])
            resolver.resolve.assert_called_once()

    @pytest.mark.asyncio
    async def test_network_error_returns_cached(self, mock_storage, mock_settings_store):
        mock_storage.lookup.return_value = _cached_response(days_ago=3)
        with patch("purl_resolver.service.validate_url", new_callable=AsyncMock, return_value=UrlValidationResult.NETWORK_ERROR):
            result = await resolve_purl(
                "pkg:pypi/requests", mock_storage, [],
                settings_store=mock_settings_store,
            )
            assert result.response is not None
            mock_storage.store.assert_not_called()
            mock_storage.delete_purls.assert_not_called()

    @pytest.mark.asyncio
    async def test_rate_limited_returns_cached(self, mock_storage, mock_settings_store):
        mock_storage.lookup.return_value = _cached_response(days_ago=3)
        with patch("purl_resolver.service.validate_url", new_callable=AsyncMock, return_value=UrlValidationResult.RATE_LIMITED):
            result = await resolve_purl(
                "pkg:pypi/requests", mock_storage, [],
                settings_store=mock_settings_store,
            )
            assert result.response is not None
            mock_storage.store.assert_not_called()

    @pytest.mark.asyncio
    async def test_validate_db_urls_false_skips_validation(self, mock_storage):
        mock_storage.lookup.return_value = _cached_response(days_ago=3)
        settings_store = MagicMock()
        settings_store.load = MagicMock(return_value=MagicMock(validate_db_urls=False))
        with patch("purl_resolver.service.validate_url", new_callable=AsyncMock) as mock_validate:
            result = await resolve_purl(
                "pkg:pypi/requests", mock_storage, [],
                settings_store=settings_store,
            )
            mock_validate.assert_not_called()

    @pytest.mark.asyncio
    async def test_resolved_at_today_skips_validation(self, mock_storage, mock_settings_store):
        mock_storage.lookup.return_value = _cached_response(days_ago=0)
        with patch("purl_resolver.service.validate_url", new_callable=AsyncMock) as mock_validate:
            result = await resolve_purl(
                "pkg:pypi/requests", mock_storage, [],
                settings_store=mock_settings_store,
            )
            mock_validate.assert_not_called()

    @pytest.mark.asyncio
    async def test_settings_store_none_skips_validation(self, mock_storage):
        mock_storage.lookup.return_value = _cached_response(days_ago=3)
        with patch("purl_resolver.service.validate_url", new_callable=AsyncMock) as mock_validate:
            result = await resolve_purl("pkg:pypi/requests", mock_storage, [])
            mock_validate.assert_not_called()
