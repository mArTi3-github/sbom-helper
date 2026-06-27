from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from purl_resolver.schemas import ResolveResponse
from purl_resolver.service import PurlResolutionService
from purl_resolver.settings_store import AppSettings, SettingsStore
from purl_resolver.url_validator import UrlValidationOutput, UrlValidationResult


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
        with patch.object(PurlResolutionService, "_validate_cached_url", new_callable=AsyncMock, return_value=cached):
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
        validate_db_urls=True, url_validation_timeout=5,
        revalidation_cooldown_hours=24,
    )
    store.load = MagicMock(return_value=settings)
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
        with patch(
            "purl_resolver.service.validate_url_with_retry",
            new_callable=AsyncMock,
            return_value=_url_output(UrlValidationResult.VALID),
        ):
            result = await PurlResolutionService(mock_storage, [], settings_store=mock_settings_store).resolve_purl(
                "pkg:pypi/requests"
            )
            assert result.response is not None
            mock_storage.store.assert_called_once()
            mock_storage.delete_purls.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_url_deletes_and_falls_through(self, mock_storage, mock_settings_store, resolver):
        mock_storage.lookup.return_value = _cached_response(days_ago=3)
        with patch(
            "purl_resolver.service.validate_url_with_retry",
            new_callable=AsyncMock,
            return_value=_url_output(UrlValidationResult.INVALID),
        ):
            await PurlResolutionService(mock_storage, [resolver], settings_store=mock_settings_store).resolve_purl(
                "pkg:pypi/requests"
            )
            mock_storage.delete_purls.assert_called_once_with(["pkg:pypi/requests"])
            resolver.resolve.assert_called_once()

    @pytest.mark.asyncio
    async def test_network_error_returns_cached(self, mock_storage, mock_settings_store):
        mock_storage.lookup.return_value = _cached_response(days_ago=3)
        with patch(
            "purl_resolver.service.validate_url_with_retry",
            new_callable=AsyncMock,
            return_value=_url_output(UrlValidationResult.NETWORK_ERROR),
        ):
            result = await PurlResolutionService(mock_storage, [], settings_store=mock_settings_store).resolve_purl(
                "pkg:pypi/requests"
            )
            assert result.response is not None
            mock_storage.store.assert_not_called()
            mock_storage.delete_purls.assert_not_called()

    @pytest.mark.asyncio
    async def test_rate_limited_returns_cached(self, mock_storage, mock_settings_store):
        mock_storage.lookup.return_value = _cached_response(days_ago=3)
        with patch(
            "purl_resolver.service.validate_url_with_retry",
            new_callable=AsyncMock,
            return_value=_url_output(UrlValidationResult.RATE_LIMITED),
        ):
            result = await PurlResolutionService(mock_storage, [], settings_store=mock_settings_store).resolve_purl(
                "pkg:pypi/requests"
            )
            assert result.response is not None
            mock_storage.store.assert_not_called()

    @pytest.mark.asyncio
    async def test_validate_db_urls_false_skips_validation(self, mock_storage):
        mock_storage.lookup.return_value = _cached_response(days_ago=3)
        settings_store = MagicMock()
        settings_store.load = MagicMock(return_value=MagicMock(validate_db_urls=False))
        with patch("purl_resolver.service.validate_url_with_retry", new_callable=AsyncMock) as mock_validate:
            await PurlResolutionService(mock_storage, [], settings_store=settings_store).resolve_purl(
                "pkg:pypi/requests"
            )
            mock_validate.assert_not_called()

    @pytest.mark.asyncio
    async def test_trusted_resolver_within_cooldown_integration(self, mock_storage, mock_settings_store):
        mock_storage.lookup.return_value = ResolveResponse(
            purl="pkg:pypi/requests",
            repository_url="https://github.com/psf/requests",
            resolver="purl2repo",
            resolved_at=datetime.now().isoformat(),
        )
        with patch("purl_resolver.service.validate_url_with_retry", new_callable=AsyncMock) as mock_validate:
            await PurlResolutionService(mock_storage, [], settings_store=mock_settings_store).resolve_purl(
                "pkg:pypi/requests"
            )
            mock_validate.assert_not_called()

    @pytest.mark.asyncio
    async def test_settings_store_none_skips_validation(self, mock_storage):
        mock_storage.lookup.return_value = _cached_response(days_ago=3)
        with patch("purl_resolver.service.validate_url_with_retry", new_callable=AsyncMock) as mock_validate:
            await PurlResolutionService(mock_storage, []).resolve_purl("pkg:pypi/requests")
            mock_validate.assert_not_called()


