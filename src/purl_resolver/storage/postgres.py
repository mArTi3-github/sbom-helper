from __future__ import annotations

import json
import logging

import asyncpg

from ..config import storage_settings
from ..schemas import ResolveResponse
from .interface import PurlFilters, PurlRow, UpsertRow, Storage

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
            resolver=row.get("resolver", ""),
        )

    async def store(self, result: ResolveResponse) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO resolved_purls (
                    purl, repository_url, repository_type, repository_kind,
                    confidence, evidence, warnings, version_reference, resolver
                ) VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb, $8, $9)
                ON CONFLICT (purl) DO UPDATE SET
                    repository_url = EXCLUDED.repository_url,
                    repository_type = EXCLUDED.repository_type,
                    repository_kind = EXCLUDED.repository_kind,
                    confidence = EXCLUDED.confidence,
                    evidence = EXCLUDED.evidence,
                    warnings = EXCLUDED.warnings,
                    version_reference = EXCLUDED.version_reference,
                    resolver = EXCLUDED.resolver,
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
                result.resolver or "purl2repo",
            )


    _SORTABLE_COLUMNS: frozenset[str] = frozenset({
        "purl", "repository_url", "resolver", "confidence", "resolved_at",
    })

    async def list_purls(
        self,
        offset: int,
        limit: int,
        filters: PurlFilters,
        sort_by: str = "resolved_at",
        sort_order: str = "desc",
    ) -> list[PurlRow]:
        clauses: list[str] = []
        params: list[object] = []
        idx = 1

        if filters.search is not None:
            clauses.append(f"purl ILIKE ${idx}")
            params.append(f"%{filters.search}%")
            idx += 1
        if filters.resolver is not None:
            clauses.append(f"resolver = ${idx}")
            params.append(filters.resolver)
            idx += 1
        if filters.confidence is not None:
            clauses.append(f"confidence = ${idx}")
            params.append(filters.confidence)
            idx += 1
        if filters.date_from is not None:
            clauses.append(f"resolved_at >= ${idx}")
            params.append(filters.date_from)
            idx += 1
        if filters.date_to is not None:
            clauses.append(f"resolved_at < ${idx}")
            params.append(filters.date_to)
            idx += 1

        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""

        safe_sort = sort_by if sort_by in self._SORTABLE_COLUMNS else "resolved_at"
        safe_order = "DESC" if sort_order == "desc" else "ASC"

        query = (
            f"SELECT * FROM resolved_purls{where}"
            f" ORDER BY {safe_sort} {safe_order}"
            f" LIMIT ${idx} OFFSET ${idx + 1}"
        )
        params.extend([limit, offset])

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

        return [
            PurlRow(
                purl=r["purl"],
                repository_url=r["repository_url"],
                repository_type=r.get("repository_type"),
                repository_kind=r.get("repository_kind"),
                confidence=r.get("confidence"),
                evidence=self._decode_jsonb(r.get("evidence")),
                warnings=self._decode_jsonb(r.get("warnings")),
                version_reference=r.get("version_reference"),
                resolver=r.get("resolver", "purl2repo"),
                resolved_at=str(r["resolved_at"]),
            )
            for r in rows
        ]

    async def count_purls(self, filters: PurlFilters) -> int:
        clauses: list[str] = []
        params: list[object] = []
        idx = 1

        if filters.search is not None:
            clauses.append(f"purl ILIKE ${idx}")
            params.append(f"%{filters.search}%")
            idx += 1
        if filters.resolver is not None:
            clauses.append(f"resolver = ${idx}")
            params.append(filters.resolver)
            idx += 1
        if filters.confidence is not None:
            clauses.append(f"confidence = ${idx}")
            params.append(filters.confidence)
            idx += 1
        if filters.date_from is not None:
            clauses.append(f"resolved_at >= ${idx}")
            params.append(filters.date_from)
            idx += 1
        if filters.date_to is not None:
            clauses.append(f"resolved_at < ${idx}")
            params.append(filters.date_to)
            idx += 1

        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        query = f"SELECT COUNT(*) as cnt FROM resolved_purls{where}"

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, *params)
        return row["cnt"] if row else 0

    async def update_purl(
        self, old_purl: str, purl: str, repository_url: str
    ) -> bool:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                existing = await conn.fetchrow(
                    "SELECT * FROM resolved_purls WHERE purl = $1", old_purl
                )
                if existing is None:
                    return False
                if old_purl == purl:
                    await conn.execute(
                        "UPDATE resolved_purls SET repository_url = $1, resolved_at = NOW() WHERE purl = $2",
                        repository_url, old_purl,
                    )
                else:
                    await conn.execute(
                        "DELETE FROM resolved_purls WHERE purl = $1", old_purl
                    )
                    await conn.execute(
                        """INSERT INTO resolved_purls (
                            purl, repository_url, repository_type, repository_kind,
                            confidence, evidence, warnings, version_reference, resolver
                        ) VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb, $8, $9)""",
                        purl,
                        repository_url,
                        existing.get("repository_type"),
                        existing.get("repository_kind"),
                        existing.get("confidence"),
                        json.dumps(self._decode_jsonb(existing.get("evidence"))),
                        json.dumps(self._decode_jsonb(existing.get("warnings"))),
                        existing.get("version_reference"),
                        existing.get("resolver", "purl2repo"),
                    )
                return True

    async def delete_purls(self, purls: list[str]) -> int:
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM resolved_purls WHERE purl = ANY($1::text[])",
                purls,
            )
            deleted = int(result.split()[-1]) if result else 0
            return deleted

    async def upsert_many(
        self, rows: list[UpsertRow]
    ) -> tuple[int, int]:
        upserted = 0
        errors = 0

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                for row in rows:
                    if not row.purl or not row.repository_url:
                        errors += 1
                        continue

                    await conn.execute(
                        """INSERT INTO resolved_purls (
                            purl, repository_url, repository_type, repository_kind,
                            confidence, evidence, warnings, version_reference, resolver
                        ) VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb, $8, $9)
                        ON CONFLICT (purl) DO UPDATE SET
                            repository_url = EXCLUDED.repository_url,
                            repository_type = EXCLUDED.repository_type,
                            repository_kind = EXCLUDED.repository_kind,
                            confidence = EXCLUDED.confidence,
                            evidence = EXCLUDED.evidence,
                            warnings = EXCLUDED.warnings,
                            version_reference = EXCLUDED.version_reference,
                            resolver = EXCLUDED.resolver,
                            resolved_at = NOW()""",
                        row.purl,
                        row.repository_url,
                        row.repository_type,
                        row.repository_kind,
                        row.confidence,
                        json.dumps(row.evidence),
                        json.dumps(row.warnings),
                        row.version_reference,
                        row.resolver,
                    )
                    upserted += 1

        return (upserted, errors)


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
