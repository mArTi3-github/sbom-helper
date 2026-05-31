from __future__ import annotations

import os

import asyncpg
import pytest

from purl_resolver.schemas import ResolveResponse
from purl_resolver.storage.interface import PurlFilters, UpsertRow
from purl_resolver.storage.postgres import PostgresCache, _load_schema

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_E2E") == "1",
    reason="Set SKIP_E2E=1 to skip end-to-end tests (require Docker)",
)


@pytest.fixture
async def pg_pool():
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:16-alpine") as pg:
        dsn = pg.get_connection_url().replace(
            "postgresql+psycopg2://", "postgresql://"
        )
        pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=2)
        async with pool.acquire() as conn:
            await conn.execute(_load_schema())
        yield pool
        await pool.close()


@pytest.fixture
async def cache(pg_pool: asyncpg.Pool) -> PostgresCache:
    return PostgresCache(pg_pool)


class TestE2EPostgresStoreAndLookup:

    async def test_store_and_lookup_full_roundtrip(
        self, cache: PostgresCache
    ) -> None:
        response = ResolveResponse(
            purl="pkg:pypi/requests@2.31.0",
            repository_url="https://github.com/psf/requests",
            repository_type="github",
            repository_kind="source_code",
            confidence="high",
            evidence=["homepage from PyPI metadata", "validated via API"],
            warnings=["deprecated version"],
            version_reference="https://github.com/psf/requests/tree/v2.31.0",
        )

        await cache.store(response)

        cached = await cache.lookup("pkg:pypi/requests@2.31.0")
        assert cached is not None
        assert cached.purl == response.purl
        assert cached.repository_url == response.repository_url
        assert cached.repository_type == response.repository_type
        assert cached.repository_kind == response.repository_kind
        assert cached.confidence == response.confidence
        assert cached.evidence == response.evidence
        assert cached.warnings == response.warnings
        assert cached.version_reference == response.version_reference

    async def test_lookup_returns_none_for_missing(
        self, cache: PostgresCache
    ) -> None:
        result = await cache.lookup("pkg:pypi/nonexistent@1.0")
        assert result is None

    async def test_store_updates_existing_purl(
        self, cache: PostgresCache
    ) -> None:
        old = ResolveResponse(
            purl="pkg:pypi/example@1.0",
            repository_url="https://github.com/old/example",
            evidence=[],
            warnings=[],
        )
        new = ResolveResponse(
            purl="pkg:pypi/example@1.0",
            repository_url="https://github.com/new/example",
            evidence=["updated"],
            warnings=[],
        )

        await cache.store(old)
        await cache.store(new)

        result = await cache.lookup("pkg:pypi/example@1.0")
        assert result is not None
        assert result.repository_url == "https://github.com/new/example"
        assert result.evidence == ["updated"]

    async def test_store_with_empty_lists(
        self, cache: PostgresCache
    ) -> None:
        response = ResolveResponse(
            purl="pkg:pypi/empty@1.0",
            repository_url="https://github.com/empty/empty",
            repository_type="github",
            repository_kind="source_code",
            confidence="low",
            evidence=[],
            warnings=[],
            version_reference=None,
        )

        await cache.store(response)
        result = await cache.lookup("pkg:pypi/empty@1.0")
        assert result is not None
        assert result.evidence == []
        assert result.warnings == []

    async def test_store_with_nullable_fields_as_none(
        self, cache: PostgresCache
    ) -> None:
        response = ResolveResponse(
            purl="pkg:pypi/minimal@1.0",
            repository_url="https://github.com/minimal/minimal",
        )

        await cache.store(response)
        result = await cache.lookup("pkg:pypi/minimal@1.0")
        assert result is not None
        assert result.repository_url == "https://github.com/minimal/minimal"
        assert result.repository_type is None
        assert result.repository_kind is None
        assert result.confidence is None
        assert result.evidence == []
        assert result.warnings == []
        assert result.version_reference is None


async def _seed_data(cache: PostgresCache) -> None:
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
        await cache.store(e)


class TestE2EPostgresListPurls:

    @pytest.mark.asyncio
    async def test_list_all(self, cache: PostgresCache) -> None:
        await _seed_data(cache)
        rows = await cache.list_purls(0, 50, PurlFilters())
        assert len(rows) == 3
        purls = {r.purl for r in rows}
        assert purls == {"pkg:pypi/requests", "pkg:npm/express", "pkg:pypi/flask"}

    @pytest.mark.asyncio
    async def test_list_with_limit(self, cache: PostgresCache) -> None:
        await _seed_data(cache)
        rows = await cache.list_purls(0, 2, PurlFilters())
        assert len(rows) == 2

    @pytest.mark.asyncio
    async def test_list_with_offset(self, cache: PostgresCache) -> None:
        await _seed_data(cache)
        rows = await cache.list_purls(2, 10, PurlFilters())
        assert len(rows) == 1

    @pytest.mark.asyncio
    async def test_list_with_search(self, cache: PostgresCache) -> None:
        await _seed_data(cache)
        rows = await cache.list_purls(0, 50, PurlFilters(search="flask"))
        assert len(rows) == 1
        assert rows[0].purl == "pkg:pypi/flask"

    @pytest.mark.asyncio
    async def test_list_with_confidence_filter(self, cache: PostgresCache) -> None:
        await _seed_data(cache)
        rows = await cache.list_purls(0, 50, PurlFilters(confidence="high"))
        assert len(rows) == 2

    @pytest.mark.asyncio
    async def test_list_sort_by_purl_asc(self, cache: PostgresCache) -> None:
        await _seed_data(cache)
        rows = await cache.list_purls(0, 50, PurlFilters(), sort_by="purl", sort_order="asc")
        purls = [r.purl for r in rows]
        assert purls == ["pkg:npm/express", "pkg:pypi/flask", "pkg:pypi/requests"]


