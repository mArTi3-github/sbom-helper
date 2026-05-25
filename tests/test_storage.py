from __future__ import annotations

import pytest

from purl_resolver.resolver.interface import InvalidPurlError, Resolution, Resolver
from purl_resolver.schemas import ResolveResponse
from purl_resolver.service import resolve_purl
from purl_resolver.storage.inmemory import InMemoryCache


class _FakeResolver(Resolver):

    def __init__(
        self, resolution: Resolution | None = None, error: Exception | None = None
    ) -> None:
        self._resolution = resolution
        self._error = error
        self.call_count = 0

    def resolve(self, purl: str) -> Resolution:
        self.call_count += 1
        if self._error:
            raise self._error
        if self._resolution:
            return self._resolution
        return Resolution(purl=purl)


@pytest.fixture
def storage() -> InMemoryCache:
    return InMemoryCache()


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

    async def test_cache_hit_returns_cached_result(self, storage: InMemoryCache) -> None:
        cached_response = ResolveResponse(
            purl="pkg:pypi/requests@2.31.0",
            repository_url="https://github.com/psf/requests",
            confidence="high",
        )
        await storage.store(cached_response)

        resolver = _FakeResolver()
        result = await resolve_purl(
            "pkg:pypi/requests@2.31.0", storage, [resolver]
        )

        assert resolver.call_count == 0
        assert result.error_status is None
        assert result.response is not None
        assert result.response.repository_url == "https://github.com/psf/requests"

    async def test_cache_miss_calls_resolver_and_stores(self, storage: InMemoryCache) -> None:
        resolver = _FakeResolver(
            resolution=Resolution(
                purl="pkg:pypi/requests@2.31.0",
                repository_url="https://github.com/psf/requests",
                repository_type="github",
                repository_kind="source_code",
                confidence="high",
                evidence=["homepage from PyPI metadata"],
            )
        )

        result = await resolve_purl(
            "pkg:pypi/requests@2.31.0", storage, [resolver]
        )

        assert resolver.call_count == 1
        assert result.error_status is None
        assert result.response is not None
        assert result.response.repository_url == "https://github.com/psf/requests"

        cached = await storage.lookup("pkg:pypi/requests@2.31.0")
        assert cached is not None
        assert cached.repository_url == "https://github.com/psf/requests"

    async def test_lookup_failure_falls_through(self, storage: InMemoryCache) -> None:
        broken_storage = InMemoryCache()

        async def failing_lookup(purl: str) -> None:
            msg = "Connection refused"
            raise ConnectionError(msg)

        broken_storage.lookup = failing_lookup

        resolver = _FakeResolver(
            resolution=Resolution(
                purl="pkg:pypi/requests@2.31.0",
                repository_url="https://github.com/psf/requests",
                repository_type="github",
                repository_kind="source_code",
                confidence="high",
            )
        )

        result = await resolve_purl(
            "pkg:pypi/requests@2.31.0", broken_storage, [resolver]
        )

        assert result.error_status is None
        assert result.response is not None
        assert result.response.repository_url == "https://github.com/psf/requests"

    async def test_store_failure_does_not_break_response(self, storage: InMemoryCache) -> None:
        broken_storage = InMemoryCache()

        async def failing_store(result: ResolveResponse) -> None:
            msg = "Disk full"
            raise OSError(msg)

        broken_storage.store = failing_store

        resolver = _FakeResolver(
            resolution=Resolution(
                purl="pkg:pypi/requests@2.31.0",
                repository_url="https://github.com/psf/requests",
                repository_type="github",
                repository_kind="source_code",
                confidence="high",
            )
        )

        result = await resolve_purl(
            "pkg:pypi/requests@2.31.0", broken_storage, [resolver]
        )

        assert result.error_status is None
        assert result.response is not None
        assert result.response.repository_url == "https://github.com/psf/requests"

    async def test_unresolved_purl_not_stored(self, storage: InMemoryCache) -> None:
        resolver = _FakeResolver(
            resolution=Resolution(
                purl="pkg:pypi/unknown@0.1",
                warnings=["No repository URL found"],
            )
        )

        result = await resolve_purl(
            "pkg:pypi/unknown@0.1", storage, [resolver]
        )

        assert result.error_status is None
        assert result.response is not None
        assert result.response.repository_url is None

        cached = await storage.lookup("pkg:pypi/unknown@0.1")
        assert cached is None

    async def test_invalid_purl_returns_error(self, storage: InMemoryCache) -> None:
        resolver = _FakeResolver(error=InvalidPurlError("not a PURL"))

        result = await resolve_purl(
            "not-a-purl", storage, [resolver]
        )

        assert result.error_status == 400
        assert result.error_body == {"error": "invalid_purl", "message": "not a PURL"}

    async def test_all_resolvers_fail_returns_unresolved(self, storage: InMemoryCache) -> None:
        resolver_a = _FakeResolver(
            resolution=Resolution(purl="pkg:pypi/missing@1.0")
        )
        resolver_b = _FakeResolver(
            resolution=Resolution(purl="pkg:pypi/missing@1.0")
        )

        result = await resolve_purl(
            "pkg:pypi/missing@1.0", storage, [resolver_a, resolver_b]
        )

        assert result.error_status is None
        assert result.response is not None
        assert result.response.repository_url is None

    async def test_second_resolver_used_when_first_returns_null(
        self, storage: InMemoryCache
    ) -> None:
        resolver_a = _FakeResolver(
            resolution=Resolution(purl="pkg:pypi/pkg@1.0")
        )
        resolver_b = _FakeResolver(
            resolution=Resolution(
                purl="pkg:pypi/pkg@1.0",
                repository_url="https://github.com/second/pkg",
            )
        )

        result = await resolve_purl(
            "pkg:pypi/pkg@1.0", storage, [resolver_a, resolver_b]
        )

        assert resolver_a.call_count == 1
        assert resolver_b.call_count == 1
        assert result.error_status is None
        assert result.response is not None
        assert result.response.repository_url == "https://github.com/second/pkg"
