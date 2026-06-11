from __future__ import annotations

import logging
from dataclasses import dataclass

from .purl_utils import normalize, safe_normalize, validate
from .resolver.interface import Resolver
from .sbom.collector import _SOURCE_REF_TYPES, SbomComponent, collect_components
from .ignore_patterns_store import IgnorePatternsStore
from .url_validator import UrlValidationResult, validate_url
from .sbom.enricher import enrich_sbom
from .sbom.parser import CycloneDXParser, SbomParseError
from .sbom.remover import remove_unresolved_components
from .sbom.reporter import build_report
from .service import resolve_batch, store_preexisting_references
from .settings_store import SettingsStore
from .storage.interface import Storage

logger = logging.getLogger(__name__)


def _component_matches_any_pattern(
    sbom_data: dict,
    comp: SbomComponent,
    ignore_patterns: list[dict[str, str]],
) -> bool:
    if not ignore_patterns:
        return False
    target: dict = sbom_data
    for segment in comp.path:
        target = target[segment]
    for rule in ignore_patterns:
        field = rule.get("field", "")
        pattern = rule.get("pattern", "")
        if not field or not pattern:
            continue
        value = target.get(field)
        if value is not None and pattern in str(value):
            return True
    return False


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
        ignore_patterns_store: IgnorePatternsStore | None = None,
    ) -> None:
        self._storage = storage
        self._resolvers = resolvers
        self._settings_store = settings_store
        self._ignore_patterns_store = ignore_patterns_store

    async def process(
        self,
        sbom_data: dict,
        remove_unresolved_no_subcomponents: bool = False,
        validate_existing_refs: bool = False,
        ignore_patterns: list[dict[str, str]] | None = None,
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

        # --- Ignore patterns filtering ---
        if ignore_patterns:
            for comp in components:
                if not comp.needs_enrichment:
                    continue
                if _component_matches_any_pattern(sbom_data, comp, ignore_patterns):
                    comp.ignored = True
                    comp.needs_enrichment = False

        purls_to_resolve = [c for c in components if c.needs_enrichment]

        seen: set[str] = set()
        unique_purls: list[str] = []
        skipped = 0
        for comp in purls_to_resolve:
            try:
                n = normalize(validate(comp.purl))
            except Exception:
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