class TestE2EPostgresCountPurls:

    @pytest.mark.asyncio
    async def test_count_all(self, cache: PostgresCache) -> None:
        await _seed_data(cache)
        count = await cache.count_purls(PurlFilters())
        assert count == 3

    @pytest.mark.asyncio
    async def test_count_with_search(self, cache: PostgresCache) -> None:
        await _seed_data(cache)
        count = await cache.count_purls(PurlFilters(search="pypi"))
        assert count == 2

    @pytest.mark.asyncio
    async def test_count_with_confidence_filter(self, cache: PostgresCache) -> None:
        await _seed_data(cache)
        count = await cache.count_purls(PurlFilters(confidence="low"))
        assert count == 1


class TestE2EPostgresUpdatePurl:

    @pytest.mark.asyncio
    async def test_update_repository_url(self, cache: PostgresCache) -> None:
        await _seed_data(cache)
        ok = await cache.update_purl(
            "pkg:pypi/requests", "pkg:pypi/requests", "https://github.com/psf/requests-v3"
        )
        assert ok is True
        row = await cache.lookup("pkg:pypi/requests")
        assert row is not None
        assert row.repository_url == "https://github.com/psf/requests-v3"

    @pytest.mark.asyncio
    async def test_update_rekey_purl(self, cache: PostgresCache) -> None:
        await _seed_data(cache)
        ok = await cache.update_purl(
            "pkg:pypi/requests", "pkg:pypi/requests3", "https://github.com/psf/requests3"
        )
        assert ok is True
        old = await cache.lookup("pkg:pypi/requests")
        assert old is None
        new = await cache.lookup("pkg:pypi/requests3")
        assert new is not None
        assert new.repository_url == "https://github.com/psf/requests3"

    @pytest.mark.asyncio
    async def test_update_not_found(self, cache: PostgresCache) -> None:
        ok = await cache.update_purl(
            "pkg:pypi/nonexistent", "pkg:pypi/nonexistent", "https://example.com"
        )
        assert ok is False


class TestE2EPostgresDeletePurls:

    @pytest.mark.asyncio
    async def test_delete_single(self, cache: PostgresCache) -> None:
        await _seed_data(cache)
        deleted = await cache.delete_purls(["pkg:pypi/requests"])
        assert deleted == 1
        assert await cache.lookup("pkg:pypi/requests") is None

    @pytest.mark.asyncio
    async def test_delete_multiple(self, cache: PostgresCache) -> None:
        await _seed_data(cache)
        deleted = await cache.delete_purls(["pkg:pypi/requests", "pkg:npm/express"])
        assert deleted == 2
        assert await cache.lookup("pkg:pypi/requests") is None
        assert await cache.lookup("pkg:npm/express") is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, cache: PostgresCache) -> None:
        deleted = await cache.delete_purls(["pkg:pypi/nonexistent"])
        assert deleted == 0

    @pytest.mark.asyncio
    async def test_delete_empty_list(self, cache: PostgresCache) -> None:
        deleted = await cache.delete_purls([])
        assert deleted == 0


class TestE2EPostgresUpsertMany:

    @pytest.mark.asyncio
    async def test_upsert_new_rows(self, cache: PostgresCache) -> None:
        rows = [
            UpsertRow(
                purl="pkg:pypi/newpkg",
                repository_url="https://github.com/new/pkg",
                confidence="high",
            ),
        ]
        upserted, errors = await cache.upsert_many(rows)
        assert upserted == 1
        assert errors == 0
        cached = await cache.lookup("pkg:pypi/newpkg")
        assert cached is not None
        assert cached.repository_url == "https://github.com/new/pkg"

    @pytest.mark.asyncio
    async def test_upsert_overwrites_existing(self, cache: PostgresCache) -> None:
        await _seed_data(cache)
        rows = [
            UpsertRow(
                purl="pkg:pypi/requests",
                repository_url="https://github.com/psf/requests-v4",
            ),
        ]
        upserted, errors = await cache.upsert_many(rows)
        assert upserted == 1
        assert errors == 0
        cached = await cache.lookup("pkg:pypi/requests")
        assert cached is not None
        assert cached.repository_url == "https://github.com/psf/requests-v4"

    @pytest.mark.asyncio
    async def test_upsert_empty_list(self, cache: PostgresCache) -> None:
        upserted, errors = await cache.upsert_many([])
        assert upserted == 0
        assert errors == 0
