from __future__ import annotations

import json

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import JSONResponse

from ..config import sbom_settings
from ..sbom.parser import SbomParseError
from ..sbom_enrichment import SbomEnrichmentPipeline
from ..schemas import ResolveRequest
from ..settings_store import SettingsStore
from ..url_validator import ensure_connectivity

router = APIRouter()


@router.post("/api/v1/resolve")
async def resolve_endpoint(body: ResolveRequest, request: Request) -> JSONResponse:
    try:
        settings: SettingsStore = request.app.state.settings_store
        app_settings = settings.load()
        await ensure_connectivity(
            url=app_settings.connectivity_url,
            timeout=app_settings.connectivity_timeout,
        )
    except ConnectionError as e:
        return JSONResponse(
            status_code=503,
            content={"error": "network_unavailable", "message": str(e)},
        )

    result = await request.app.state.resolution_service.resolve_purl(purl=body.purl)

    if result.error_status is not None:
        return JSONResponse(
            status_code=result.error_status, content=result.error_body
        )

    return JSONResponse(status_code=200, content=result.response.model_dump())


@router.post("/api/v1/resolve/sbom")
async def resolve_sbom_endpoint(
    request: Request,
    file: UploadFile = File(...),
    remove_unresolved_no_subcomponents: bool = Form(False),
    ignore_patterns: str = Form(None),
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

    parsed_patterns: list[dict[str, str]] | None = None
    if ignore_patterns:
        try:
            parsed_patterns = json.loads(ignore_patterns)
            if not isinstance(parsed_patterns, list):
                parsed_patterns = None
        except json.JSONDecodeError:
            parsed_patterns = None

    try:
        settings: SettingsStore = request.app.state.settings_store
        app_settings = settings.load()
        await ensure_connectivity(
            url=app_settings.connectivity_url,
            timeout=app_settings.connectivity_timeout,
        )
    except ConnectionError as e:
        return JSONResponse(
            status_code=503,
            content={"error": "network_unavailable", "message": str(e)},
        )

    pipeline = SbomEnrichmentPipeline(
        resolution_service=request.app.state.resolution_service,
    )

    try:
        result = await pipeline.process(
            data,
            remove_unresolved_no_subcomponents=remove_unresolved_no_subcomponents,
            ignore_patterns=parsed_patterns,
        )
    except SbomParseError as e:
        return JSONResponse(
            status_code=400,
            content={"error": "invalid_sbom", "message": str(e)},
        )

    return JSONResponse(
        status_code=200,
        content={**result.report, "enriched_sbom": result.enriched_sbom},
    )
