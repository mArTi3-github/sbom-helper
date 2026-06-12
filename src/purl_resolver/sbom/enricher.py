from __future__ import annotations

from ..purl_utils import safe_normalize
from ..schemas import ResolveResponse
from .collector import SbomComponent


def enrich_sbom(
    sbom: dict,
    components: list[SbomComponent],
    resolved: dict[str, ResolveResponse],
) -> None:
    for comp in components:
        if not comp.needs_enrichment:
            continue
        key = safe_normalize(comp.purl)
        resp = resolved.get(key)
        if resp is None:
            continue
        repo_url = resp.repository_url

        obj: object = sbom
        for k in comp.path:
            if isinstance(k, int):
                assert isinstance(obj, list)
                obj = obj[k]
            else:
                assert isinstance(obj, dict)
                obj = obj[k]

        assert isinstance(obj, dict)
        new_ref = {"type": "vcs", "url": repo_url}
        obj["externalReferences"] = list(comp.existing_references) + [new_ref]

    sbom["version"] = sbom.get("version", 0) + 1
