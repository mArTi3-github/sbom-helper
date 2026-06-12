from __future__ import annotations

from fastapi import APIRouter, File, Form, Query, Request, UploadFile
from fastapi.responses import JSONResponse, Response

from ..db_admin_service import DbAdminError, DbAdminService
from ..schemas import (
    ImportStrategy,
    PurlDeleteRequest,
    PurlListParams,
    PurlUpdateRequest,
)

router = APIRouter()


@router.get("/api/v1/db/purls")
async def list_purls_endpoint(request: Request, params: PurlListParams = Query()):
    service: DbAdminService = request.app.state.db_admin_service
    response = await service.list_purls(params)
    return JSONResponse(status_code=200, content=response.model_dump())


@router.patch("/api/v1/db/purls/{purl:path}")
async def update_purl_endpoint(
    purl: str, body: PurlUpdateRequest, request: Request
):
    service: DbAdminService = request.app.state.db_admin_service
    ok, error_msg = await service.update_purl(purl, body)
    if not ok:
        status = 404 if error_msg == "PURL not found" else 400
        return JSONResponse(
            status_code=status,
            content={"error": "not_found" if status == 404 else "invalid_update", "message": error_msg},
        )
    return JSONResponse(status_code=200, content={"ok": True})


@router.delete("/api/v1/db/purls")
async def delete_purls_endpoint(body: PurlDeleteRequest, request: Request):
    service: DbAdminService = request.app.state.db_admin_service
    deleted = await service.delete_purls(body.purls)
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

    service: DbAdminService = request.app.state.db_admin_service
    try:
        result = await service.import_csv(text, strategy)
    except DbAdminError as e:
        return JSONResponse(
            status_code=e.status_code,
            content={"error": "invalid_csv", "message": e.message},
        )
    return JSONResponse(status_code=200, content=result.model_dump())


@router.get("/api/v1/db/export")
async def export_csv_endpoint(
    request: Request,
    params: PurlListParams = Query(),
):
    service: DbAdminService = request.app.state.db_admin_service
    csv_text = await service.export_csv(params)
    csv_bytes = csv_text.encode("utf-8")
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="resolved_purls_export.csv"'},
    )
