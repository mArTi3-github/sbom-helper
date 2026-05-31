from __future__ import annotations

from .collector import SbomComponent
from ..purl_utils import safe_normalize


def enrich_sbom(
    sbom: dict,
    components: list[SbomComponent],
    resolved: dict[str, str],
) -> None:
    for comp in components:
        if not comp.needs_enrichment:
            continue
        key = safe_normalize(comp.purl)
        repo_url = resolved.get(key)
        if repo_url is None:
            continue

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