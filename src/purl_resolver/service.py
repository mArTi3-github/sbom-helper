from __future__ import annotations

import logging

from .purl_utils import normalize, validate
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
        components = validate(purl)
    except Exception as e:
        return ResolveResult.err(400, "invalid_purl", str(e))

    purl_key = normalize(components)

    try:
        cached = await storage.lookup(purl_key)
        if cached is not None:
            logger.info("Cache hit for %s", purl_key)
            return ResolveResult.ok(cached)
    except Exception:
        logger.warning(
            "Cache lookup failed for %s, falling through to resolver",
            purl_key,
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
            purl=purl_key,
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
            logger.info("Stored result for %s", purl_key)
        except Exception:
            logger.warning("Failed to store result for %s", purl_key, exc_info=True)

        return ResolveResult.ok(response)

    return ResolveResult.ok(
        ResolveResponse(
            purl=purl_key,
            warnings=["No resolver found a repository URL"],
        )
    )
