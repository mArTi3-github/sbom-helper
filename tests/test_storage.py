from __future__ import annotations

import pytest

from purl_resolver.resolver.interface import InvalidPurlError, Resolution
from purl_resolver.schemas import ResolveResponse
from purl_resolver.service import PurlResolutionService
from purl_resolver.storage.inmemory import InMemoryCache
from tests.helpers import FakeResolver


@pytest.fixture
def storage() -> InMemoryCache:
    return InMemoryCache()


class TestInMemoryCache:

    @pytest.mark.asyncio
    async def test_lookup_returns_none_for_missing(self, storage: InMemoryCache) -> None:
        result = await storage.lookup("pkg:pypi/unknown@1.0")
        assert result is None

    @pytest.mark.asyncio
    async def test_store_and_lookup(self, storage: InMemoryCache) -> None:
        response = ResolveResponse(
            purl="pkg:pypi/requests",
            repository_url="https://github.com/psf/requests",
        )
        await storage.store(response)
        cached = await storage.lookup("pkg:pypi/requests")
        assert cached is not None
        assert cached.repository_url == "https://github.com/psf/requests"

    @pytest.mark.asyncio
    async def test_store_overwrites_existing(self, storage: InMemoryCache) -> None:
        response_old = ResolveResponse(
            purl="pkg:pypi/example",
            repository_url="https://github.com/old/example",
        )
        response_new = ResolveResponse(
            purl="pkg:pypi/example",
            repository_url="https://github.com/new/example",
        )
        await storage.store(response_old)
        await storage.store(response_new)
        cached = await storage.lookup("pkg:pypi/example")
        assert cached is not None
        assert cached.repository_url == "https://github.com/new/example"

    @pytest.mark.asyncio
    async def test_list_resolvers(self, storage: InMemoryCache) -> None:
        r1 = ResolveResponse(purl="pkg:pypi/a", repository_url="https://example.com/a", resolver="purl2repo")
        r2 = ResolveResponse(purl="pkg:pypi/b", repository_url="https://example.com/b", resolver="import-csv")
        r3 = ResolveResponse(purl="pkg:pypi/c", repository_url="https://example.com/c", resolver="purl2repo")
        await storage.store(r1)
        await storage.store(r2)
        await storage.store(r3)
        result = await storage.list_resolvers()
        assert result == ["import-csv", "purl2repo"]

    @pytest.mark.asyncio
    async def test_list_resolvers_empty(self, storage: InMemoryCache) -> None:
        result = await storage.list_resolvers()
        assert result == []

    @pytest.mark.asyncio
    async def test_clear_removes_all(self, storage: InMemoryCache) -> None:
        response = ResolveResponse(
            purl="pkg:pypi/requests",
            repository_url="https://github.com/psf/requests",
        )
        await storage.store(response)
        storage.clear()
        assert await storage.lookup("pkg:pypi/requests") is None


