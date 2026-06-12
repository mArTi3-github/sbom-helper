from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter()


class IgnorePatternItem(BaseModel):
    field: str
    pattern: str


class IgnorePatternsPayload(BaseModel):
    patterns: list[IgnorePatternItem]


@router.get("/api/v1/sbom/ignore-patterns")
async def get_ignore_patterns(request: Request) -> JSONResponse:
    store = request.app.state.ignore_patterns_store
    patterns = store.load()
    return JSONResponse(content={"patterns": patterns})


@router.post("/api/v1/sbom/ignore-patterns")
async def save_ignore_patterns(
    payload: IgnorePatternsPayload,
    request: Request,
) -> JSONResponse:
    store = request.app.state.ignore_patterns_store
    data = [{"field": p.field, "pattern": p.pattern} for p in payload.patterns]
    store.save(data)
    return JSONResponse(content={"status": "saved"})
