from __future__ import annotations

import logging
from dataclasses import dataclass

from .purl_utils import normalize, validate
from .sbom.collector import SbomComponent, collect_components
from .sbom.enricher import enrich_sbom
from .sbom.parser import CycloneDXParser
from .sbom.remover import remove_unresolved_components
from .sbom.reporter import build_report
from .service import PurlResolutionService
from .settings_store import AppSettings
from .url_validator import UrlValidationOutput, UrlValidationResult, validate_url_with_retry

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
        resolution_service: PurlResolutionService,
    ) -> None:
        self._resolution_service = resolution_service

    async def _validate_external_references(
        self,
        components: list[SbomComponent],
        app_settings: AppSettings,
    ) -> None:
        val_timeout = app_settings.url_validation_timeout
        val_token = app_settings.github_token
        behavior = app_settings.sbom_multiple_vcs_behavior

        for comp in components:
            if comp.ignored:
                continue

            vcs_refs: list[dict] = []
            other_refs: list[dict] = []
            for ref in comp.existing_references:
                if ref.get("type") == "vcs" and ref.get("url"):
                    vcs_refs.append(ref)
                else:
                    other_refs.append(ref)

            valid_vcs: list[dict] = []
            for ref in vcs_refs:
                vs = self._resolution_service.validation_service
                if vs is not None:
                    voutput = await vs.validate_url(ref["url"], timeout=val_timeout, github_token=val_token)
                else:
                    voutput = await validate_url_with_retry(
                        ref["url"], timeout=val_timeout, github_token=val_token,
                    )
                if voutput.result in (UrlValidationResult.INVALID, UrlValidationResult.NETWORK_ERROR):
                    logger.info("Removed VCS ref %s for %s (reason=%s)", ref["url"], comp.purl, voutput.result.value)
                    continue
                if voutput.final_url and voutput.final_url != ref["url"]:
                    ref["url"] = voutput.final_url
                valid_vcs.append(ref)

            if len(valid_vcs) >= 2 and behavior == "keep-first":
                for extra in valid_vcs[1:]:
                    logger.info("Removed extra valid VCS ref %s for %s (keep-first)", extra["url"], comp.purl)
                valid_vcs = valid_vcs[:1]

            comp.existing_references = other_refs + valid_vcs

            if not valid_vcs:
                comp.needs_enrichment = True

    async def process(
        self,
        sbom_data: dict,
        remove_unresolved_no_subcomponents: bool = False,
        ignore_patterns: list[dict[str, str]] | None = None,
    ) -> SbomEnrichmentResult:
        """Parse, collect, deduplicate, resolve, enrich, and report."""
        CycloneDXParser.parse(sbom_data)

        components = collect_components(sbom_data)

        # --- Ignore patterns filtering (before validation) ---
        if ignore_patterns:
            for comp in components:
                if _component_matches_any_pattern(sbom_data, comp, ignore_patterns):
                    comp.ignored = True
                    comp.needs_enrichment = False

        settings = self._resolution_service.settings_store
        if settings:
            app_settings = settings.load()
            if app_settings.validate_sbom_refs:
                await self._validate_external_references(components, app_settings)
                # Sync filtered existing_references back to SBOM data
                # Components that go through validation but keep valid VCS refs
                # (no enrichment needed) must have their filtered refs written back
                for comp in components:
                    if comp.ignored:
                        continue
                    obj: object = sbom_data
                    for k in comp.path:
                        if isinstance(k, int):
                            assert isinstance(obj, list)
                            obj = obj[k]
                        else:
                            assert isinstance(obj, dict)
                            obj = obj[k]
                    assert isinstance(obj, dict)
                    obj["externalReferences"] = list(comp.existing_references)

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

        resolved = await self._resolution_service.resolve_batch(
            unique_purls,
            resolver="import-sbom",
        )
        await self._resolution_service.store_preexisting_references(
            components, resolver="import-sbom"
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
