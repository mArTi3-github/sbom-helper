from __future__ import annotations

import logging

from .csv_io import parse_csv_import, render_csv_export
from .schemas import (
    ImportErrorItem,
    ImportResponse,
    ImportStrategy,
    PurlListParams,
    PurlListResponse,
    PurlUpdateRequest,
)
from .storage.interface import PurlFilters, Storage

logger = logging.getLogger(__name__)


class DbAdminError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class DbAdminService:

    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    async def list_purls(self, params: PurlListParams) -> PurlListResponse:
        filters = PurlFilters(
            search=params.search,
            resolver=params.resolver,
            confidence=params.confidence,
            date_from=params.date_from,
            date_to=params.date_to,
        )
        total = await self._storage.count_purls(filters)
        offset = (params.page - 1) * params.page_size
        rows = await self._storage.list_purls(
            offset=offset,
            limit=params.page_size,
            filters=filters,
            sort_by=params.sort_by,
            sort_order=params.sort_order,
        )
        row_responses = [r.to_resolve_response() for r in rows]
        return PurlListResponse(
            rows=row_responses,
            total=total,
            page=params.page,
            page_size=params.page_size,
        )

    async def update_purl(self, purl: str, body: PurlUpdateRequest) -> tuple[bool, str | None]:
        new_purl = body.purl if body.purl is not None else purl
        new_repo = body.repository_url if body.repository_url is not None else ""

        existing = await self._storage.lookup(purl)
        if new_repo == "" and existing is not None:
            new_repo = existing.repository_url or ""

        if new_repo == "":
            return False, "repository_url is required for new rows"

        ok = await self._storage.update_purl(purl, new_purl, new_repo)
        if not ok:
            return False, "PURL not found"
        return True, None

    async def delete_purls(self, purls: list[str]) -> int:
        return await self._storage.delete_purls(purls)

    async def import_csv(self, text: str, strategy: ImportStrategy) -> ImportResponse:
        rows, errors = parse_csv_import(text)
        if not rows and errors:
            raise DbAdminError(errors[0]["error"], status_code=400)

        if strategy == ImportStrategy.skip_existing:
            to_insert = []
            skipped = 0
            for row in rows:
                existing = await self._storage.lookup(row.purl)
                if existing is not None:
                    skipped += 1
                else:
                    to_insert.append(row)
            upserted, _ = await self._storage.upsert_many(to_insert)
            return ImportResponse(
                imported=upserted,
                skipped=skipped,
                errors=[ImportErrorItem(row=e["row"], error=str(e["error"])) for e in errors],
            )

        upserted, _ = await self._storage.upsert_many(rows)
        return ImportResponse(
            imported=upserted,
            skipped=0,
            errors=[ImportErrorItem(row=e["row"], error=str(e["error"])) for e in errors],
        )

    async def export_selected_csv(self, purls: list[str]) -> str:
        rows = []
        for purl in purls:
            row = await self._storage.lookup(purl)
            if row is not None:
                rows.append(row)
        return render_csv_export(rows)
