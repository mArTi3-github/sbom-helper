from __future__ import annotations

import json
import logging

import asyncpg

from ..config import storage_settings
from ..schemas import ResolveResponse
from .interface import Storage

logger = logging.getLogger(__name__)

CREATE_TABLE_SQL: str | None = None


def _load_schema() -> str:
    global CREATE_TABLE_SQL
    if CREATE_TABLE_SQL is None:
        import pathlib

        path = pathlib.Path(__file__).parent / "schema.sql"
        CREATE_TABLE_SQL = path.read_text()
    return CREATE_TABLE_SQL


class PostgresCache(Storage):

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @staticmethod
    def _decode_jsonb(val: object) -> list[str]:
        if val is None:
            return []
        if isinstance(val, str):
            return json.loads(val)
        if isinstance(val, list):
            return val
        return []

    async def lookup(self, purl: str) -> ResolveResponse | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM resolved_purls WHERE purl = $1", purl
            )
        if row is None:
            return None
        return ResolveResponse(
            purl=row["purl"],
            repository_url=row["repository_url"],
            repository_type=row.get("repository_type"),
            repository_kind=row.get("repository_kind"),
            confidence=row.get("confidence"),
            evidence=self._decode_jsonb(row.get("evidence")),
            warnings=self._decode_jsonb(row.get("warnings")),
            version_reference=row.get("version_reference"),
        )

    async def store(self, result: ResolveResponse) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO resolved_purls (
                    purl, repository_url, repository_type, repository_kind,
                    confidence, evidence, warnings, version_reference
                ) VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb, $8)
                ON CONFLICT (purl) DO UPDATE SET
                    repository_url = EXCLUDED.repository_url,
                    repository_type = EXCLUDED.repository_type,
                    repository_kind = EXCLUDED.repository_kind,
                    confidence = EXCLUDED.confidence,
                    evidence = EXCLUDED.evidence,
                    warnings = EXCLUDED.warnings,
                    version_reference = EXCLUDED.version_reference,
                    resolved_at = NOW()
                """,
                result.purl,
                result.repository_url,
                result.repository_type,
                result.repository_kind,
                result.confidence,
                result.evidence
    if isinstance(result.evidence, str)
    else json.dumps(result.evidence),
    result.warnings
    if isinstance(result.warnings, str)
    else json.dumps(result.warnings),
                result.version_reference,
            )


async def create_pool() -> asyncpg.Pool:
    pool = await asyncpg.create_pool(
        dsn=storage_settings.url,
        min_size=storage_settings.pool_min_size,
        max_size=storage_settings.pool_max_size,
    )
    async with pool.acquire() as conn:
        await conn.execute(_load_schema())
        logger.info("Table 'resolved_purls' ensured")
    return pool
