from __future__ import annotations

from ..schemas import ResolveResponse
from .interface import PurlFilters, PurlRow, Storage


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
            rows.append(PurlRow(
                purl=r.purl,
                repository_url=r.repository_url or "",
                repository_type=r.repository_type,
                repository_kind=r.repository_kind,
                confidence=r.confidence,
                evidence=r.evidence,
                warnings=r.warnings,
                version_reference=r.version_reference,
                resolver="purl2repo",
                resolved_at="",
            ))

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
        if filters.resolver and filters.resolver != "purl2repo":
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
        self, rows: list[dict[str, object]]
    ) -> tuple[int, int]:
        upserted = 0
        errors = 0
        for row in rows:
            purl = row.get("purl")
            repo_url = row.get("repository_url")
            if not purl or not repo_url:
                errors += 1
                continue
            purl_str = str(purl)
            evidence = row.get("evidence")
            evidence_val: list[str] = []
            if evidence is not None:
                if isinstance(evidence, list):
                    evidence_val = [str(e) for e in evidence]
                elif isinstance(evidence, str):
                    import json
                    try:
                        parsed = json.loads(evidence)
                        evidence_val = [str(e) for e in parsed] if isinstance(parsed, list) else []
                    except (json.JSONDecodeError, TypeError):
                        evidence_val = []

            warnings = row.get("warnings")
            warnings_val: list[str] = []
            if warnings is not None:
                if isinstance(warnings, list):
                    warnings_val = [str(w) for w in warnings]
                elif isinstance(warnings, str):
                    import json
                    try:
                        parsed = json.loads(warnings)
                        warnings_val = [str(w) for w in parsed] if isinstance(parsed, list) else []
                    except (json.JSONDecodeError, TypeError):
                        warnings_val = []

            self._store[purl_str] = ResolveResponse(
                purl=purl_str,
                repository_url=str(repo_url),
                repository_type=str(row["repository_type"]) if row.get("repository_type") else None,
                repository_kind=str(row["repository_kind"]) if row.get("repository_kind") else None,
                confidence=str(row["confidence"]) if row.get("confidence") else None,
                evidence=evidence_val,
                warnings=warnings_val,
                version_reference=str(row["version_reference"]) if row.get("version_reference") else None,
            )
            upserted += 1
        return (upserted, errors)

    def clear(self) -> None:
        self._store.clear()
