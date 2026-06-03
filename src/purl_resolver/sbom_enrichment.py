from __future__ import annotations

import logging
from dataclasses import dataclass

from .purl_utils import safe_normalize
from .resolver.interface import Resolver
from .sbom.collector import collect_components
from .sbom.parser import CycloneDXParser, SbomParseError
from .service import process_sbom, resolve_batch, store_preexisting_references
from .storage.interface import Storage

logger = logging.getLogger(__name__)


@dataclass
class SbomEnrichmentResult:
    report: dict
    enriched_sbom: dict


class SbomEnrichmentPipeline:
    """Orchestrates the full CycloneDX SBOM enrichment workflow."""

    def __init__(
        self,
        storage: Storage,
        resolvers: list[Resolver],
        settings_store=None,
    ) -> None:
        self._storage = storage
        self._resolvers = resolvers
        self._settings_store = settings_store

    async def process(self, sbom_data: dict) -> SbomEnrichmentResult:
        """Parse, collect, deduplicate, resolve, enrich, and report."""
        CycloneDXParser.parse(sbom_data)

        components = collect_components(sbom_data)
        purls_to_resolve = [c for c in components if c.needs_enrichment]

        seen: set[str] = set()
        unique_purls: list[str] = []
        skipped = 0
        for comp in purls_to_resolve:
            n = safe_normalize(comp.purl)
            if n == comp.purl:
                skipped += 1
                continue
            if n not in seen:
                seen.add(n)
                unique_purls.append(comp.purl)

        resolved = await resolve_batch(
            unique_purls,
            self._storage,
            self._resolvers,
            settings_store=self._settings_store,
            resolver="import-sbom",
        )
        await store_preexisting_references(
            components, self._storage, resolver="import-sbom"
        )
        report = process_sbom(sbom_data, components, resolved, skipped=skipped)

        return SbomEnrichmentResult(
            report=report,
            enriched_sbom=sbom_data,
        )
