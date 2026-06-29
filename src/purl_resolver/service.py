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
from .url_validator import UrlValidationOutput, UrlValidationResult, validate_url_with_retry
from .validation_service import UrlValidationService

logger = logging.getLogger(__name__)

TRUSTED_RESOLVERS: frozenset[str] = frozenset({"purl2repo", "ecosyste.ms", "libraries.io"})

_BATCH_SEMAPHORE_LIMIT = 10


class PurlResolutionService:
    def __init__(
        self,
        storage: Storage,
        resolvers: list[Resolver],
        settings_store: SettingsStore | None = None,
        validation_service: UrlValidationService | None = None,
    ) -> None:
        self._storage = storage
        self._resolvers = resolvers
        self._settings_store = settings_store
        self._validation_service = validation_service

    @property
    def settings_store(self) -> SettingsStore | None:
        return self._settings_store

    @property
    def validation_service(self) -> UrlValidationService | None:
        return self._validation_service

    def _is_within_cooldown(self, cached: ResolveResponse) -> bool:
        if self._settings_store is None:
            return True
        app_settings = self._settings_store.load()
        if not app_settings.validate_db_urls:
            return True
        cooldown_hours = app_settings.revalidation_cooldown_hours
        if cooldown_hours > 0 and cached.resolver in TRUSTED_RESOLVERS and cached.resolved_at:
            try:
                resolved_date = datetime.fromisoformat(cached.resolved_at)
                elapsed = datetime.now() - resolved_date
                if elapsed.total_seconds() < cooldown_hours * 3600:
                    return True
            except (ValueError, TypeError):
                pass
        return False

    async def _validate_cached_url(
        self,
        cached: ResolveResponse,
        purl_key: str,
    ) -> ResolveResponse | None:
        if self._is_within_cooldown(cached):
            return cached

        app_settings = self._settings_store.load()
        github_token = app_settings.github_token

        if self._validation_service is not None:
            voutput = await self._validation_service.validate_url(
                cached.repository_url,
                app_settings.url_validation_timeout,
                github_token=github_token,
                skip_connectivity_check=True,
            )
        else:
            voutput = await validate_url_with_retry(
                cached.repository_url,
                app_settings.url_validation_timeout,
                github_token=github_token,
                settings_store=self._settings_store,
                skip_connectivity_check=True,
            )

        if voutput.result == UrlValidationResult.VALID:
            new_url = voutput.final_url or cached.repository_url
            if new_url != cached.repository_url:
                logger.info("Updated repository URL for %s: %s -> %s", purl_key, cached.repository_url, new_url)
                cached.repository_url = new_url
            try:
                await self._storage.store(cached)
            except Exception:
                logger.warning("Failed to update resolved_at for %s", purl_key, exc_info=True)
        elif voutput.result == UrlValidationResult.INVALID:
            try:
                await self._storage.delete_purls([purl_key])
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
                cached = await self._validate_cached_url(cached, purl_key)
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
                    if self._validation_service is not None:
                        voutput = await self._validation_service.validate_url(
                            repo_url,
                            app_settings.url_validation_timeout,
                            github_token=app_settings.github_token,
                            skip_connectivity_check=True,
                        )
                    else:
                        voutput = await validate_url_with_retry(
                            repo_url,
                            app_settings.url_validation_timeout,
                            github_token=app_settings.github_token,
                            settings_store=self._settings_store,
                            skip_connectivity_check=True,
                        )
                    if voutput.result == UrlValidationResult.INVALID:
                        logger.warning(
                            "Resolver %s returned invalid URL %s for %s, skipping",
                            r.name, repo_url, purl,
                        )
                        continue
                    if voutput.result in (UrlValidationResult.NETWORK_ERROR, UrlValidationResult.RATE_LIMITED):
                        logger.warning(
                            "URL validation inconclusive for %s (resolver=%s, result=%s), accepting anyway",
                            repo_url, r.name, voutput.result.value,
                        )
                    repo_url = voutput.final_url or repo_url

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


