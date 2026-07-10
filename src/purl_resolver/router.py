from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from .routes.db_admin import router as db_admin_router
from .routes.ignore_patterns import router as ignore_patterns_router
from .routes.images_list import router as images_list_router
from .routes.jobs import router as jobs_router
from .routes.resolve import router as resolve_router
from .routes.settings import router as settings_router

router = APIRouter()

router.include_router(resolve_router)
router.include_router(jobs_router)
router.include_router(db_admin_router)
router.include_router(settings_router)
router.include_router(images_list_router)
router.include_router(ignore_patterns_router)


@router.get("/health")
async def health() -> JSONResponse:
    return JSONResponse(content={"status": "ok"})