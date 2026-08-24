from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..schemas import BatchResolveItem, BatchResolveRequest, BatchResolveResponse
from ..settings_store import SettingsStore
from ..url_validator import ensure_connectivity

router = APIRouter()


@router.post("/api/v1/resolve/batch")
async def resolve_batch_endpoint(body: BatchResolveRequest, request: Request) -> JSONResponse:
    try:
        settings: SettingsStore = request.app.state.settings_store
        app_settings = settings.load()
        await ensure_connectivity(
            url=app_settings.connectivity_url,
            timeout=app_settings.connectivity_timeout,
        )
    except ConnectionError:
        return JSONResponse(
            status_code=503,
            content={"error": "network_unavailable"},
        )

    if len(body.purls) > app_settings.batch_max_items:
        return JSONResponse(
            status_code=400,
            content={
                "error": "batch_too_large",
                "detail": f"Maximum {app_settings.batch_max_items} PURLs per request",
            },
        )

    results = await request.app.state.resolution_service.resolve_many(purls=body.purls)

    items: list[BatchResolveItem] = []
    for original, result in zip(body.purls, results):
        if result.error_status is not None:
            items.append(
                BatchResolveItem(
                    purl=original,
                    error=result.error_body.get("error") if result.error_body else "error",
                )
            )
        elif result.response is not None:
            response_data = result.response.model_dump()
            response_data["purl"] = original
            items.append(BatchResolveItem(**response_data))

    return JSONResponse(
        status_code=200,
        content=BatchResolveResponse(results=items).model_dump(),
    )
