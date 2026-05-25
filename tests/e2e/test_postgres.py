from __future__ import annotations

import os

import asyncpg
import pytest

from purl_resolver.schemas import ResolveResponse
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
