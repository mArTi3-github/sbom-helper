from __future__ import annotations

from unittest.mock import patch

import pytest

from purl_resolver.config import Settings
from purl_resolver.schemas import ResolveResponse
from purl_resolver.service import resolve_purl
from purl_resolver.storage.inmemory import InMemoryCache


@pytest.fixture
def storage() -> InMemoryCache:
    return InMemoryCache()


@pytest.fixture
def settings() -> Settings:
    return Settings()


class TestImports:

    def test_asyncpg_is_importable(self) -> None:
        import asyncpg

        assert asyncpg is not None


class TestInMemoryCache:

    async def test_lookup_returns_none_for_missing(self, storage: InMemoryCache) -> None:
        result = await storage.lookup("pkg:pypi/unknown@1.0")
        assert result is None

    async def test_store_and_lookup(self, storage: InMemoryCache) -> None:
        response = ResolveResponse(
            purl="pkg:pypi/requests@2.31.0",
            repository_url="https://github.com/psf/requests",
            repository_type="github",
            repository_kind="source_code",
            confidence="high",
        )
        await storage.store(response)
        cached = await storage.lookup("pkg:pypi/requests@2.31.0")
        assert cached is not None
        assert cached.repository_url == "https://github.com/psf/requests"

    async def test_store_overwrites_existing(self, storage: InMemoryCache) -> None:
        response_old = ResolveResponse(
            purl="pkg:pypi/example@1.0",
            repository_url="https://github.com/old/example",
        )
        response_new = ResolveResponse(
            purl="pkg:pypi/example@1.0",
            repository_url="https://github.com/new/example",
        )
        await storage.store(response_old)
        await storage.store(response_new)
        cached = await storage.lookup("pkg:pypi/example@1.0")
        assert cached is not None
        assert cached.repository_url == "https://github.com/new/example"

    async def test_clear_removes_all(self, storage: InMemoryCache) -> None:
        response = ResolveResponse(
            purl="pkg:pypi/requests@2.31.0",
            repository_url="https://github.com/psf/requests",
        )
        await storage.store(response)
        storage.clear()
        assert await storage.lookup("pkg:pypi/requests@2.31.0") is None


class TestResolvePurl:

    async def test_cache_hit_returns_cached_result(
        self, storage: InMemoryCache, settings: Settings
    ) -> None:
        cached_response = ResolveResponse(
            purl="pkg:pypi/requests@2.31.0",
            repository_url="https://github.com/psf/requests",
            confidence="high",
        )
        await storage.store(cached_response)

        with patch("purl_resolver.service.purl2repo_resolve") as mock_resolve:
            result = await resolve_purl(
                "pkg:pypi/requests@2.31.0", storage, settings
            )
            mock_resolve.assert_not_called()

        assert result.error_status is None
        assert result.response is not None
        assert result.response.repository_url == "https://github.com/psf/requests"

    async def test_cache_miss_calls_resolver_and_stores(
        self, storage: InMemoryCache, settings: Settings
    ) -> None:
        from purl2repo import ResolutionResult

        fake_result = ResolutionResult(
            purl="pkg:pypi/requests@2.31.0",
            repository_url="https://github.com/psf/requests",
            repository_type="github",
            repository_kind="source_code",
            repository_candidates=[],
            canonical_repository=None,
            release_link=None,
            version_reference=None,
            confidence="high",
            evidence=["homepage from PyPI metadata"],
            warnings=[],
            metadata_sources=[],
        )

        with patch(
            "purl_resolver.service.purl2repo_resolve", return_value=fake_result
        ) as mock_resolve:
            result = await resolve_purl(
                "pkg:pypi/requests@2.31.0", storage, settings
            )

        mock_resolve.assert_called_once()
        assert result.error_status is None
        assert result.response is not None
        assert result.response.repository_url == "https://github.com/psf/requests"

        cached = await storage.lookup("pkg:pypi/requests@2.31.0")
        assert cached is not None
        assert cached.repository_url == "https://github.com/psf/requests"

    async def test_lookup_failure_falls_through(
        self, storage: InMemoryCache, settings: Settings
    ) -> None:
        from purl2repo import ResolutionResult

        broken_storage = InMemoryCache()

        async def failing_lookup(purl: str) -> None:
            msg = "Connection refused"
            raise ConnectionError(msg)

        broken_storage.lookup = failing_lookup

        fake_result = ResolutionResult(
            purl="pkg:pypi/requests@2.31.0",
            repository_url="https://github.com/psf/requests",
            repository_type="github",
            repository_kind="source_code",
            repository_candidates=[],
            canonical_repository=None,
            release_link=None,
            version_reference=None,
            confidence="high",
            evidence=[],
            warnings=[],
            metadata_sources=[],
        )

        with patch(
            "purl_resolver.service.purl2repo_resolve", return_value=fake_result
        ):
            result = await resolve_purl(
                "pkg:pypi/requests@2.31.0", broken_storage, settings
            )

        assert result.error_status is None
        assert result.response is not None
        assert result.response.repository_url == "https://github.com/psf/requests"

    async def test_store_failure_does_not_break_response(
        self, storage: InMemoryCache, settings: Settings
    ) -> None:
        from purl2repo import ResolutionResult

        broken_storage = InMemoryCache()

        async def failing_store(result: ResolveResponse) -> None:
            msg = "Disk full"
            raise OSError(msg)

        broken_storage.store = failing_store

        fake_result = ResolutionResult(
            purl="pkg:pypi/requests@2.31.0",
            repository_url="https://github.com/psf/requests",
            repository_type="github",
            repository_kind="source_code",
            repository_candidates=[],
            canonical_repository=None,
            release_link=None,
            version_reference=None,
            confidence="high",
            evidence=[],
            warnings=[],
            metadata_sources=[],
        )

        with patch(
            "purl_resolver.service.purl2repo_resolve", return_value=fake_result
        ):
            result = await resolve_purl(
                "pkg:pypi/requests@2.31.0", broken_storage, settings
            )

        assert result.error_status is None
        assert result.response is not None
        assert result.response.repository_url == "https://github.com/psf/requests"

    async def test_unresolved_purl_not_stored(
        self, storage: InMemoryCache, settings: Settings
    ) -> None:
        from purl2repo import ResolutionResult

        fake_result = ResolutionResult(
            purl="pkg:pypi/unknown@0.1",
            repository_url=None,
            repository_type=None,
            repository_kind=None,
            repository_candidates=[],
            canonical_repository=None,
            release_link=None,
            version_reference=None,
            confidence=None,
            evidence=[],
            warnings=["No repository URL found"],
            metadata_sources=[],
        )

        with patch(
            "purl_resolver.service.purl2repo_resolve", return_value=fake_result
        ):
            result = await resolve_purl(
                "pkg:pypi/unknown@0.1", storage, settings
            )

        assert result.error_status is None
        assert result.response is not None
        assert result.response.repository_url is None

        cached = await storage.lookup("pkg:pypi/unknown@0.1")
        assert cached is None

    async def test_invalid_purl_returns_error(
        self, storage: InMemoryCache, settings: Settings
    ) -> None:
        from purl2repo.errors import InvalidPurlError

        with patch(
            "purl_resolver.service.purl2repo_resolve",
            side_effect=InvalidPurlError("not a PURL"),
        ):
            result = await resolve_purl("not-a-purl", storage, settings)

        assert result.error_status == 400
        assert result.error_body == {"error": "invalid_purl", "message": "not a PURL"}
