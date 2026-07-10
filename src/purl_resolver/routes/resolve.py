from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

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
            content={"error": "network_unavailable"},
        )

    result = await request.app.state.resolution_service.resolve_purl(purl=body.purl)

    if result.error_status is not None:
        return JSONResponse(
            status_code=result.error_status, content=result.error_body
        )

    return JSONResponse(status_code=200, content=result.response.model_dump())


