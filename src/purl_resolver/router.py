from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from purl2repo import resolve
from purl2repo.errors import (
    InvalidPurlError,
    MetadataFetchError,
    ResolutionError,
    UnsupportedEcosystemError,
)

from .config import settings
from .schemas import ErrorResponse, ResolveRequest, ResolveResponse

router = APIRouter()
templates = Jinja2Templates(directory="src/purl_resolver/templates")


@router.post("/api/v1/resolve")
async def resolve_endpoint(body: ResolveRequest) -> JSONResponse:
    try:
        result = resolve(
            body.purl,
            timeout=settings.timeout,
            use_cache=settings.use_cache,
            strict=settings.strict,
            no_network=settings.no_network,
            cache_dir=settings.cache_dir,
        )
    except (InvalidPurlError, UnsupportedEcosystemError) as e:
        return JSONResponse(
            status_code=400,
            content=ErrorResponse(
                error="invalid_purl",
                message=str(e),
            ).model_dump(),
        )
    except (ResolutionError, MetadataFetchError) as e:
        return JSONResponse(
            status_code=502,
            content=ErrorResponse(
                error="upstream_error",
                message=str(e),
            ).model_dump(),
        )

    if result.repository_url is None:
        return JSONResponse(
            status_code=200,
            content=ResolveResponse(
                purl=body.purl,
                warnings=result.warnings,
            ).model_dump(),
        )

    return JSONResponse(
        status_code=200,
        content=ResolveResponse(
            purl=body.purl,
            repository_url=result.repository_url,
            repository_type=result.repository_type,
            repository_kind=result.repository_kind,
            confidence=result.confidence,
            evidence=list(result.evidence),
            warnings=list(result.warnings),
            version_reference=result.version_reference.url
            if result.version_reference
            else None,
        ).model_dump(),
    )


@router.get("/health")
async def health() -> JSONResponse:
    return JSONResponse(content={"status": "ok"})


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="index.html")