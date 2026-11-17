from __future__ import annotations

from datetime import datetime

import asyncpg

from .source_archive import SourceArchiveRow, SourceArchiveStorage


def _iso(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    text = str(value)
    try:
        return datetime.fromisoformat(text).isoformat()
    except ValueError:
        return text


class PostgresSourceArchiveStorage(SourceArchiveStorage):

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def lookup_archive(self, purl: str) -> SourceArchiveRow | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM purl_source_archives WHERE purl = $1", purl
            )
        if row is None:
            return None
        return SourceArchiveRow(
            purl=row["purl"],
            version=row["version"],
            match_type=row["match_type"],
            reason=row["reason"],
            archive_url=row["archive_url"],
            archive_url_commit=row["archive_url_commit"],
            matched_ref=row["matched_ref"],
            matched_ref_type=row["matched_ref_type"],
            matched_version=row["matched_version"],
            repository_url=row["repository_url"],
            resolver=row["resolver"],
            resolved_at=_iso(row["resolved_at"]),
        )

    async def store_archive(self, row: SourceArchiveRow) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO purl_source_archives (
                    purl, version, match_type, reason, archive_url,
                    archive_url_commit, matched_ref, matched_ref_type,
                    matched_version, repository_url, resolver
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                ON CONFLICT (purl) DO UPDATE SET
                    version = EXCLUDED.version,
                    match_type = EXCLUDED.match_type,
                    reason = EXCLUDED.reason,
                    archive_url = EXCLUDED.archive_url,
                    archive_url_commit = EXCLUDED.archive_url_commit,
                    matched_ref = EXCLUDED.matched_ref,
                    matched_ref_type = EXCLUDED.matched_ref_type,
                    matched_version = EXCLUDED.matched_version,
                    repository_url = EXCLUDED.repository_url,
                    resolver = EXCLUDED.resolver,
                    resolved_at = EXCLUDED.resolved_at
                """,
                row.purl,
                row.version,
                row.match_type,
                row.reason,
                row.archive_url,
                row.archive_url_commit,
                row.matched_ref,
                row.matched_ref_type,
                row.matched_version,
                row.repository_url,
                row.resolver,
            )
