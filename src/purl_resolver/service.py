from __future__ import annotations

import logging

from .resolver.interface import InvalidPurlError, Resolver, UpstreamError
from .schemas import ResolveResponse, ResolveResult
from .storage.interface import Storage

logger = logging.getLogger(__name__)


async def resolve_purl(
    purl: str,
    storage: Storage,
    resolvers: list[Resolver],
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

    for resolver in resolvers:
        try:
            resolution = resolver.resolve(purl)
        except InvalidPurlError as e:
            return ResolveResult.err(400, "invalid_purl", str(e))
        except UpstreamError as e:
            return ResolveResult.err(502, "upstream_error", str(e))

        if resolution.repository_url is None:
            continue

        response = ResolveResponse(
            purl=resolution.purl,
            repository_url=resolution.repository_url,
            repository_type=resolution.repository_type,
            repository_kind=resolution.repository_kind,
            confidence=resolution.confidence,
            evidence=list(resolution.evidence),
            warnings=list(resolution.warnings),
            version_reference=resolution.version_reference,
        )

        try:
            await storage.store(response)
            logger.info("Stored result for %s", purl)
        except Exception:
            logger.warning("Failed to store result for %s", purl, exc_info=True)

        return ResolveResult.ok(response)

    return ResolveResult.ok(
        ResolveResponse(
            purl=purl,
            warnings=["No resolver found a repository URL"],
        )
    )
