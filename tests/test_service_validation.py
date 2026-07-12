from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from purl_resolver.schemas import ResolveResponse
from purl_resolver.service import PurlResolutionService
from purl_resolver.settings_store import AppSettings, SettingsStore
from purl_resolver.url_validator import UrlValidationOutput, UrlValidationResult
from purl_resolver.validation_service import UrlValidationService


def _url_output(result: UrlValidationResult, final_url: str | None = None) -> UrlValidationOutput:
    return UrlValidationOutput(result=result, final_url=final_url)


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
        with patch.object(PurlResolutionService, "_validate_stored_url", new_callable=AsyncMock, return_value=cached):
            result = await PurlResolutionService(mock_storage, [resolver], mock_settings_store).resolve_purl(
                "pkg:pypi/requests@2.31.0"
            )
        assert result.response is not None
        assert result.response.found_by == "local_db"
        assert result.response.resolver == "purl2repo"

    @pytest.mark.asyncio
    async def test_found_by_resolver_when_fresh(self, mock_storage, resolver):
        mock_storage.lookup = AsyncMock(return_value=None)
        resolver.name = "fake_resolver"
        result = await PurlResolutionService(mock_storage, [resolver], settings_store=None).resolve_purl(
            "pkg:pypi/requests@2.31.0"
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
    settings = MagicMock(
        validate_db_urls=True, validate_sbom_refs=False,
        url_validation_timeout=5, revalidation_cooldown_hours=24,
    )
    store.load = MagicMock(return_value=settings)
    return store


@pytest.fixture
def mock_validation_service(mock_settings_store):
    vs = AsyncMock(spec=UrlValidationService)
    vs.validate_url.return_value = _url_output(UrlValidationResult.VALID)
    return vs


@pytest.fixture
def resolver():
    r = AsyncMock()
    r.name = "test_resolver"
    r.resolve = AsyncMock(return_value=AsyncMock(
        repository_url="https://github.com/new/repo",
    ))
    return r


class TestValidationIntegration:
    @pytest.mark.asyncio
    async def test_valid_url_updates_resolved_at(self, mock_storage, mock_settings_store, mock_validation_service):
        mock_storage.lookup.return_value = _cached_response(days_ago=3)
        mock_validation_service.validate_url.return_value = _url_output(UrlValidationResult.VALID)
        result = await PurlResolutionService(
            mock_storage, [],
            settings_store=mock_settings_store,
            validation_service=mock_validation_service,
        ).resolve_purl("pkg:pypi/requests")
        assert result.response is not None
        mock_storage.store.assert_not_called()
        mock_storage.delete_purls.assert_not_called()

    @pytest.mark.asyncio
    async def test_valid_url_with_redirect_stores(self, mock_storage, mock_settings_store, mock_validation_service):
        mock_storage.lookup.return_value = _cached_response(days_ago=3)
        mock_validation_service.validate_url.return_value = _url_output(UrlValidationResult.VALID, final_url="https://github.com/psf/requests-v2")
        result = await PurlResolutionService(
            mock_storage, [],
            settings_store=mock_settings_store,
            validation_service=mock_validation_service,
        ).resolve_purl("pkg:pypi/requests")
        assert result.response is not None
        mock_storage.store.assert_called_once()
        mock_storage.delete_purls.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_url_deletes_and_falls_through(self, mock_storage, mock_settings_store, mock_validation_service, resolver):
        mock_storage.lookup.return_value = _cached_response(days_ago=3)
        mock_validation_service.validate_url.return_value = _url_output(UrlValidationResult.INVALID)
        await PurlResolutionService(
            mock_storage, [resolver],
            settings_store=mock_settings_store,
            validation_service=mock_validation_service,
        ).resolve_purl("pkg:pypi/requests")
        mock_storage.delete_purls.assert_called_once_with(["pkg:pypi/requests"])
        resolver.resolve.assert_called_once()

    @pytest.mark.asyncio
    async def test_network_error_returns_cached(self, mock_storage, mock_settings_store, mock_validation_service):
        mock_storage.lookup.return_value = _cached_response(days_ago=3)
        mock_validation_service.validate_url.return_value = _url_output(UrlValidationResult.NETWORK_ERROR)
        result = await PurlResolutionService(
            mock_storage, [],
            settings_store=mock_settings_store,
            validation_service=mock_validation_service,
        ).resolve_purl("pkg:pypi/requests")
        assert result.response is not None
        mock_storage.store.assert_not_called()
        mock_storage.delete_purls.assert_not_called()

    @pytest.mark.asyncio
    async def test_validate_db_urls_false_skips_validation(self, mock_storage):
        mock_storage.lookup.return_value = _cached_response(days_ago=3)
        settings_store = MagicMock()
        settings_store.load = MagicMock(return_value=MagicMock(validate_db_urls=False))
        result = await PurlResolutionService(
            mock_storage, [],
            settings_store=settings_store,
            validation_service=None,
        ).resolve_purl("pkg:pypi/requests")
        assert result.response is not None


class TestValidateStoredUrl:
    """Tests for _validate_stored_url — replaces old _validate_cached_url + cooldown tests."""

    @pytest.mark.asyncio
    async def test_valid_url_returns_cached(self):
        cached = _cached_response(days_ago=3)
        service = PurlResolutionService(
            storage=AsyncMock(), resolvers=[],
            settings_store=MagicMock(),
            validation_service=AsyncMock(spec=UrlValidationService),
        )
        service._validation_service.validate_url.return_value = _url_output(UrlValidationResult.VALID)
        result = await service._validate_stored_url(cached, "pkg:pypi/requests")
        assert result is cached

    @pytest.mark.asyncio
    async def test_invalid_url_deletes_cached(self):
        cached = _cached_response(days_ago=3)
        storage = AsyncMock()
        storage.delete_purls = AsyncMock(return_value=1)
        service = PurlResolutionService(
            storage=storage, resolvers=[],
            settings_store=MagicMock(),
            validation_service=AsyncMock(spec=UrlValidationService),
        )
        service._validation_service.validate_url.return_value = _url_output(UrlValidationResult.INVALID)
        result = await service._validate_stored_url(cached, "pkg:pypi/requests")
        assert result is None
        storage.delete_purls.assert_called_once_with(["pkg:pypi/requests"])

    @pytest.mark.asyncio
    async def test_network_error_keeps_cached(self):
        cached = _cached_response(days_ago=3)
        storage = AsyncMock()
        service = PurlResolutionService(
            storage=storage, resolvers=[],
            settings_store=MagicMock(),
            validation_service=AsyncMock(spec=UrlValidationService),
        )
        service._validation_service.validate_url.return_value = _url_output(UrlValidationResult.NETWORK_ERROR)
        result = await service._validate_stored_url(cached, "pkg:pypi/requests")
        assert result is cached
        storage.delete_purls.assert_not_called()

    @pytest.mark.asyncio
    async def test_validate_db_urls_false_returns_cached_immediately(self):
        cached = _cached_response(days_ago=3)
        settings_store = MagicMock()
        settings_store.load = MagicMock(return_value=MagicMock(validate_db_urls=False))
        service = PurlResolutionService(
            storage=AsyncMock(), resolvers=[],
            settings_store=settings_store,
            validation_service=AsyncMock(spec=UrlValidationService),
        )
        result = await service._validate_stored_url(cached, "pkg:pypi/requests")
        assert result is cached
        service._validation_service.validate_url.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_validation_service_returns_cached(self):
        cached = _cached_response(days_ago=3)
        service = PurlResolutionService(
            storage=AsyncMock(), resolvers=[],
            settings_store=MagicMock(),
            validation_service=None,
        )
        result = await service._validate_stored_url(cached, "pkg:pypi/requests")
        assert result is cached

    @pytest.mark.asyncio
    async def test_redirect_updates_repository_url_and_stores(self):
        cached = _cached_response(days_ago=3)
        cached.repository_url = "https://old-url.com/repo"
        storage = AsyncMock()
        service = PurlResolutionService(
            storage=storage, resolvers=[],
            settings_store=MagicMock(),
            validation_service=AsyncMock(spec=UrlValidationService),
        )
        service._validation_service.validate_url.return_value = _url_output(
            UrlValidationResult.VALID, final_url="https://new-url.com/repo"
        )
        result = await service._validate_stored_url(cached, "pkg:pypi/requests")
        assert result is cached
        assert cached.repository_url == "https://new-url.com/repo"
        storage.store.assert_called_once()


class TestFreshResolverValidation:
    """Validation of freshly resolved URLs (not cached) when validate_db_urls is enabled."""

    @pytest.mark.asyncio
    async def test_skips_invalid_fresh_url_to_next_resolver(self, mock_storage, mock_settings_store, mock_validation_service):
        first = AsyncMock()
        first.name = "first_resolver"
        first.resolve = AsyncMock(return_value=AsyncMock(
            repository_url="https://github.com/not-found/repo",
        ))
        second = AsyncMock()
        second.name = "second_resolver"
        second.resolve = AsyncMock(return_value=AsyncMock(
            repository_url="https://github.com/valid/repo",
        ))
        mock_storage.lookup = AsyncMock(return_value=None)

        mock_validation_service.validate_url.side_effect = [
            _url_output(UrlValidationResult.INVALID),
            _url_output(UrlValidationResult.VALID),
        ]
        result = await PurlResolutionService(
            mock_storage, [first, second],
            settings_store=mock_settings_store,
            validation_service=mock_validation_service,
        ).resolve_purl("pkg:npm/archy@1.0.0")

        assert result.response is not None
        assert result.response.repository_url == "https://github.com/valid/repo"
        assert result.response.resolver == "second_resolver"
        assert result.response.found_by == "resolver"
        mock_storage.store.assert_called_once()
        assert mock_storage.store.call_args[0][0].repository_url == "https://github.com/valid/repo"

    @pytest.mark.asyncio
    async def test_accepts_valid_fresh_url(self, mock_storage, mock_settings_store, mock_validation_service):
        mock_storage.lookup = AsyncMock(return_value=None)
        resolver = AsyncMock()
        resolver.name = "test_resolver"
        resolver.resolve = AsyncMock(return_value=AsyncMock(
            repository_url="https://github.com/valid/repo",
        ))

        result = await PurlResolutionService(
            mock_storage, [resolver],
            settings_store=mock_settings_store,
            validation_service=mock_validation_service,
        ).resolve_purl("pkg:npm/archy@1.0.0")

        assert result.response is not None
        assert result.response.repository_url == "https://github.com/valid/repo"
        mock_storage.store.assert_called_once()

    @pytest.mark.asyncio
    async def test_accepts_fresh_url_on_network_error(self, mock_storage, mock_settings_store, mock_validation_service):
        mock_storage.lookup = AsyncMock(return_value=None)
        resolver = AsyncMock()
        resolver.name = "test_resolver"
        resolver.resolve = AsyncMock(return_value=AsyncMock(
            repository_url="https://github.com/some/repo",
        ))

        mock_validation_service.validate_url.return_value = _url_output(UrlValidationResult.NETWORK_ERROR)
        result = await PurlResolutionService(
            mock_storage, [resolver],
            settings_store=mock_settings_store,
            validation_service=mock_validation_service,
        ).resolve_purl("pkg:npm/archy@1.0.0")

        assert result.response is not None
        assert result.response.repository_url == "https://github.com/some/repo"
        mock_storage.store.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_validation_when_validate_db_urls_false(self, mock_storage):
        settings_store = MagicMock()
        settings_store.load = MagicMock(return_value=MagicMock(validate_db_urls=False))
        mock_storage.lookup = AsyncMock(return_value=None)
        resolver = AsyncMock()
        resolver.name = "test_resolver"
        resolver.resolve = AsyncMock(return_value=AsyncMock(
            repository_url="https://github.com/any/repo",
        ))

        result = await PurlResolutionService(
            mock_storage, [resolver], settings_store,
            validation_service=None,
        ).resolve_purl("pkg:npm/archy@1.0.0")

        assert result.response is not None

    @pytest.mark.asyncio
    async def test_all_resolvers_return_invalid_returns_unresolved(self, mock_storage, mock_settings_store, mock_validation_service):
        mock_storage.lookup = AsyncMock(return_value=None)
        first = AsyncMock()
        first.name = "first"
        first.resolve = AsyncMock(return_value=AsyncMock(
            repository_url="https://github.com/gone/repo",
        ))
        second = AsyncMock()
        second.name = "second"
        second.resolve = AsyncMock(return_value=AsyncMock(
            repository_url="https://github.com/gone2/repo",
        ))

        mock_validation_service.validate_url.return_value = _url_output(UrlValidationResult.INVALID)
        result = await PurlResolutionService(
            mock_storage, [first, second],
            settings_store=mock_settings_store,
            validation_service=mock_validation_service,
        ).resolve_purl("pkg:npm/archy@1.0.0")

        assert result.response is not None
        assert result.response.repository_url is None
        assert "No resolver found a repository URL" in result.response.warnings
        mock_storage.store.assert_not_called()

    @pytest.mark.asyncio
    async def test_uses_final_url_on_redirect(self, mock_storage, mock_settings_store, mock_validation_service):
        mock_storage.lookup = AsyncMock(return_value=None)
        resolver = AsyncMock()
        resolver.name = "test_resolver"
        resolver.resolve = AsyncMock(return_value=AsyncMock(
            repository_url="https://old-url.com/repo",
        ))

        mock_validation_service.validate_url.return_value = _url_output(
            UrlValidationResult.VALID, final_url="https://github.com/new/repo"
        )
        result = await PurlResolutionService(
            mock_storage, [resolver],
            settings_store=mock_settings_store,
            validation_service=mock_validation_service,
        ).resolve_purl("pkg:npm/archy@1.0.0")

        assert result.response is not None
        assert result.response.repository_url == "https://github.com/new/repo"
        mock_storage.store.assert_called_once()
        assert mock_storage.store.call_args[0][0].repository_url == "https://github.com/new/repo"


class TestValidationServiceDelegation:
    """Verify delegation to UrlValidationService when injected."""

    @pytest.mark.asyncio
    async def test_cached_url_delegates_to_validation_service(self, mock_storage, mock_settings_store):
        mock_storage.lookup.return_value = _cached_response(days_ago=3)
        mock_validation = AsyncMock(spec=UrlValidationService)
        mock_validation.validate_url = AsyncMock(return_value=_url_output(UrlValidationResult.VALID))

        result = await PurlResolutionService(
            mock_storage, [], settings_store=mock_settings_store,
            validation_service=mock_validation,
        ).resolve_purl("pkg:pypi/requests")

        assert result.response is not None
        mock_validation.validate_url.assert_called_once()
        mock_validation.validate_url.assert_called_with(
            "https://github.com/psf/requests",
            mock_settings_store.load().url_validation_timeout,
            github_token=mock_settings_store.load().github_token,
        )

    @pytest.mark.asyncio
    async def test_fresh_resolve_delegates_to_validation_service(self, mock_storage, mock_settings_store):
        mock_storage.lookup = AsyncMock(return_value=None)
        mock_validation = AsyncMock(spec=UrlValidationService)
        mock_validation.validate_url = AsyncMock(return_value=_url_output(UrlValidationResult.VALID))
        resolver = AsyncMock()
        resolver.name = "test_resolver"
        resolver.resolve = AsyncMock(return_value=AsyncMock(
            repository_url="https://github.com/valid/repo",
        ))

        result = await PurlResolutionService(
            mock_storage, [resolver], settings_store=mock_settings_store,
            validation_service=mock_validation,
        ).resolve_purl("pkg:npm/archy@1.0.0")

        assert result.response is not None
        assert result.response.repository_url == "https://github.com/valid/repo"
        mock_validation.validate_url.assert_called_once()
        mock_validation.validate_url.assert_called_with(
            "https://github.com/valid/repo",
            mock_settings_store.load().url_validation_timeout,
            github_token=mock_settings_store.load().github_token,
        )
