from __future__ import annotations

import json
import logging

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from ..config import sbom_settings
from ..sbom.fixer import SbomFixOptions, fix_sbom
from ..sbom.parser import CycloneDXParser, SbomParseError

logger = logging.getLogger(__name__)

router = APIRouter()


def _invalid_options(detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={"error": "invalid_options", "detail": detail},
    )


@router.post("/api/v1/sbom/fix")
async def fix_sbom_endpoint(
    file: UploadFile = File(...),
    options: str | None = Form(None),
) -> JSONResponse:
    raw = await file.read()
    if len(raw) > sbom_settings.max_file_size:
        return JSONResponse(
            status_code=413,
            content={
                "error": "file_too_large",
                "max_size_mb": sbom_settings.max_file_size // (1024 * 1024),
            },
        )

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JSONResponse(
            status_code=400,
            content={"error": "invalid_json"},
        )

    try:
        data = CycloneDXParser.parse(data)
    except SbomParseError as e:
        return JSONResponse(
            status_code=400,
            content={"error": "invalid_sbom", "detail": str(e)},
        )

    if options is None:
        fix_options = SbomFixOptions()
    else:
        try:
            fix_options = SbomFixOptions.model_validate(json.loads(options))
        except json.JSONDecodeError as e:
            return _invalid_options(str(e))
        except ValidationError as e:
            return _invalid_options(str(e))

    result = fix_sbom(data, fix_options)

    return JSONResponse(
        status_code=200,
        content={
            "changed": result.changed,
            "fixed_sbom": result.fixed_sbom,
            "stats": [
                {"rule_id": stat.rule_id, "count": stat.count}
                for stat in result.stats
            ],
            "issues": [
                {
                    "code": issue.code,
                    "path": issue.path,
                    "component": issue.component,
                    "details": issue.details,
                }
                for issue in result.issues
            ],
        },
    )


@router.get("/api/v1/sbom/fix/options")
async def get_sbom_fix_options(request: Request) -> JSONResponse:
    store = request.app.state.sbom_fix_options_store
    return JSONResponse(content={"options": store.load().model_dump()})


@router.post("/api/v1/sbom/fix/options")
async def save_sbom_fix_options(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return _invalid_options(str(e))

    if not isinstance(body, dict) or "options" not in body:
        return _invalid_options("Body must be a JSON object with an 'options' key")

    try:
        options = SbomFixOptions.model_validate(body["options"])
    except ValidationError as e:
        return _invalid_options(str(e))

    store = request.app.state.sbom_fix_options_store
    try:
        store.save(options)
    except OSError:
        logger.exception("Failed to save sbom fix options")
        return JSONResponse(
            status_code=500,
            content={"error": "options_save_failed"},
        )

    return JSONResponse(content={"status": "saved"})
