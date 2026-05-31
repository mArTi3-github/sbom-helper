from __future__ import annotations

from .collector import SbomComponent
from ..purl_utils import safe_normalize


def build_report(
    components: list[SbomComponent],
    resolved: dict[str, str],
    skipped: int = 0,
) -> dict:
    seen: set[str] = set()
    results: list[dict] = []
    found_count = 0
    not_found_count = 0

    for comp in components:
        if not comp.needs_enrichment:
            continue
        key = safe_normalize(comp.purl)
        if key in seen:
            continue
        seen.add(key)
        repo_url = resolved.get(key)
        if repo_url is not None:
            found_count += 1
            results.append({"purl": key, "status": "found", "repository_url": repo_url})
        else:
            not_found_count += 1
            results.append({"purl": key, "status": "not_found", "repository_url": None})

    return {
        "summary": {
            "total_purls": found_count + not_found_count,
            "found": found_count,
            "not_found": not_found_count,
            "skipped": skipped,
        },
        "results": results,
    }