from __future__ import annotations

from ..purl_utils import safe_normalize
from ..schemas import ResolveResponse
from .collector import SbomComponent


def remove_unresolved_components(
    sbom: dict,
    components: list[SbomComponent],
    resolved: dict[str, ResolveResponse],
) -> list[dict]:
    to_remove = [
        c for c in components
        if c.needs_enrichment
        and not c.has_subcomponents
        and safe_normalize(c.purl) not in resolved
    ]

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
