from __future__ import annotations

import json
import logging
import pathlib
from datetime import date

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates

from .config import sbom_settings
from .schemas import (
    ResolveRequest,
    ResolveResponse,
    DeleteResponse,
    ImportErrorItem,
    ImportResponse,
    ImportStrategy,
    PurlDeleteRequest,
    PurlListParams,
    PurlListResponse,
    PurlUpdateRequest,
)
from pydantic import BaseModel, Field

from .service import resolve_purl
from .sbom_enrichment import SbomEnrichmentPipeline
from .sbom.parser import SbomParseError
from .settings_store import SettingsStore, AppSettings
from .url_validator import validate_github_token
from .csv_io import parse_csv_import, render_csv_export
from .storage.interface import PurlFilters

logger = logging.getLogger(__name__)

class SettingsUpdate(BaseModel):
    validate_db_urls: bool | None = None
    url_validation_timeout: int | None = Field(None, ge=1, le=60)
    github_token: str | None = None


router = APIRouter()
_templates_dir = (pathlib.Path(__file__).parent / "templates").resolve()
templates = Jinja2Templates(directory=str(_templates_dir))


@router.post("/api/v1/resolve")
async def resolve_endpoint(body: ResolveRequest, request: Request) -> JSONResponse:
    result = await resolve_purl(
        purl=body.purl,
        storage=request.app.state.storage,
        resolvers=request.app.state.resolvers,
        settings_store=request.app.state.settings_store,
    )

    if result.error_status is not None:
        return JSONResponse(
            status_code=result.error_status, content=result.error_body
        )

    return JSONResponse(status_code=200, content=result.response.model_dump())


@router.get("/health")
async def health() -> JSONResponse:
    return JSONResponse(content={"status": "ok"})


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="index.html")


@router.get("/sbom-updater", response_class=HTMLResponse)
async def sbom_updater_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="sbom.html")


@router.post("/api/v1/resolve/sbom")
async def resolve_sbom_endpoint(
    request: Request,
    file: UploadFile = File(...),
    remove_unresolved_no_subcomponents: bool = Form(False),
) -> JSONResponse:
    raw = await file.read()
    if len(raw) > sbom_settings.max_file_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={
                "error": "file_too_large",
                "message": f"File size exceeds maximum of {sbom_settings.max_file_size // (1024*1024)} MB",
            },
        )

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        return JSONResponse(
            status_code=400,
            content={"error": "invalid_json", "message": f"Invalid JSON: {e}"},
        )

    pipeline = SbomEnrichmentPipeline(
        storage=request.app.state.storage,
        resolvers=request.app.state.resolvers,
        settings_store=getattr(request.app.state, "settings_store", None),
    )

    try:
        result = await pipeline.process(data, remove_unresolved_no_subcomponents=remove_unresolved_no_subcomponents)
    except SbomParseError as e:
        return JSONResponse(
            status_code=400,
            content={"error": "invalid_sbom", "message": str(e)},
        )

    return JSONResponse(
        status_code=200,
        content={**result.report, "enriched_sbom": result.enriched_sbom},
    )


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
    row_responses = [
        ResolveResponse(
            purl=r.purl,
            repository_url=r.repository_url,
            repository_type=r.repository_type,
            repository_kind=r.repository_kind,
            confidence=r.confidence,
            evidence=r.evidence,
            warnings=r.warnings,
            version_reference=r.version_reference,
            resolver=r.resolver,
            resolved_at=r.resolved_at,
        )
        for r in rows
    ]
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


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="settings.html")


@router.get("/db-admin", response_class=HTMLResponse)
async def db_admin_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="db-admin.html")


@router.get("/api/v1/settings")
async def get_settings(request: Request) -> JSONResponse:
    store: SettingsStore = request.app.state.settings_store
    settings = store.load()
    return JSONResponse(content={
        "validate_db_urls": settings.validate_db_urls,
        "url_validation_timeout": settings.url_validation_timeout,
        "token_set": {
            "github_token": settings.github_token is not None,
        },
    })


@router.patch("/api/v1/settings")
async def update_settings(body: SettingsUpdate, request: Request) -> JSONResponse:
    store: SettingsStore = request.app.state.settings_store
    current = store.load()
    update_data = body.model_dump(exclude_unset=True)

    if "github_token" in update_data:
        token_value = update_data["github_token"]
        if token_value == "" or token_value is None:
            update_data["github_token"] = None
        else:
            is_valid = await validate_github_token(token_value)
            if not is_valid:
                return JSONResponse(
                    status_code=400,
                    content={"error": "invalid_token", "message": "GitHub token is invalid or expired"},
                )

    if update_data:
        updated = current.model_copy(update=update_data)
        store.save(updated)
    else:
        updated = current

    return JSONResponse(content={
        "validate_db_urls": updated.validate_db_urls,
        "url_validation_timeout": updated.url_validation_timeout,
        "token_set": {
            "github_token": updated.github_token is not None,
        },
    })
