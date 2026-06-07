from __future__ import annotations

from ..schemas import ResolveResponse
from .interface import PurlFilters, PurlRow, UpsertRow, Storage


class InMemoryCache(Storage):

    def __init__(self) -> None:
        self._store: dict[str, ResolveResponse] = {}

    async def lookup(self, purl: str) -> ResolveResponse | None:
        return self._store.get(purl)

    async def store(self, result: ResolveResponse) -> None:
        self._store[result.purl] = result

    async def list_purls(
        self,
        offset: int,
        limit: int,
        filters: PurlFilters,
        sort_by: str = "resolved_at",
        sort_order: str = "desc",
    ) -> list[PurlRow]:
        rows: list[PurlRow] = []
        for key in self._store:
            r = self._store[key]
            if not self._matches_filters(r, filters):
                continue
            rows.append(PurlRow.from_response(r))

        reverse = sort_order == "desc"
        sort_keys = {
            "purl": lambda x: x.purl,
            "repository_url": lambda x: x.repository_url,
            "resolver": lambda x: x.resolver,
            "confidence": lambda x: x.confidence or "",
            "resolved_at": lambda x: x.resolved_at,
        }
        key_fn = sort_keys.get(sort_by, sort_keys["resolved_at"])
        rows.sort(key=key_fn, reverse=reverse)

        return rows[offset : offset + limit]

    def _matches_filters(
        self, r: ResolveResponse, filters: PurlFilters
    ) -> bool:
        if filters.search and filters.search.lower() not in r.purl.lower():
            return False
        if filters.resolver and filters.resolver != (r.resolver or ""):
            return False
        if filters.confidence and filters.confidence != r.confidence:
            return False
        return True

    async def count_purls(self, filters: PurlFilters) -> int:
        count = 0
        for key in self._store:
            r = self._store[key]
            if self._matches_filters(r, filters):
                count += 1
        return count

    async def update_purl(
        self, old_purl: str, purl: str, repository_url: str
    ) -> bool:
        existing = self._store.get(old_purl)
        if existing is None:
            return False
        updated = ResolveResponse(
            purl=purl,
            repository_url=repository_url,
            repository_type=existing.repository_type,
            repository_kind=existing.repository_kind,
            confidence=existing.confidence,
            evidence=existing.evidence,
            warnings=existing.warnings,
            version_reference=existing.version_reference,
        )
        if old_purl != purl:
            del self._store[old_purl]
        self._store[purl] = updated
        return True

    async def delete_purls(self, purls: list[str]) -> int:
        deleted = 0
        for p in purls:
            if p in self._store:
                del self._store[p]
                deleted += 1
        return deleted

    async def upsert_many(
        self, rows: list[UpsertRow]
    ) -> tuple[int, int]:
        upserted = 0
        errors = 0
        for row in rows:
            if not row.purl or not row.repository_url:
                errors += 1
                continue
            self._store[row.purl] = ResolveResponse(
                purl=row.purl,
                repository_url=row.repository_url,
                repository_type=row.repository_type,
                repository_kind=row.repository_kind,
                confidence=row.confidence,
                evidence=row.evidence,
                warnings=row.warnings,
                version_reference=row.version_reference,
            )
            upserted += 1
        return (upserted, errors)

    def clear(self) -> None:
        self._store.clear()
