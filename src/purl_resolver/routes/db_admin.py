from __future__ import annotations

from datetime import date

from fastapi import APIRouter, File, Form, Query, Request, UploadFile
from fastapi.responses import JSONResponse, Response

from ..schemas import (
    DeleteResponse,
    ImportErrorItem,
    ImportResponse,
    ImportStrategy,
    PurlDeleteRequest,
    PurlListParams,
    PurlListResponse,
    PurlUpdateRequest,
)
from ..csv_io import parse_csv_import, render_csv_export
from ..storage.interface import PurlFilters

router = APIRouter()


@router.get("/api/v1/db/purls")
async def list_purls_endpoint(request: Request, params: PurlListParams = Query()):
    storage = request.app.state.storage
    filters = PurlFilters(
        search=params.search,
        resolver=params.resolver,
        confidence=params.confidence,
        date_from=params.date_from,
        date_to=params.date_to,
    )
    total = await storage.count_purls(filters)
    offset = (params.page - 1) * params.page_size
    rows = await storage.list_purls(
        offset=offset,
        limit=params.page_size,
        filters=filters,
        sort_by=params.sort_by,
        sort_order=params.sort_order,
    )
    row_responses = [r.to_resolve_response() for r in rows]
    return JSONResponse(
        status_code=200,
        content=PurlListResponse(
            rows=row_responses,
            total=total,
            page=params.page,
            page_size=params.page_size,
        ).model_dump(),
    )


@router.patch("/api/v1/db/purls/{purl:path}")
async def update_purl_endpoint(
    purl: str, body: PurlUpdateRequest, request: Request
):
    new_purl = body.purl if body.purl is not None else purl
    new_repo = body.repository_url if body.repository_url is not None else ""
    storage = request.app.state.storage

    existing = await storage.lookup(purl)
    if new_repo == "" and existing is not None:
        new_repo = existing.repository_url or ""

    if new_repo == "":
        return JSONResponse(
            status_code=400,
            content={"error": "invalid_update", "message": "repository_url is required for new rows"},
        )

    ok = await storage.update_purl(purl, new_purl, new_repo)
    if not ok:
        return JSONResponse(
            status_code=404,
            content={"error": "not_found", "message": "PURL not found"},
        )
    return JSONResponse(status_code=200, content={"ok": True})


@router.delete("/api/v1/db/purls")
async def delete_purls_endpoint(body: PurlDeleteRequest, request: Request):
    storage = request.app.state.storage
    deleted = await storage.delete_purls(body.purls)
    return JSONResponse(status_code=200, content={"deleted": deleted})


@router.post("/api/v1/db/import")
async def import_csv_endpoint(
    request: Request,
    file: UploadFile = File(...),
    strategy: ImportStrategy = Form(...),
):
    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return JSONResponse(
            status_code=400,
            content={"error": "invalid_csv", "message": "File must be UTF-8 encoded"},
        )

    rows, errors = parse_csv_import(text)
    if not rows and errors:
        return JSONResponse(
            status_code=400,
            content={"error": "invalid_csv", "message": errors[0]["error"]},
        )

    storage = request.app.state.storage

    if strategy == ImportStrategy.skip_existing:
        to_insert = []
        skipped = 0
        for row in rows:
            existing = await storage.lookup(row.purl)
            if existing is not None:
                skipped += 1
            else:
                to_insert.append(row)
        upserted, _ = await storage.upsert_many(to_insert)
        return JSONResponse(
            status_code=200,
            content=ImportResponse(
                imported=upserted,
                skipped=skipped,
                errors=[ImportErrorItem(row=e["row"], error=str(e["error"])) for e in errors],
            ).model_dump(),
        )

    upserted, _ = await storage.upsert_many(rows)
    return JSONResponse(
        status_code=200,
        content=ImportResponse(
            imported=upserted,
            skipped=0,
            errors=[ImportErrorItem(row=e["row"], error=str(e["error"])) for e in errors],
        ).model_dump(),
    )


@router.get("/api/v1/db/export")
async def export_csv_endpoint(
    request: Request,
    search: str | None = Query(None),
    resolver: str | None = Query(None),
    confidence: str | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    sort_by: str = Query("resolved_at"),
    sort_order: str = Query("desc"),
):
    storage = request.app.state.storage
    filters = PurlFilters(
        search=search,
        resolver=resolver,
        confidence=confidence,
        date_from=date_from,
        date_to=date_to,
    )
    total = await storage.count_purls(filters)
    rows = await storage.list_purls(
        offset=0,
        limit=max(total, 1),
        filters=filters,
        sort_by=sort_by,
        sort_order=sort_order,
    )

    csv_text = render_csv_export(rows)
    csv_bytes = csv_text.encode("utf-8")
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="resolved_purls_export.csv"'},
    )