@pytest.mark.asyncio
async def test_resolve_purl_delegates_token_to_validate_url_with_retry():
    storage = AsyncMock()
    storage.lookup = AsyncMock(return_value=_cached_response(days_ago=3))
    storage.store = AsyncMock()
    settings_store = MagicMock(spec=SettingsStore)
    settings_store.load.return_value = AppSettings(
        validate_db_urls=True,
        github_token="ghp_test123",
        revalidation_cooldown_hours=24,
    )
    with patch(
            "purl_resolver.service.validate_url_with_retry",
            new_callable=AsyncMock,
            return_value=_url_output(UrlValidationResult.VALID),
        ) as mock_validate:
        await PurlResolutionService(
            storage=storage,
            resolvers=[],
            settings_store=settings_store,
        ).resolve_purl(
            purl="pkg:pypi/requests@2.31.0",
        )
        mock_validate.assert_called()
        call_kwargs = mock_validate.call_args[1]
        assert call_kwargs.get("github_token") == "ghp_test123"


class TestValidateCachedUrl:
    @pytest.mark.asyncio
    async def test_returns_cached_when_no_settings_store(self):
        cached = ResolveResponse(
            purl="pkg:pypi/requests",
            repository_url="https://github.com/psf/requests",
        )
        service = PurlResolutionService(AsyncMock(), [])
        result = await service._validate_cached_url(cached, "pkg:pypi/requests")
        assert result == cached

    @pytest.mark.asyncio
    async def test_returns_cached_when_validation_disabled(self):
        cached = ResolveResponse(
            purl="pkg:pypi/requests",
            repository_url="https://github.com/psf/requests",
        )
        settings_store = MagicMock()
        settings_store.load.return_value = MagicMock(validate_db_urls=False)
        service = PurlResolutionService(AsyncMock(), [], settings_store=settings_store)
        result = await service._validate_cached_url(cached, "pkg:pypi/requests")
        assert result == cached

    @pytest.mark.asyncio
    async def test_returns_cached_when_resolved_today(self):
        cached = ResolveResponse(
            purl="pkg:pypi/requests",
            repository_url="https://github.com/psf/requests",
            resolver="purl2repo",
            resolved_at=datetime.now().isoformat(),
        )
        settings_store = MagicMock()
        settings_store.load.return_value = MagicMock(validate_db_urls=True, revalidation_cooldown_hours=24)
        service = PurlResolutionService(AsyncMock(), [], settings_store=settings_store)
        result = await service._validate_cached_url(cached, "pkg:pypi/requests")
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
            revalidation_cooldown_hours=24,
        )
        storage = AsyncMock()
        with patch("purl_resolver.service.validate_url_with_retry", return_value=_url_output(UrlValidationResult.VALID)):
            service = PurlResolutionService(storage, [], settings_store=settings_store)
            result = await service._validate_cached_url(cached, "pkg:pypi/requests")
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
            revalidation_cooldown_hours=24,
        )
        storage = AsyncMock()
        with patch("purl_resolver.service.validate_url_with_retry", return_value=_url_output(UrlValidationResult.INVALID)):
            service = PurlResolutionService(storage, [], settings_store=settings_store)
            result = await service._validate_cached_url(cached, "pkg:pypi/requests")
        assert result is None
        storage.delete_purls.assert_called_once_with(["pkg:pypi/requests"])

    @pytest.mark.asyncio
    async def test_delegates_token_retry_to_validate_url_with_retry(self):
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
            revalidation_cooldown_hours=24,
        )
        settings_store.load.return_value = app_settings
        storage = AsyncMock()
        with patch(
            "purl_resolver.service.validate_url_with_retry",
            new_callable=AsyncMock,
            return_value=_url_output(UrlValidationResult.VALID),
        ) as mock_validate:
            service = PurlResolutionService(storage, [], settings_store=settings_store)
            result = await service._validate_cached_url(cached, "pkg:pypi/requests")
        assert result == cached
        mock_validate.assert_called_once_with(
            cached.repository_url, 5,
            github_token="ghp_invalid",
            settings_store=settings_store,
            skip_connectivity_check=True,
        )

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
            revalidation_cooldown_hours=24,
        )
        storage = AsyncMock()
        with patch("purl_resolver.service.validate_url_with_retry", return_value=_url_output(UrlValidationResult.NETWORK_ERROR)):
            service = PurlResolutionService(storage, [], settings_store=settings_store)
            result = await service._validate_cached_url(cached, "pkg:pypi/requests")
        assert result == cached

    @pytest.mark.asyncio
    async def test_rate_limited_does_not_update_resolved_at(self):
        cached = ResolveResponse(
            purl="pkg:pypi/requests",
            repository_url="https://github.com/psf/requests",
            resolver="purl2repo",
            resolved_at="2020-01-01T00:00:00",
        )
        settings_store = MagicMock()
        settings_store.load.return_value = MagicMock(
            validate_db_urls=True,
            revalidation_cooldown_hours=24,
            github_token=None,
            url_validation_timeout=5,
        )
        storage = AsyncMock()
        with patch(
            "purl_resolver.service.validate_url_with_retry",
            return_value=_url_output(UrlValidationResult.RATE_LIMITED),
        ):
            service = PurlResolutionService(storage, [], settings_store=settings_store)
            result = await service._validate_cached_url(cached, "pkg:pypi/requests")
        assert result == cached
        storage.store.assert_not_called()
        storage.delete_purls.assert_not_called()

    @pytest.mark.asyncio
    async def test_updates_repository_url_on_redirect(self):
        cached = ResolveResponse(
            purl="pkg:pypi/requests",
            repository_url="https://old-url.com/psf/requests",
            resolved_at="2020-01-01T00:00:00",
        )
        settings_store = MagicMock()
        settings_store.load.return_value = MagicMock(
            validate_db_urls=True,
            github_token=None,
            url_validation_timeout=5,
            revalidation_cooldown_hours=24,
        )
        storage = AsyncMock()
        with patch(
            "purl_resolver.service.validate_url_with_retry",
            new_callable=AsyncMock,
            return_value=_url_output(UrlValidationResult.VALID, final_url="https://github.com/psf/requests"),
        ):
            service = PurlResolutionService(storage, [], settings_store=settings_store)
            result = await service._validate_cached_url(cached, "pkg:pypi/requests")
        assert result is not None
        assert result.repository_url == "https://github.com/psf/requests"
        storage.store.assert_called_once_with(result)

    @pytest.mark.asyncio
    async def test_preserves_url_when_no_redirect(self):
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
            revalidation_cooldown_hours=24,
        )
        storage = AsyncMock()
        with patch(
            "purl_resolver.service.validate_url_with_retry",
            new_callable=AsyncMock,
            return_value=_url_output(UrlValidationResult.VALID, final_url="https://github.com/psf/requests"),
        ):
            service = PurlResolutionService(storage, [], settings_store=settings_store)
            result = await service._validate_cached_url(cached, "pkg:pypi/requests")
        assert result is not None
        assert result.repository_url == "https://github.com/psf/requests"
        storage.store.assert_called_once_with(result)


