from __future__ import annotations

import logging
from dataclasses import dataclass

from .purl_utils import safe_normalize
from .resolver.interface import Resolver
from .sbom.collector import _SOURCE_REF_TYPES, collect_components
from .url_validator import UrlValidationResult, validate_url
from .sbom.enricher import enrich_sbom
from .sbom.parser import CycloneDXParser, SbomParseError
from .sbom.remover import remove_unresolved_components
from .sbom.reporter import build_report
from .service import resolve_batch, store_preexisting_references
from .settings_store import SettingsStore
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
        settings_store: SettingsStore | None = None,
    ) -> None:
        self._storage = storage
        self._resolvers = resolvers
        self._settings_store = settings_store

    async def process(
        self,
        sbom_data: dict,
        remove_unresolved_no_subcomponents: bool = False,
        validate_existing_refs: bool = False,
    ) -> SbomEnrichmentResult:
        """Parse, collect, deduplicate, resolve, enrich, and report."""
        CycloneDXParser.parse(sbom_data)

        components = collect_components(sbom_data)

        if validate_existing_refs:
            for comp in components:
                if comp.needs_enrichment:
                    continue
                for ref in comp.existing_references:
                    if ref.get("type") in _SOURCE_REF_TYPES and ref.get("url"):
                        vresult = await validate_url(
                            ref["url"],
                            timeout=5,
                            github_token=None,
                        )
                        if vresult == UrlValidationResult.INVALID:
                            comp.needs_enrichment = True
                            comp.existing_references = []
                        break

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

        removed: list[dict] = []
        enrich_sbom(sbom_data, components, resolved)

        if remove_unresolved_no_subcomponents:
            removed = remove_unresolved_components(sbom_data, components, resolved)

        report = build_report(components, resolved, skipped=skipped, removed=removed)

        return SbomEnrichmentResult(
            report=report,
            enriched_sbom=sbom_data,
        )
