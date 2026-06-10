from __future__ import annotations

import pathlib

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from .routes.resolve import router as resolve_router
from .routes.db_admin import router as db_admin_router
from .routes.settings import router as settings_router
from .routes.images_list import router as images_list_router

router = APIRouter()
_templates_dir = (pathlib.Path(__file__).parent / "templates").resolve()
templates = Jinja2Templates(directory=str(_templates_dir))

router.include_router(resolve_router)
router.include_router(db_admin_router)
router.include_router(settings_router)
router.include_router(images_list_router)


@router.get("/health")
async def health() -> JSONResponse:
    return JSONResponse(content={"status": "ok"})


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="index.html")


@router.get("/sbom-updater", response_class=HTMLResponse)
async def sbom_updater_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="sbom.html")


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="settings.html")


@router.get("/db-admin", response_class=HTMLResponse)
async def db_admin_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="db-admin.html")


@router.get("/images-list-converter", response_class=HTMLResponse)
async def images_list_converter_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="images-list-converter.html")