class TestResolverBasedCooldown:
    """_validate_cached_url cooldown depends on resolver field."""

    @pytest.mark.asyncio
    async def test_trusted_resolver_within_cooldown_skips_validation(self):
        cached = ResolveResponse(
            purl="pkg:pypi/requests",
            repository_url="https://github.com/psf/requests",
            resolver="purl2repo",
            resolved_at=(datetime.now() - timedelta(hours=2)).isoformat(),
        )
        settings_store = MagicMock()
        settings_store.load.return_value = MagicMock(
            validate_db_urls=True,
            revalidation_cooldown_hours=24,
            github_token=None,
            url_validation_timeout=5,
        )
        with patch("purl_resolver.service.validate_url_with_retry") as mock_validate:
            service = PurlResolutionService(AsyncMock(), [], settings_store=settings_store)
            result = await service._validate_cached_url(cached, "pkg:pypi/requests")
        assert result == cached
        mock_validate.assert_not_called()

    @pytest.mark.asyncio
    async def test_trusted_resolver_outside_cooldown_runs_validation(self):
        cached = ResolveResponse(
            purl="pkg:pypi/requests",
            repository_url="https://github.com/psf/requests",
            resolver="purl2repo",
            resolved_at=(datetime.now() - timedelta(hours=48)).isoformat(),
        )
        settings_store = MagicMock()
        settings_store.load.return_value = MagicMock(
            validate_db_urls=True,
            revalidation_cooldown_hours=24,
            github_token=None,
            url_validation_timeout=5,
        )
        with patch(
            "purl_resolver.service.validate_url_with_retry",
            return_value=_url_output(UrlValidationResult.VALID),
        ) as mock_validate:
            service = PurlResolutionService(AsyncMock(), [], settings_store=settings_store)
            result = await service._validate_cached_url(cached, "pkg:pypi/requests")
        assert result == cached
        mock_validate.assert_called_once()

    @pytest.mark.asyncio
    async def test_untrusted_resolver_always_validates(self):
        cached = ResolveResponse(
            purl="pkg:pypi/requests",
            repository_url="https://github.com/psf/requests",
            resolver="import-sbom",
            resolved_at=(datetime.now() - timedelta(hours=1)).isoformat(),
        )
        settings_store = MagicMock()
        settings_store.load.return_value = MagicMock(
            validate_db_urls=True,
            revalidation_cooldown_hours=24,
            github_token=None,
            url_validation_timeout=5,
        )
        with patch(
            "purl_resolver.service.validate_url_with_retry",
            return_value=_url_output(UrlValidationResult.VALID),
        ) as mock_validate:
            service = PurlResolutionService(AsyncMock(), [], settings_store=settings_store)
            result = await service._validate_cached_url(cached, "pkg:pypi/requests")
        assert result == cached
        mock_validate.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_resolver_always_validates(self):
        cached = ResolveResponse(
            purl="pkg:pypi/requests",
            repository_url="https://github.com/psf/requests",
            resolver="",
            resolved_at=(datetime.now() - timedelta(hours=1)).isoformat(),
        )
        settings_store = MagicMock()
        settings_store.load.return_value = MagicMock(
            validate_db_urls=True,
            revalidation_cooldown_hours=24,
            github_token=None,
            url_validation_timeout=5,
        )
        with patch(
            "purl_resolver.service.validate_url_with_retry",
            return_value=_url_output(UrlValidationResult.VALID),
        ) as mock_validate:
            service = PurlResolutionService(AsyncMock(), [], settings_store=settings_store)
            result = await service._validate_cached_url(cached, "pkg:pypi/requests")
        assert result == cached
        mock_validate.assert_called_once()

    @pytest.mark.asyncio
    async def test_cooldown_hours_zero_disables_cooldown(self):
        cached = ResolveResponse(
            purl="pkg:pypi/requests",
            repository_url="https://github.com/psf/requests",
            resolver="purl2repo",
            resolved_at=(datetime.now() - timedelta(hours=1)).isoformat(),
        )
        settings_store = MagicMock()
        settings_store.load.return_value = MagicMock(
            validate_db_urls=True,
            revalidation_cooldown_hours=0,
            github_token=None,
            url_validation_timeout=5,
        )
        with patch(
            "purl_resolver.service.validate_url_with_retry",
            return_value=_url_output(UrlValidationResult.VALID),
        ) as mock_validate:
            service = PurlResolutionService(AsyncMock(), [], settings_store=settings_store)
            result = await service._validate_cached_url(cached, "pkg:pypi/requests")
        assert result == cached
        mock_validate.assert_called_once()


