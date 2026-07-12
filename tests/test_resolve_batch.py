from __future__ import annotations

import pytest

from purl_resolver.resolver.interface import Resolution
from purl_resolver.service import PurlResolutionService
from purl_resolver.storage.inmemory import InMemoryCache
from tests.helpers import FakeResolver


@pytest.fixture
def storage() -> InMemoryCache:
    return InMemoryCache()


class TestResolveBatch:

    @pytest.mark.asyncio
    async def test_resolves_multiple_purls(self, storage: InMemoryCache) -> None:
        resolver = FakeResolver(
            resolution=Resolution(
                purl="pkg:pypi/requests@2.31.0",
                repository_url="https://github.com/psf/requests",
            )
        )
        purls = [
            "pkg:pypi/requests@2.31.0",
            "pkg:npm/express@4.17.1",
            "pkg:pypi/flask@3.0.0",
        ]
        result = await PurlResolutionService(storage, [resolver]).resolve_batch(purls)
        assert len(result) == 3
        for key, resp in result.items():
            assert resp.repository_url == "https://github.com/psf/requests"

    @pytest.mark.asyncio
    async def test_skips_purls_with_no_repository_url(self, storage: InMemoryCache) -> None:
        resolver = FakeResolver(
            resolution=Resolution(
                purl="pkg:pypi/requests@2.31.0",
                repository_url=None,
            )
        )
        purls = ["pkg:pypi/requests@2.31.0"]
        result = await PurlResolutionService(storage, [resolver]).resolve_batch(purls)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_uses_normalized_keys(self, storage: InMemoryCache) -> None:
        resolver = FakeResolver(
            resolution=Resolution(
                purl="pkg:pypi/requests@2.31.0",
                repository_url="https://github.com/psf/requests",
            )
        )
        purls = ["pkg:pypi/requests@2.31.0", "pkg:pypi/requests@3.0.0"]
        result = await PurlResolutionService(storage, [resolver]).resolve_batch(purls)
        assert len(result) == 1
        assert "pkg:pypi/requests" in result

    @pytest.mark.asyncio
    async def test_empty_purl_list(self, storage: InMemoryCache) -> None:
        resolver = FakeResolver()
        result = await PurlResolutionService(storage, [resolver]).resolve_batch([])
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_stores_resolved_results_in_storage(self, storage: InMemoryCache) -> None:
        resolver = FakeResolver(
            resolution=Resolution(
                purl="pkg:pypi/requests@2.31.0",
                repository_url="https://github.com/psf/requests",
            )
        )
        purls = ["pkg:pypi/requests@2.31.0"]
        await PurlResolutionService(storage, [resolver]).resolve_batch(purls)
        cached = await storage.lookup("pkg:pypi/requests")
        assert cached is not None
        assert cached.repository_url == "https://github.com/psf/requests"

    @pytest.mark.asyncio
    async def test_resolved_entries_have_found_by_and_resolver(self, storage: InMemoryCache) -> None:
        resolver = FakeResolver(
            resolution=Resolution(
                purl="pkg:pypi/requests@2.31.0",
                repository_url="https://github.com/psf/requests",
            )
        )
        purls = ["pkg:pypi/requests@2.31.0"]
        result = await PurlResolutionService(storage, [resolver]).resolve_batch(purls)
        assert len(result) == 1
        resp = result["pkg:pypi/requests"]
        assert resp.found_by == "resolver"
        assert resp.resolver == "fake"