class TestResolvePurl:

    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached_result(self, storage: InMemoryCache) -> None:
        cached_response = ResolveResponse(
            purl="pkg:pypi/requests",
            repository_url="https://github.com/psf/requests",
        )
        await storage.store(cached_response)

        resolver = FakeResolver()
        result = await PurlResolutionService(storage, [resolver]).resolve_purl(
            "pkg:pypi/requests@2.31.0"
        )

        assert resolver.call_count == 0
        assert result.error_status is None
        assert result.response is not None
        assert result.response.repository_url == "https://github.com/psf/requests"
        assert result.response.purl == "pkg:pypi/requests"

    @pytest.mark.asyncio
    async def test_cache_hit_with_different_version(self, storage: InMemoryCache) -> None:
        cached_response = ResolveResponse(
            purl="pkg:pypi/requests",
            repository_url="https://github.com/psf/requests",
        )
        await storage.store(cached_response)

        resolver = FakeResolver()
        result = await PurlResolutionService(storage, [resolver]).resolve_purl(
            "pkg:pypi/requests@3.0.0"
        )

        assert resolver.call_count == 0
        assert result.error_status is None
        assert result.response is not None
        assert result.response.repository_url == "https://github.com/psf/requests"

    @pytest.mark.asyncio
    async def test_cache_miss_calls_resolver_and_stores(self, storage: InMemoryCache) -> None:
        resolver = FakeResolver(
            resolution=Resolution(
                purl="pkg:pypi/requests@2.31.0",
                repository_url="https://github.com/psf/requests",
            )
        )

        result = await PurlResolutionService(storage, [resolver]).resolve_purl(
            "pkg:pypi/requests@2.31.0"
        )

        assert resolver.call_count == 1
        assert result.error_status is None
        assert result.response is not None
        assert result.response.repository_url == "https://github.com/psf/requests"
        assert result.response.purl == "pkg:pypi/requests"

        cached = await storage.lookup("pkg:pypi/requests")
        assert cached is not None
        assert cached.repository_url == "https://github.com/psf/requests"

    @pytest.mark.asyncio
    async def test_lookup_failure_falls_through(self, storage: InMemoryCache) -> None:
        broken_storage = InMemoryCache()

        async def failing_lookup(purl: str) -> None:
            msg = "Connection refused"
            raise ConnectionError(msg)

        broken_storage.lookup = failing_lookup

        resolver = FakeResolver(
            resolution=Resolution(
                purl="pkg:pypi/requests@2.31.0",
                repository_url="https://github.com/psf/requests",
            )
        )

        result = await PurlResolutionService(broken_storage, [resolver]).resolve_purl(
            "pkg:pypi/requests@2.31.0"
        )

        assert result.error_status is None
        assert result.response is not None
        assert result.response.repository_url == "https://github.com/psf/requests"

    @pytest.mark.asyncio
    async def test_store_failure_does_not_break_response(self, storage: InMemoryCache) -> None:
        broken_storage = InMemoryCache()

        async def failing_store(result: ResolveResponse) -> None:
            msg = "Disk full"
            raise OSError(msg)

        broken_storage.store = failing_store

        resolver = FakeResolver(
            resolution=Resolution(
                purl="pkg:pypi/requests@2.31.0",
                repository_url="https://github.com/psf/requests",
            )
        )

        result = await PurlResolutionService(broken_storage, [resolver]).resolve_purl(
            "pkg:pypi/requests@2.31.0"
        )

        assert result.error_status is None
        assert result.response is not None
        assert result.response.repository_url == "https://github.com/psf/requests"

    @pytest.mark.asyncio
    async def test_unresolved_purl_not_stored(self, storage: InMemoryCache) -> None:
        resolver = FakeResolver(
            resolution=Resolution(
                purl="pkg:pypi/unknown@0.1",
                warnings=["No repository URL found"],
            )
        )

        result = await PurlResolutionService(storage, [resolver]).resolve_purl(
            "pkg:pypi/unknown@0.1"
        )

        assert result.error_status is None
        assert result.response is not None
        assert result.response.repository_url is None

        cached = await storage.lookup("pkg:pypi/unknown@0.1")
        assert cached is None

    @pytest.mark.asyncio
    async def test_invalid_purl_returns_error_from_validation(self, storage: InMemoryCache) -> None:
        resolver = FakeResolver()
        result = await PurlResolutionService(storage, [resolver]).resolve_purl(
            "not-a-purl"
        )

        assert resolver.call_count == 0
        assert result.error_status == 400
        assert result.error_body is not None
        assert result.error_body["error"] == "invalid_purl"
        assert isinstance(result.error_body["detail"], str)

    @pytest.mark.asyncio
    async def test_invalid_purl_from_resolver_still_works(self, storage: InMemoryCache) -> None:
        resolver = FakeResolver(error=InvalidPurlError("unsupported ecosystem"))
        result = await PurlResolutionService(storage, [resolver]).resolve_purl(
            "pkg:pypi/somepackage@1.0"
        )

        assert resolver.call_count == 1
        assert result.error_status == 400
        assert result.error_body == {"error": "invalid_purl", "detail": "unsupported ecosystem"}

    @pytest.mark.asyncio
    async def test_all_resolvers_fail_returns_unresolved(self, storage: InMemoryCache) -> None:
        resolver_a = FakeResolver(
            resolution=Resolution(purl="pkg:pypi/missing@1.0")
        )
        resolver_b = FakeResolver(
            resolution=Resolution(purl="pkg:pypi/missing@1.0")
        )

        result = await PurlResolutionService(storage, [resolver_a, resolver_b]).resolve_purl(
            "pkg:pypi/missing@1.0"
        )

        assert result.error_status is None
        assert result.response is not None
        assert result.response.repository_url is None

    @pytest.mark.asyncio
    async def test_second_resolver_used_when_first_returns_null(
        self, storage: InMemoryCache
    ) -> None:
        resolver_a = FakeResolver(
            resolution=Resolution(purl="pkg:pypi/pkg@1.0")
        )
        resolver_b = FakeResolver(
            resolution=Resolution(
                purl="pkg:pypi/pkg@1.0",
                repository_url="https://github.com/second/pkg",
            )
        )

        result = await PurlResolutionService(storage, [resolver_a, resolver_b]).resolve_purl(
            "pkg:pypi/pkg@1.0"
        )

        assert resolver_a.call_count == 1
        assert resolver_b.call_count == 1
        assert result.error_status is None
        assert result.response is not None
        assert result.response.repository_url == "https://github.com/second/pkg"