class TestFreshResolverValidation:
    """Validation of freshly resolved URLs (not cached) when validate_db_urls is enabled."""

    @pytest.mark.asyncio
    async def test_skips_invalid_fresh_url_to_next_resolver(self, mock_storage, mock_settings_store):
        first = AsyncMock()
        first.name = "first_resolver"
        first.resolve = AsyncMock(return_value=AsyncMock(
            repository_url="https://github.com/not-found/repo",
            repository_type="git",
            repository_kind="vcs",
            confidence="low",
            evidence=["ecosyste.ms:npm/archy"],
            warnings=[],
            version_reference=None,
        ))
        second = AsyncMock()
        second.name = "second_resolver"
        second.resolve = AsyncMock(return_value=AsyncMock(
            repository_url="https://github.com/valid/repo",
            repository_type="git",
            repository_kind="vcs",
            confidence="high",
            evidence=["libraries.io:npm/archy"],
            warnings=[],
            version_reference=None,
        ))
        mock_storage.lookup = AsyncMock(return_value=None)

        with patch("purl_resolver.service.validate_url_with_retry", new_callable=AsyncMock) as mock_validate:
            mock_validate.side_effect = [
                _url_output(UrlValidationResult.INVALID),
                _url_output(UrlValidationResult.VALID),
            ]
            result = await PurlResolutionService(mock_storage, [first, second], mock_settings_store).resolve_purl(
                "pkg:npm/archy@1.0.0"
            )

        assert result.response is not None
        assert result.response.repository_url == "https://github.com/valid/repo"
        assert result.response.resolver == "second_resolver"
        assert result.response.found_by == "resolver"
        mock_storage.store.assert_called_once()
        assert mock_storage.store.call_args[0][0].repository_url == "https://github.com/valid/repo"

    @pytest.mark.asyncio
    async def test_accepts_valid_fresh_url(self, mock_storage, mock_settings_store):
        mock_storage.lookup = AsyncMock(return_value=None)
        resolver = AsyncMock()
        resolver.name = "test_resolver"
        resolver.resolve = AsyncMock(return_value=AsyncMock(
            repository_url="https://github.com/valid/repo",
            repository_type="git",
            repository_kind="vcs",
            confidence="high",
            evidence=["test"],
            warnings=[],
            version_reference=None,
        ))

        with patch(
            "purl_resolver.service.validate_url_with_retry",
            new_callable=AsyncMock,
            return_value=_url_output(UrlValidationResult.VALID),
        ):
            result = await PurlResolutionService(mock_storage, [resolver], mock_settings_store).resolve_purl(
                "pkg:npm/archy@1.0.0"
            )

        assert result.response is not None
        assert result.response.repository_url == "https://github.com/valid/repo"
        mock_storage.store.assert_called_once()

    @pytest.mark.asyncio
    async def test_accepts_fresh_url_on_network_error(self, mock_storage, mock_settings_store):
        mock_storage.lookup = AsyncMock(return_value=None)
        resolver = AsyncMock()
        resolver.name = "test_resolver"
        resolver.resolve = AsyncMock(return_value=AsyncMock(
            repository_url="https://github.com/some/repo",
            repository_type="git",
            repository_kind="vcs",
            confidence="high",
            evidence=["test"],
            warnings=[],
            version_reference=None,
        ))

        with patch(
            "purl_resolver.service.validate_url_with_retry",
            new_callable=AsyncMock,
            return_value=_url_output(UrlValidationResult.NETWORK_ERROR),
        ):
            result = await PurlResolutionService(mock_storage, [resolver], mock_settings_store).resolve_purl(
                "pkg:npm/archy@1.0.0"
            )

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
            repository_type="git",
            repository_kind="vcs",
            confidence="high",
            evidence=["test"],
            warnings=[],
            version_reference=None,
        ))

        with patch("purl_resolver.service.validate_url_with_retry", new_callable=AsyncMock) as mock_validate:
            result = await PurlResolutionService(mock_storage, [resolver], settings_store).resolve_purl(
                "pkg:npm/archy@1.0.0"
            )

        assert result.response is not None
        mock_validate.assert_not_called()

    @pytest.mark.asyncio
    async def test_all_resolvers_return_invalid_returns_unresolved(self, mock_storage, mock_settings_store):
        mock_storage.lookup = AsyncMock(return_value=None)
        first = AsyncMock()
        first.name = "first"
        first.resolve = AsyncMock(return_value=AsyncMock(
            repository_url="https://github.com/gone/repo",
            repository_type="git", repository_kind="vcs",
            confidence="low", evidence=["ecosyste.ms"], warnings=[], version_reference=None,
        ))
        second = AsyncMock()
        second.name = "second"
        second.resolve = AsyncMock(return_value=AsyncMock(
            repository_url="https://github.com/gone2/repo",
            repository_type="git", repository_kind="vcs",
            confidence="low", evidence=["libraries.io"], warnings=[], version_reference=None,
        ))

        with patch(
            "purl_resolver.service.validate_url_with_retry",
            new_callable=AsyncMock,
            return_value=_url_output(UrlValidationResult.INVALID),
        ):
            result = await PurlResolutionService(mock_storage, [first, second], mock_settings_store).resolve_purl(
                "pkg:npm/archy@1.0.0"
            )

        assert result.response is not None
        assert result.response.repository_url is None
        assert "No resolver found a repository URL" in result.response.warnings
        mock_storage.store.assert_not_called()

    @pytest.mark.asyncio
    async def test_uses_final_url_on_redirect(self, mock_storage, mock_settings_store):
        mock_storage.lookup = AsyncMock(return_value=None)
        resolver = AsyncMock()
        resolver.name = "test_resolver"
        resolver.resolve = AsyncMock(return_value=AsyncMock(
            repository_url="https://old-url.com/repo",
            repository_type="git",
            repository_kind="vcs",
            confidence="high",
            evidence=["test"],
            warnings=[],
            version_reference=None,
        ))

        with patch(
            "purl_resolver.service.validate_url_with_retry",
            new_callable=AsyncMock,
            return_value=_url_output(UrlValidationResult.VALID, final_url="https://github.com/new/repo"),
        ):
            result = await PurlResolutionService(mock_storage, [resolver], mock_settings_store).resolve_purl(
                "pkg:npm/archy@1.0.0"
            )

        assert result.response is not None
        assert result.response.repository_url == "https://github.com/new/repo"
        mock_storage.store.assert_called_once()
        assert mock_storage.store.call_args[0][0].repository_url == "https://github.com/new/repo"
