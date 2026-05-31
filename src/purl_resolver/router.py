from __future__ import annotations

import json
import logging
import pathlib

from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from .config import sbom_settings
from .schemas import ResolveRequest
from .service import resolve_purl, resolve_batch, process_sbom
from .sbom.collector import collect_components
from .sbom.parser import CycloneDXParser, SbomParseError
from .purl_utils import safe_normalize

logger = logging.getLogger(__name__)

router = APIRouter()
_templates_dir = (pathlib.Path(__file__).parent / "templates").resolve()
templates = Jinja2Templates(directory=str(_templates_dir))


@router.post("/api/v1/resolve")
async def resolve_endpoint(body: ResolveRequest, request: Request) -> JSONResponse:
    result = await resolve_purl(
        purl=body.purl,
        storage=request.app.state.storage,
        resolvers=request.app.state.resolvers,
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

    try:
        CycloneDXParser.parse(data)
    except SbomParseError as e:
        return JSONResponse(
            status_code=400,
            content={"error": "invalid_sbom", "message": str(e)},
        )

    components = collect_components(data)
    purls_to_resolve = [c for c in components if c.needs_enrichment]

    seen: set[str] = set()
    unique_purls: list[str] = []
    skipped = 0
    for comp in purls_to_resolve:
        n = safe_normalize(comp.purl)
        if n == comp.purl:
            skipped += 1
            continue
        if n not in seen:
            seen.add(n)
            unique_purls.append(comp.purl)

    storage = request.app.state.storage
    resolvers = request.app.state.resolvers
    resolved = await resolve_batch(unique_purls, storage, resolvers)
    report = process_sbom(data, components, resolved, skipped=skipped)

    return JSONResponse(
        status_code=200,
        content={**report, "enriched_sbom": data},
    )
