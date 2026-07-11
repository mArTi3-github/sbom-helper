from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter, File, Form, Request, UploadFile, status
from fastapi.responses import JSONResponse, FileResponse

from ..config import sbom_settings

if TYPE_CHECKING:
    from ..job_manager import JobManager

router = APIRouter()

_UNAVAILABLE = JSONResponse(
    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    content={"error": "job_queue_unavailable"},
)


def _get_manager(request: Request) -> JobManager | None:
    return getattr(request.app.state, "job_manager", None)


@router.post("/api/v1/jobs/sbom-enrich", status_code=status.HTTP_202_ACCEPTED)
async def create_sbom_enrich_job(
    request: Request,
    file: UploadFile = File(...),
    remove_unresolved_no_subcomponents: bool = Form(False),
    ignore_patterns: str | None = Form(None),
) -> JSONResponse:
    raw = await file.read()
    if len(raw) > sbom_settings.max_file_size:
        return JSONResponse(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            content={
                "error": "file_too_large",
                "max_size_mb": sbom_settings.max_file_size // (1024 * 1024),
            },
        )

    try:
        json.loads(raw)
    except json.JSONDecodeError:
        return JSONResponse(status_code=400, content={"error": "invalid_json"})

    parsed_patterns = None
    if ignore_patterns:
        try:
            parsed_patterns = json.loads(ignore_patterns)
            if not isinstance(parsed_patterns, list):
                parsed_patterns = None
        except json.JSONDecodeError:
            parsed_patterns = None

    params = {
        "remove_unresolved_no_subcomponents": remove_unresolved_no_subcomponents,
    }
    if parsed_patterns:
        params["ignore_patterns"] = parsed_patterns

    manager = _get_manager(request)
    if manager is None:
        return _UNAVAILABLE
    job = await manager.create_job(raw, file.filename or "unknown.json", params)

    return JSONResponse(
        content={"job_id": job.id, "status": job.status},
        status_code=status.HTTP_202_ACCEPTED,
    )


@router.get("/api/v1/jobs/{job_id}")
async def get_job(request: Request, job_id: str) -> JSONResponse:
    manager = _get_manager(request)
    if manager is None:
        return _UNAVAILABLE
    record = await manager.get_job(job_id)
    if not record:
        return JSONResponse(status_code=404, content={"error": "job_not_found"})
    return JSONResponse(content={
        "job_id": record.id,
        "type": record.type,
        "status": record.status,
        "progress_current": record.progress_current,
        "progress_total": record.progress_total,
        "input_filename": record.input_filename,
        "summary": record.get_summary(),
        "results": record.get_results(),
        "error_message": record.error_message,
        "created_at": record.created_at,
        "started_at": record.started_at,
        "finished_at": record.finished_at,
    })


@router.get("/api/v1/jobs/{job_id}/result")
async def download_job_result(request: Request, job_id: str) -> FileResponse:
    manager = _get_manager(request)
    if manager is None:
        return _UNAVAILABLE
    record = await manager.get_job(job_id)
    if not record:
        return JSONResponse(status_code=404, content={"error": "job_not_found"})
    if record.status != "completed":
        return JSONResponse(
            status_code=400,
            content={"error": "result_not_ready", "status": record.status},
        )
    path = Path(record.result_path) if record.result_path else None
    if not path or not path.exists():
        return JSONResponse(status_code=404, content={"error": "result_file_not_found"})
    return FileResponse(
        path=path,
        filename=record.input_filename.replace(".json", "") + "_enriched.json",
        media_type="application/json",
    )


@router.post("/api/v1/jobs/{job_id}/cancel")
async def cancel_job(request: Request, job_id: str) -> JSONResponse:
    manager = _get_manager(request)
    if manager is None:
        return _UNAVAILABLE
    success = await manager.cancel_job(job_id)
    if not success:
        record = await manager.get_job(job_id)
        if not record:
            return JSONResponse(status_code=404, content={"error": "job_not_found"})
        return JSONResponse(
            status_code=409,
            content={"error": "job_already_terminal", "status": record.status},
        )
    return JSONResponse(content={"job_id": job_id, "status": "cancelled"})


@router.delete("/api/v1/jobs/{job_id}")
async def delete_job(request: Request, job_id: str) -> JSONResponse:
    manager = _get_manager(request)
    if manager is None:
        return _UNAVAILABLE
    success = await manager.delete_job(job_id)
    if not success:
        return JSONResponse(status_code=404, content={"error": "job_not_found"})
    return JSONResponse(content={"job_id": job_id, "deleted": True})


@router.get("/api/v1/jobs")
async def list_jobs(
    request: Request,
    limit: int = 20,
    offset: int = 0,
) -> JSONResponse:
    manager = _get_manager(request)
    if manager is None:
        return _UNAVAILABLE
    records = await manager.list_jobs(limit=limit, offset=offset)
    return JSONResponse(content={
        "jobs": [
            {
                "job_id": r.id,
                "type": r.type,
                "status": r.status,
                "progress_current": r.progress_current,
                "progress_total": r.progress_total,
                "input_filename": r.input_filename,
                "summary": r.get_summary(),
                "error_message": r.error_message,
                "created_at": r.created_at,
                "started_at": r.started_at,
                "finished_at": r.finished_at,
            }
            for r in records
        ],
    })
