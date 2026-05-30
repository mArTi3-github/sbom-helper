from __future__ import annotations

from dataclasses import dataclass, field

_SOURCE_REF_TYPES = frozenset({"vcs", "source-distribution"})

_COMPONENT_PATH = tuple[str | int, ...]


@dataclass
class SbomComponent:
    name: str
    version: str
    purl: str
    path: _COMPONENT_PATH
    needs_enrichment: bool
    existing_references: list[dict] = field(default_factory=list)


def _has_source_reference(component: dict) -> bool:
    refs = component.get("externalReferences")
    if not refs:
        return False
    return any(r.get("type") in _SOURCE_REF_TYPES for r in refs)


def _collect(
    components: list[dict],
    path_prefix: _COMPONENT_PATH,
    accumulator: list[SbomComponent],
) -> None:
    for i, comp in enumerate(components):
        purl = comp.get("purl")
        if not purl:
            continue

        current_path = (*path_prefix, i)
        needs = not _has_source_reference(comp)
        existing = comp.get("externalReferences", [])
        if not isinstance(existing, list):
            existing = []

        accumulator.append(
            SbomComponent(
                name=comp.get("name", ""),
                version=comp.get("version", ""),
                purl=purl,
                path=current_path,
                needs_enrichment=needs,
                existing_references=list(existing),
            )
        )

        nested = comp.get("components")
        if isinstance(nested, list):
            _collect(nested, (*current_path, "components"), accumulator)


def collect_components(sbom: dict) -> list[SbomComponent]:
    components = sbom.get("components", [])
    if not isinstance(components, list):
        return []
    result: list[SbomComponent] = []
    _collect(components, ("components",), result)
    return result