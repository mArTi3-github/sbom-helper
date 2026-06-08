from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from .purl_utils import normalize, safe_normalize, validate
from .resolver.interface import InvalidPurlError, Resolver, UpstreamError
from .schemas import ResolveResponse, ResolveResult
from .settings_store import SettingsStore
from .storage.interface import Storage
from .url_validator import UrlValidationResult, validate_url

from .sbom.collector import SbomComponent

logger = logging.getLogger(__name__)

_BATCH_SEMAPHORE_LIMIT = 10


async def _validate_cached_url(
    cached: ResolveResponse,
    settings_store: SettingsStore | None,
    purl_key: str,
    storage: Storage,
) -> ResolveResponse | None:
    if settings_store is None:
        return cached

    app_settings = settings_store.load()
    if not app_settings.validate_db_urls:
        return cached

    resolved_date = None
    if cached.resolved_at:
        try:
            resolved_date = datetime.fromisoformat(cached.resolved_at).date()
        except (ValueError, TypeError):
            pass

    if resolved_date == datetime.now().date():
        return cached

    github_token = app_settings.github_token
    vresult = await validate_url(
        cached.repository_url,
        app_settings.url_validation_timeout,
        github_token=github_token,
    )

    if vresult == UrlValidationResult.TOKEN_INVALID:
        logger.warning("GitHub token invalid, removing from settings")
        try:
            settings_store.save(app_settings.model_copy(update={"github_token": None}))
        except Exception:
            logger.warning("Failed to persist token removal to settings", exc_info=True)
        vresult = await validate_url(
            cached.repository_url,
            app_settings.url_validation_timeout,
            github_token=None,
        )

    if vresult == UrlValidationResult.VALID:
        try:
            await storage.store(cached)
        except Exception:
            logger.warning("Failed to update resolved_at for %s", purl_key, exc_info=True)
    elif vresult == UrlValidationResult.INVALID:
        try:
            await storage.delete_purls([purl_key])
        except Exception:
            logger.warning("Failed to delete invalid URL for %s", purl_key, exc_info=True)
        return None

    return cached


async def resolve_purl(
    purl: str,
    storage: Storage,
    resolvers: list[Resolver],
    settings_store: SettingsStore | None = None,
    resolver: str = "",
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
            cached = await _validate_cached_url(cached, settings_store, purl_key, storage)
        if cached is not None:
            return ResolveResult.ok(cached)
    except Exception:
        logger.warning(
            "Cache lookup failed for %s, falling through to resolver",
            purl_key,
            exc_info=True,
        )

    for r in resolvers:
        try:
            resolution = await r.resolve(purl)
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
            resolver=r.name,
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


async def resolve_batch(
    purls: list[str],
    storage: Storage,
    resolvers: list[Resolver],
    settings_store: SettingsStore | None = None,
    resolver: str = "",
) -> dict[str, str]:
    semaphore = asyncio.Semaphore(_BATCH_SEMAPHORE_LIMIT)

    async def _resolve_one(original: str) -> tuple[str, str | None]:
        async with semaphore:
            result = await resolve_purl(original, storage, resolvers, settings_store=settings_store, resolver=resolver)
            key = safe_normalize(original)
            if result.response and result.response.repository_url:
                return (key, result.response.repository_url)
            return (key, None)

    tasks = [_resolve_one(p) for p in purls]
    results = await asyncio.gather(*tasks)
    return {k: v for k, v in results if v is not None}


async def store_preexisting_references(
    components: list[SbomComponent],
    storage: Storage,
    resolver: str = "",
) -> None:
    for comp in components:
        if comp.needs_enrichment:
            continue
        for ref in comp.existing_references:
            if ref.get("type") == "vcs" and ref.get("url"):
                purl_key = safe_normalize(comp.purl)
                try:
                    existing = await storage.lookup(purl_key)
                except Exception:
                    existing = None
                if existing is None:
                    await storage.store(ResolveResponse(
                        purl=purl_key,
                        repository_url=ref["url"],
                        evidence=["from SBOM externalReferences"],
                        resolver=resolver,
                    ))
                break
