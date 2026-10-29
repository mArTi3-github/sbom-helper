from __future__ import annotations

import json
import logging

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from ..config import sbom_settings
from ..sbom.fixer import SbomFixOptions, fix_sbom
from ..sbom.optional_fields import (
    DEFAULT_KEEP_FIELDS,
    FSTEC_FIELDS,
    analyze_fields,
    invalid_keep_entries,
)
from ..sbom.parser import CycloneDXParser, SbomParseError

logger = logging.getLogger(__name__)

router = APIRouter()


def _invalid_options(detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={"error": "invalid_options", "detail": detail},
    )


def _invalid_remove_fields() -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={"error": "invalid_remove_fields"},
    )


async def _load_sbom(
    file: UploadFile,
) -> tuple[dict | None, JSONResponse | None]:
    raw = await file.read()
    if len(raw) > sbom_settings.max_file_size:
        return None, JSONResponse(
            status_code=413,
            content={
                "error": "file_too_large",
                "max_size_mb": sbom_settings.max_file_size // (1024 * 1024),
            },
        )

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, JSONResponse(
            status_code=400,
            content={"error": "invalid_json"},
        )

    try:
        data = CycloneDXParser.parse(data)
    except SbomParseError as e:
        return None, JSONResponse(
            status_code=400,
            content={"error": "invalid_sbom", "detail": str(e)},
        )

    return data, None


def _parse_remove_fields(
    raw: str | None,
) -> tuple[list[str] | None, JSONResponse | None]:
    if raw is None:
        return [], None
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, _invalid_remove_fields()
    if not isinstance(value, list) or not all(
        isinstance(item, str) for item in value
    ):
        return None, _invalid_remove_fields()
    return value, None


@router.get("/api/v1/sbom/fix/field-catalog")
async def get_sbom_fix_field_catalog() -> JSONResponse:
    return JSONResponse(
        content={
            "fstec_fields": [
                {
                    "path": fstec_field.path,
                    "status": fstec_field.status,
                    **(
                        {"condition_key": fstec_field.condition_key}
                        if fstec_field.condition_key is not None
                        else {}
                    ),
                }
                for fstec_field in FSTEC_FIELDS
            ],
            "default_keep": list(DEFAULT_KEEP_FIELDS),
        }
    )


@router.post("/api/v1/sbom/fix/analyze")
async def analyze_sbom_endpoint(file: UploadFile = File(...)) -> JSONResponse:
    data, error = await _load_sbom(file)
    if error is not None:
        return error
    assert data is not None
    return JSONResponse(
        content={
            "fields": [
                {
                    "path": field_info.path,
                    "status": field_info.status,
                    "count": field_info.count,
                }
                for field_info in analyze_fields(data)
            ]
        }
    )


@router.post("/api/v1/sbom/fix")
async def fix_sbom_endpoint(
    file: UploadFile = File(...),
    options: str | None = Form(None),
    remove_fields: str | None = Form(None),
) -> JSONResponse:
    data, error = await _load_sbom(file)
    if error is not None:
        return error
    assert data is not None

    if options is None:
        fix_options = SbomFixOptions()
    else:
        try:
            fix_options = SbomFixOptions.model_validate(json.loads(options))
        except json.JSONDecodeError as e:
            return _invalid_options(str(e))
        except ValidationError as e:
            return _invalid_options(str(e))

    fields_to_remove, remove_error = _parse_remove_fields(remove_fields)
    if remove_error is not None:
        return remove_error
    assert fields_to_remove is not None

    result = fix_sbom(data, fix_options, remove_fields=fields_to_remove)

    return JSONResponse(
        status_code=200,
        content={
            "changed": result.changed,
            "fixed_sbom": result.fixed_sbom,
            "stats": [
                {
                    "rule_id": stat.rule_id,
                    "count": stat.count,
                    **({"field": stat.field} if stat.field is not None else {}),
                }
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

    raw_options = body["options"]
    if isinstance(raw_options, dict):
        optional_fields = raw_options.get("optional_fields")
        if isinstance(optional_fields, dict):
            raw_keep = optional_fields.get("keep")
            if isinstance(raw_keep, list):
                invalid_entries = invalid_keep_entries(raw_keep)
                if invalid_entries:
                    return _invalid_options(
                        "Invalid keep entries: " + ", ".join(invalid_entries)
                    )

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
