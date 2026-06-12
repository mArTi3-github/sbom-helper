from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from .purl_utils import normalize, safe_normalize, validate
from .resolver.interface import InvalidPurlError, Resolver, UpstreamError
from .sbom.collector import SbomComponent
from .schemas import ResolveResponse, ResolveResult
from .settings_store import SettingsStore
from .storage.interface import Storage
from .url_validator import UrlValidationResult, validate_url, validate_url_with_retry

logger = logging.getLogger(__name__)

TRUSTED_RESOLVERS: frozenset[str] = frozenset({"purl2repo", "ecosyste.ms", "libraries.io"})

_BATCH_SEMAPHORE_LIMIT = 10


class PurlResolutionService:
    def __init__(
        self,
        storage: Storage,
        resolvers: list[Resolver],
        settings_store: SettingsStore | None = None,
    ) -> None:
        self._storage = storage
        self._resolvers = resolvers
        self._settings_store = settings_store

    @staticmethod
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

        cooldown_hours = app_settings.revalidation_cooldown_hours
        if cooldown_hours > 0 and cached.resolver in TRUSTED_RESOLVERS and cached.resolved_at:
            try:
                resolved_date = datetime.fromisoformat(cached.resolved_at)
                elapsed = datetime.now() - resolved_date
                if elapsed.total_seconds() < cooldown_hours * 3600:
                    return cached
            except (ValueError, TypeError):
                pass

        github_token = app_settings.github_token
        vresult = await validate_url_with_retry(
            cached.repository_url,
            app_settings.url_validation_timeout,
            github_token=github_token,
            settings_store=settings_store,
            skip_connectivity_check=True,
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
        self,
        purl: str,
        resolver: str = "",
    ) -> ResolveResult:
        try:
            components = validate(purl)
        except Exception as e:
            return ResolveResult.err(400, "invalid_purl", str(e))

        purl_key = normalize(components)

        try:
            cached = await self._storage.lookup(purl_key)
            if cached is not None:
                logger.info("Cache hit for %s", purl_key)
                cached = await self._validate_cached_url(cached, self._settings_store, purl_key, self._storage)
            if cached is not None:
                cached.found_by = "local_db"
                return ResolveResult.ok(cached)
        except Exception:
            logger.warning(
                "Cache lookup failed for %s, falling through to resolver",
                purl_key,
                exc_info=True,
            )

        for r in self._resolvers:
            try:
                resolution = await r.resolve(purl)
            except InvalidPurlError as e:
                return ResolveResult.err(400, "invalid_purl", str(e))
            except UpstreamError as e:
                return ResolveResult.err(502, "upstream_error", str(e))

            if resolution.repository_url is None:
                continue

            repo_url = resolution.repository_url

            if self._settings_store is not None:
                app_settings = self._settings_store.load()
                if app_settings.validate_db_urls:
                    vresult = await validate_url_with_retry(
                        repo_url,
                        app_settings.url_validation_timeout,
                        github_token=app_settings.github_token,
                        settings_store=self._settings_store,
                        skip_connectivity_check=True,
                    )
                    if vresult == UrlValidationResult.INVALID:
                        logger.warning(
                            "Resolver %s returned invalid URL %s for %s, skipping",
                            r.name, repo_url, purl,
                        )
                        continue
                    if vresult in (UrlValidationResult.NETWORK_ERROR, UrlValidationResult.RATE_LIMITED):
                        logger.warning(
                            "URL validation inconclusive for %s (resolver=%s, result=%s), accepting anyway",
                            repo_url, r.name, vresult,
                        )

            response = ResolveResponse(
                purl=purl_key,
                repository_url=repo_url,
                repository_type=resolution.repository_type,
                repository_kind=resolution.repository_kind,
                confidence=resolution.confidence,
                evidence=list(resolution.evidence),
                warnings=list(resolution.warnings),
                version_reference=resolution.version_reference,
                resolver=r.name,
                found_by="resolver",
            )

            try:
                await self._storage.store(response)
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
        self,
        purls: list[str],
        resolver: str = "",
    ) -> dict[str, ResolveResponse]:
        semaphore = asyncio.Semaphore(_BATCH_SEMAPHORE_LIMIT)

        async def _resolve_one(original: str) -> tuple[str, ResolveResponse | None]:
            async with semaphore:
                result = await self.resolve_purl(original, resolver=resolver)
                key = safe_normalize(original)
                if result.response and result.response.repository_url:
                    return (key, result.response)
                return (key, None)

        tasks = [_resolve_one(p) for p in purls]
        results = await asyncio.gather(*tasks)
        return {k: v for k, v in results if v is not None}

    async def store_preexisting_references(
        self,
        components: list[SbomComponent],
        resolver: str = "",
    ) -> None:
        for comp in components:
            if comp.needs_enrichment:
                continue
            for ref in comp.existing_references:
                if ref.get("type") == "vcs" and ref.get("url"):
                    purl_key = safe_normalize(comp.purl)
                    try:
                        existing = await self._storage.lookup(purl_key)
                    except Exception:
                        existing = None
                    if existing is None:
                        await self._storage.store(ResolveResponse(
                            purl=purl_key,
                            repository_url=ref["url"],
                            evidence=["from SBOM externalReferences"],
                            resolver=resolver,
                        ))
                    break


async def _validate_cached_url(
    cached: ResolveResponse,
    settings_store: SettingsStore | None,
    purl_key: str,
    storage: Storage,
) -> ResolveResponse | None:
    return await PurlResolutionService._validate_cached_url(cached, settings_store, purl_key, storage)


async def resolve_purl(
    purl: str,
    storage: Storage,
    resolvers: list[Resolver],
    settings_store: SettingsStore | None = None,
    resolver: str = "",
) -> ResolveResult:
    svc = PurlResolutionService(storage, resolvers, settings_store)
    return await svc.resolve_purl(purl, resolver=resolver)


async def resolve_batch(
    purls: list[str],
    storage: Storage,
    resolvers: list[Resolver],
    settings_store: SettingsStore | None = None,
    resolver: str = "",
) -> dict[str, ResolveResponse]:
    svc = PurlResolutionService(storage, resolvers, settings_store)
    return await svc.resolve_batch(purls, resolver=resolver)


async def store_preexisting_references(
    components: list[SbomComponent],
    storage: Storage,
    resolver: str = "",
) -> None:
    svc = PurlResolutionService(storage, [], None)
    return await svc.store_preexisting_references(components, resolver=resolver)
