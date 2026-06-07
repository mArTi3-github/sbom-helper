from __future__ import annotations

import json
import logging

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import JSONResponse

from ..config import sbom_settings
from ..schemas import ResolveRequest
from ..service import resolve_purl
from ..sbom_enrichment import SbomEnrichmentPipeline
from ..sbom.parser import SbomParseError

logger = logging.getLogger(__name__)

router = APIRouter()


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
