from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from purl_resolver.schemas import ResolveResponse, ResolveResult
from purl_resolver.service import resolve_purl, _validate_cached_url
from purl_resolver.settings_store import AppSettings, SettingsStore
from purl_resolver.url_validator import UrlValidationResult


class TestFoundBy:
    @pytest.mark.asyncio
    async def test_found_by_local_db_when_cached(self, mock_storage, mock_settings_store, resolver):
        from datetime import datetime
        cached = ResolveResponse(
            purl="pkg:pypi/requests",
            repository_url="https://github.com/psf/requests",
            resolver="purl2repo",
            resolved_at=datetime.now().isoformat(),
        )
        mock_storage.lookup = AsyncMock(return_value=cached)
        with patch("purl_resolver.service._validate_cached_url", new_callable=AsyncMock, return_value=cached):
            result = await resolve_purl(
                "pkg:pypi/requests@2.31.0", mock_storage, [resolver], mock_settings_store
            )
        assert result.response is not None
        assert result.response.found_by == "local_db"
        assert result.response.resolver == "purl2repo"

    @pytest.mark.asyncio
    async def test_found_by_resolver_when_fresh(self, mock_storage, mock_settings_store, resolver):
        mock_storage.lookup = AsyncMock(return_value=None)
        resolver.name = "fake_resolver"
        result = await resolve_purl(
            "pkg:pypi/requests@2.31.0", mock_storage, [resolver], mock_settings_store
        )
        assert result.response is not None
        assert result.response.found_by == "resolver"
        assert result.response.resolver == "fake_resolver"


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
    r = AsyncMock()
    r.name = "test_resolver"
    r.resolve = AsyncMock(return_value=AsyncMock(
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


@pytest.mark.asyncio
async def test_resolve_purl_passes_token_to_validate_url():
    storage = AsyncMock()
    storage.lookup = AsyncMock(return_value=_cached_response(days_ago=3))
    storage.store = AsyncMock()
    settings_store = MagicMock(spec=SettingsStore)
    settings_store.load.return_value = AppSettings(
        validate_db_urls=True,
        github_token="ghp_test123",
    )
    with patch("purl_resolver.service.validate_url", new_callable=AsyncMock, return_value=UrlValidationResult.VALID) as mock_validate:
        await resolve_purl(
            purl="pkg:pypi/requests@2.31.0",
            storage=storage,
            resolvers=[],
            settings_store=settings_store,
        )
        mock_validate.assert_called()
        call_kwargs = mock_validate.call_args[1]
        assert call_kwargs.get("github_token") == "ghp_test123"


@pytest.mark.asyncio
async def test_resolve_purl_handles_token_invalid():
    storage = AsyncMock()
    storage.lookup = AsyncMock(return_value=_cached_response(days_ago=3))
    storage.store = AsyncMock()
    storage.delete_purls = AsyncMock(return_value=1)
    settings_store = MagicMock(spec=SettingsStore)
    settings_store.load.return_value = AppSettings(
        validate_db_urls=True,
        github_token="ghp_invalid",
    )
    with patch("purl_resolver.service.validate_url", new_callable=AsyncMock) as mock_validate, \
         patch.object(settings_store, "save") as mock_save:
        mock_validate.side_effect = [
            UrlValidationResult.TOKEN_INVALID,
            UrlValidationResult.VALID,
        ]
        await resolve_purl(
            purl="pkg:pypi/requests@2.31.0",
            storage=storage,
            resolvers=[],
            settings_store=settings_store,
        )
        mock_save.assert_called_once()
        saved_settings = mock_save.call_args[0][0]
        assert saved_settings.github_token is None


class TestValidateCachedUrl:
    @pytest.mark.asyncio
    async def test_returns_cached_when_no_settings_store(self):
        cached = ResolveResponse(
            purl="pkg:pypi/requests",
            repository_url="https://github.com/psf/requests",
        )
        result = await _validate_cached_url(cached, None, "pkg:pypi/requests", AsyncMock())
        assert result == cached

    @pytest.mark.asyncio
    async def test_returns_cached_when_validation_disabled(self):
        cached = ResolveResponse(
            purl="pkg:pypi/requests",
            repository_url="https://github.com/psf/requests",
        )
        settings_store = MagicMock()
        settings_store.load.return_value = MagicMock(validate_db_urls=False)
        result = await _validate_cached_url(cached, settings_store, "pkg:pypi/requests", AsyncMock())
        assert result == cached

    @pytest.mark.asyncio
    async def test_returns_cached_when_resolved_today(self):
        cached = ResolveResponse(
            purl="pkg:pypi/requests",
            repository_url="https://github.com/psf/requests",
            resolved_at=datetime.now().isoformat(),
        )
        settings_store = MagicMock()
        settings_store.load.return_value = MagicMock(validate_db_urls=True)
        result = await _validate_cached_url(cached, settings_store, "pkg:pypi/requests", AsyncMock())
        assert result == cached

    @pytest.mark.asyncio
    async def test_updates_resolved_at_on_valid_url(self):
        cached = ResolveResponse(
            purl="pkg:pypi/requests",
            repository_url="https://github.com/psf/requests",
            resolved_at="2020-01-01T00:00:00",
        )
        settings_store = MagicMock()
        settings_store.load.return_value = MagicMock(
            validate_db_urls=True,
            github_token=None,
            url_validation_timeout=5,
        )
        storage = AsyncMock()
        with patch("purl_resolver.service.validate_url", return_value=UrlValidationResult.VALID):
            result = await _validate_cached_url(cached, settings_store, "pkg:pypi/requests", storage)
        assert result == cached
        storage.store.assert_called_once_with(cached)

    @pytest.mark.asyncio
    async def test_deletes_cache_on_invalid_url(self):
        cached = ResolveResponse(
            purl="pkg:pypi/requests",
            repository_url="https://github.com/psf/requests",
            resolved_at="2020-01-01T00:00:00",
        )
        settings_store = MagicMock()
        settings_store.load.return_value = MagicMock(
            validate_db_urls=True,
            github_token=None,
            url_validation_timeout=5,
        )
        storage = AsyncMock()
        with patch("purl_resolver.service.validate_url", return_value=UrlValidationResult.INVALID):
            result = await _validate_cached_url(cached, settings_store, "pkg:pypi/requests", storage)
        assert result is None
        storage.delete_purls.assert_called_once_with(["pkg:pypi/requests"])

    @pytest.mark.asyncio
    async def test_removes_token_on_token_invalid(self):
        cached = ResolveResponse(
            purl="pkg:pypi/requests",
            repository_url="https://github.com/psf/requests",
            resolved_at="2020-01-01T00:00:00",
        )
        settings_store = MagicMock()
        app_settings = MagicMock(
            validate_db_urls=True,
            github_token="ghp_invalid",
            url_validation_timeout=5,
        )
        settings_store.load.return_value = app_settings
        storage = AsyncMock()
        with patch("purl_resolver.service.validate_url") as mock_validate:
            mock_validate.side_effect = [UrlValidationResult.TOKEN_INVALID, UrlValidationResult.VALID]
            result = await _validate_cached_url(cached, settings_store, "pkg:pypi/requests", storage)
        assert result == cached
        settings_store.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_cached_on_network_error(self):
        cached = ResolveResponse(
            purl="pkg:pypi/requests",
            repository_url="https://github.com/psf/requests",
            resolved_at="2020-01-01T00:00:00",
        )
        settings_store = MagicMock()
        settings_store.load.return_value = MagicMock(
            validate_db_urls=True,
            github_token=None,
            url_validation_timeout=5,
        )
        storage = AsyncMock()
        with patch("purl_resolver.service.validate_url", return_value=UrlValidationResult.NETWORK_ERROR):
            result = await _validate_cached_url(cached, settings_store, "pkg:pypi/requests", storage)
        assert result == cached
