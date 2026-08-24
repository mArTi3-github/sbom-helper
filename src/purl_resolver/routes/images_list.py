from __future__ import annotations

import json

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse

from ..config import sbom_settings
from ..sbom.images_list_converter import ImagesListConverter
from ..sbom.parser import SbomParseError

router = APIRouter()


@router.post("/api/v1/convert/images-list")
async def convert_images_list(
    file: UploadFile = File(...),
) -> JSONResponse:
    raw = await file.read()
    if len(raw) > sbom_settings.max_file_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={
                "error": "file_too_large",
                "max_size_mb": sbom_settings.max_file_size // (1024*1024),
            },
        )

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return JSONResponse(
            status_code=400,
            content={"error": "invalid_json"},
        )

    try:
        result = ImagesListConverter.convert(data)
    except SbomParseError as e:
        return JSONResponse(
            status_code=400,
            content={"error": "invalid_sbom", "detail": str(e)},
        )

    return JSONResponse(
        status_code=200,
        content={
            "was_transformed": result.was_transformed,
            "images": [
                {
                    "name": img.name,
                    "version": img.version,
                    "missing_components": img.missing_components,
                    "missing_name": img.missing_name,
                    "missing_version": img.missing_version,
                    "missing_properties": img.missing_properties,
                    "duplicates_removed": img.duplicates_removed,
                }
                for img in result.images
            ],
            "images_list": result.images_list,
        },
    )
