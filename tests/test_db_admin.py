from __future__ import annotations

import pytest
from datetime import date

from purl_resolver.storage.inmemory import InMemoryCache
from purl_resolver.storage.interface import PurlFilters, PurlRow
from purl_resolver.schemas import ResolveResponse


@pytest.fixture
def storage():
    return InMemoryCache()


@pytest.fixture
def populated_storage(storage):
    entries = [
        ResolveResponse(
            purl="pkg:pypi/requests",
            repository_url="https://github.com/psf/requests",
            repository_type="github",
            repository_kind="source_code",
            confidence="high",
            evidence=["homepage from PyPI"],
            warnings=[],
        ),
        ResolveResponse(
            purl="pkg:npm/express",
            repository_url="https://github.com/expressjs/express",
            repository_type="github",
            repository_kind="source_code",
            confidence="low",
            evidence=[],
            warnings=["registry mismatch"],
        ),
        ResolveResponse(
            purl="pkg:pypi/flask",
            repository_url="https://github.com/pallets/flask",
            repository_type="github",
            repository_kind="source_code",
            confidence="high",
            evidence=["homepage from PyPI"],
            warnings=[],
        ),
    ]
    for e in entries:
        storage._store[e.purl] = e
    return storage


class TestInMemoryCacheList:
    async def test_list_all_returns_all(self, populated_storage):
        rows = await populated_storage.list_purls(0, 50, PurlFilters())
        assert len(rows) == 3
        purls = {r.purl for r in rows}
        assert purls == {"pkg:pypi/requests", "pkg:npm/express", "pkg:pypi/flask"}

    async def test_list_with_limit(self, populated_storage):
        rows = await populated_storage.list_purls(0, 2, PurlFilters())
        assert len(rows) == 2

    async def test_list_with_offset(self, populated_storage):
        rows = await populated_storage.list_purls(2, 10, PurlFilters())
        assert len(rows) == 1

    async def test_list_with_search(self, populated_storage):
        rows = await populated_storage.list_purls(0, 50, PurlFilters(search="flask"))
        assert len(rows) == 1
        assert rows[0].purl == "pkg:pypi/flask"

    async def test_list_with_resolver_filter(self, populated_storage):
        rows = await populated_storage.list_purls(0, 50, PurlFilters(resolver="purl2repo"))
        assert len(rows) == 3

    async def test_list_with_confidence_filter(self, populated_storage):
        rows = await populated_storage.list_purls(0, 50, PurlFilters(confidence="high"))
        assert len(rows) == 2

    async def test_list_with_confidence_filter_no_match(self, populated_storage):
        rows = await populated_storage.list_purls(0, 50, PurlFilters(confidence="medium"))
        assert len(rows) == 0

    async def test_list_sort_by_purl_asc(self, populated_storage):
        rows = await populated_storage.list_purls(0, 50, PurlFilters(), sort_by="purl", sort_order="asc")
        purls = [r.purl for r in rows]
        assert purls == ["pkg:npm/express", "pkg:pypi/flask", "pkg:pypi/requests"]

    async def test_list_sort_by_confidence_desc(self, populated_storage):
        rows = await populated_storage.list_purls(0, 50, PurlFilters(), sort_by="confidence", sort_order="desc")
        assert rows[0].confidence == "low"


class TestInMemoryCacheCount:
    async def test_count_all(self, populated_storage):
        count = await populated_storage.count_purls(PurlFilters())
        assert count == 3

    async def test_count_with_search(self, populated_storage):
        count = await populated_storage.count_purls(PurlFilters(search="pypi"))
        assert count == 2


class TestInMemoryCacheUpdate:
    async def test_update_repository_url(self, populated_storage):
        ok = await populated_storage.update_purl(
            "pkg:pypi/requests", "pkg:pypi/requests", "https://github.com/psf/requests3"
        )
        assert ok is True
        row = await populated_storage.lookup("pkg:pypi/requests")
        assert row.repository_url == "https://github.com/psf/requests3"

    async def test_update_rekey_purl(self, populated_storage):
        ok = await populated_storage.update_purl(
            "pkg:pypi/requests", "pkg:pypi/requests3", "https://github.com/psf/requests3"
        )
        assert ok is True
        old = await populated_storage.lookup("pkg:pypi/requests")
        assert old is None
        new = await populated_storage.lookup("pkg:pypi/requests3")
        assert new is not None
        assert new.repository_url == "https://github.com/psf/requests3"

    async def test_update_not_found(self, populated_storage):
        ok = await populated_storage.update_purl(
            "pkg:pypi/nonexistent", "pkg:pypi/nonexistent", "https://example.com"
        )
        assert ok is False
