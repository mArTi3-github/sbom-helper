from __future__ import annotations

from .collector import SbomComponent
from ..purl_utils import safe_normalize


def _has_resolved_sibling(
    sbom: dict,
    comp: SbomComponent,
    resolved: dict[str, str],
) -> bool:
    obj: object = sbom
    for k in comp.path[:-1]:
        if isinstance(k, int):
            assert isinstance(obj, list)
            obj = obj[k]
        else:
            assert isinstance(obj, dict)
            obj = obj[k]

    if not isinstance(obj, list):
        return False

    for sibling in obj:
        purl = sibling.get("purl")
        if purl and safe_normalize(purl) in resolved:
            return True

    return False


def remove_unresolved_components(
    sbom: dict,
    components: list[SbomComponent],
    resolved: dict[str, str],
) -> list[dict]:
    candidates = [
        c for c in components
        if c.needs_enrichment
        and not c.has_subcomponents
        and safe_normalize(c.purl) not in resolved
    ]

    to_remove = []
    for c in candidates:
        if len(c.path) == 2 or _has_resolved_sibling(sbom, c, resolved):
            to_remove.append(c)

    to_remove.sort(key=lambda c: c.path, reverse=True)

    removed: list[dict] = []
    for comp in to_remove:
        obj: object = sbom
        for k in comp.path[:-1]:
            if isinstance(k, int):
                assert isinstance(obj, list)
                obj = obj[k]
            else:
                assert isinstance(obj, dict)
                obj = obj[k]

        idx = comp.path[-1]
        if isinstance(idx, int) and isinstance(obj, list):
            obj.pop(idx)
            removed.append({"purl": comp.purl, "name": comp.name, "version": comp.version})

    return removed
