from __future__ import annotations

import asyncio
import itertools
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime

from .purl_utils import normalize, safe_normalize, validate
from .resolver.interface import InvalidPurlError, Resolver, UpstreamError
from .sbom.collector import SbomComponent
from .schemas import ResolveResponse, ResolveResult
from .settings_store import SettingsStore
from .storage.interface import Storage
from .url_validator import UrlValidationOutput, UrlValidationResult
from .validation_service import UrlValidationService

logger = logging.getLogger(__name__)

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

    def set_resolvers(self, resolvers: list[Resolver]) -> None:
        self._resolvers = resolvers

    @property
    def validation_service(self) -> UrlValidationService | None:
        return self._validation_service

    async def _validate_stored_url(
        self,
        cached: ResolveResponse,
        purl_key: str,
    ) -> ResolveResponse | None:
        if self._validation_service is None:
            return cached
        app_settings = self._settings_store.load()
        if not app_settings.validate_db_urls:
            return cached

        voutput = await self._validation_service.validate_url(
            cached.repository_url,
            app_settings.url_validation_timeout,
        )

        if voutput.result == UrlValidationResult.VALID:
            new_url = voutput.final_url or cached.repository_url
            if new_url != cached.repository_url:
                logger.info("Updated repository URL for %s: %s -> %s", purl_key, cached.repository_url, new_url)
                cached.repository_url = new_url
                try:
                    await self._storage.store(cached)
                except Exception:
                    logger.warning("Failed to update stored URL for %s", purl_key, exc_info=True)
            return cached

        if voutput.result == UrlValidationResult.INVALID:
            logger.warning("Cached URL %s is invalid for %s, deleting", cached.repository_url, purl_key)
            try:
                await self._storage.delete_purls([purl_key])
            except Exception:
                logger.warning("Failed to delete invalid cached URL for %s", purl_key, exc_info=True)
            return None

        return cached  # NETWORK_ERROR / RATE_LIMITED — keep

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
                logger.info("Resolution cache hit for %s", purl_key)
                validated = await self._validate_stored_url(cached, purl_key)
                if validated is not None:
                    validated.found_by = "local_db"
                    return ResolveResult.ok(validated)
        except Exception:
            logger.warning(
                "Resolution cache lookup failed for %s, falling through to resolver",
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

            if self._validation_service is not None:
                app_settings = self._settings_store.load()
                if app_settings.validate_db_urls:
                    voutput = await self._validation_service.validate_url(
                        repo_url,
                        app_settings.url_validation_timeout,
                    )
                    if voutput.result == UrlValidationResult.INVALID:
                        logger.warning(
                            "URL %s from resolver %s is invalid, skipping",
                            repo_url, r.name,
                        )
                        continue
                    if voutput.result == UrlValidationResult.NETWORK_ERROR:
                        logger.warning(
                            "URL validation inconclusive for %s (resolver=%s, result=%s), accepting anyway",
                            repo_url, r.name, voutput.result.value,
                        )
                    repo_url = voutput.final_url or repo_url

            response = ResolveResponse(
                purl=purl_key,
                repository_url=repo_url,
                warnings=list(resolution.warnings),
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

    async def _resolve_concurrent(
        self,
        purls: list[str],
        resolver: str = "",
        on_progress: Callable[[int, int], Awaitable[None]] | None = None,
    ) -> list[ResolveResult]:
        if self._settings_store is not None:
            batch_limit = self._settings_store.load().batch_semaphore_limit
        else:
            batch_limit = _BATCH_SEMAPHORE_LIMIT
        semaphore = asyncio.Semaphore(batch_limit)

        resolve_sources: list[str] = []
        source_index: dict[str, int] = {}
        per_input: list[int] = []
        for original in purls:
            key = safe_normalize(original)
            if key not in source_index:
                source_index[key] = len(resolve_sources)
                resolve_sources.append(original)
            per_input.append(source_index[key])

        async def _resolve_one(original: str) -> ResolveResult:
            async with semaphore:
                return await self.resolve_purl(original, resolver=resolver)

        unique_results = await asyncio.gather(*[_resolve_one(p) for p in resolve_sources])
        results = [unique_results[idx] for idx in per_input]

        if on_progress is not None:
            total = len(purls)
            counter = itertools.count(1)
            for _ in results:
                await on_progress(next(counter), total)

        return results

    async def resolve_many(
        self,
        purls: list[str],
        resolver: str = "",
    ) -> list[ResolveResult]:
        return await self._resolve_concurrent(purls, resolver=resolver)

    async def resolve_batch(
        self,
        purls: list[str],
        resolver: str = "",
        on_progress: Callable[[int, int], Awaitable[None]] | None = None,
    ) -> dict[str, ResolveResponse]:
        results = await self._resolve_concurrent(
            purls, resolver=resolver, on_progress=on_progress
        )
        batch: dict[str, ResolveResponse] = {}
        for original, result in zip(purls, results):
            if result.response is None or not result.response.repository_url:
                continue
            batch[safe_normalize(original)] = result.response
        return batch

    async def store_preexisting_references(
        self,
        components: list[SbomComponent],
        resolver: str = "",
    ) -> None:
        for comp in components:
            if comp.needs_enrichment:
                continue
            vcs_refs = [ref for ref in comp.existing_references if ref.get("type") == "vcs" and ref.get("url")]
            if not vcs_refs:
                continue
            purl_key = safe_normalize(comp.purl)
            try:
                existing = await self._storage.lookup(purl_key)
            except Exception:
                existing = None
            if existing is None:
                await self._storage.store(ResolveResponse(
                    purl=purl_key,
                    repository_url=vcs_refs[0]["url"],
                    resolver=resolver,
                ))


