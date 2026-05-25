from __future__ import annotations

import logging

from purl2repo import resolve as purl2repo_resolve
from purl2repo.errors import (
    InvalidPurlError,
    MetadataFetchError,
    ResolutionError,
    UnsupportedEcosystemError,
)

from .config import Settings
from .schemas import ResolveResponse, ResolveResult
from .storage.interface import Storage

logger = logging.getLogger(__name__)


async def resolve_purl(
    purl: str,
    storage: Storage,
    settings: Settings,
) -> ResolveResult:
    try:
        cached = await storage.lookup(purl)
        if cached is not None:
            logger.info("Cache hit for %s", purl)
            return ResolveResult.ok(cached)
    except Exception:
        logger.warning(
            "Cache lookup failed for %s, falling through to resolver",
            purl,
            exc_info=True,
        )

    try:
        result = purl2repo_resolve(
            purl,
            timeout=settings.timeout,
            use_cache=settings.use_cache,
            strict=settings.strict,
            no_network=settings.no_network,
            cache_dir=settings.cache_dir,
        )
    except (InvalidPurlError, UnsupportedEcosystemError) as e:
        return ResolveResult.err(400, "invalid_purl", str(e))
    except (ResolutionError, MetadataFetchError) as e:
        return ResolveResult.err(502, "upstream_error", str(e))

    if result.repository_url is None:
        return ResolveResult.ok(
            ResolveResponse(
                purl=purl,
                warnings=list(result.warnings),
            )
        )

    response = ResolveResponse(
        purl=purl,
        repository_url=result.repository_url,
        repository_type=result.repository_type,
        repository_kind=result.repository_kind,
        confidence=result.confidence,
        evidence=list(result.evidence),
        warnings=list(result.warnings),
        version_reference=result.version_reference.url
        if result.version_reference
        else None,
    )

    try:
        await storage.store(response)
        logger.info("Stored result for %s", purl)
    except Exception:
        logger.warning("Failed to store result for %s", purl, exc_info=True)

    return ResolveResult.ok(response)
