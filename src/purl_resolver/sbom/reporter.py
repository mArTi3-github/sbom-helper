from __future__ import annotations

from .collector import SbomComponent
from ..purl_utils import safe_normalize
from ..schemas import ResolveResponse


def build_report(
    components: list[SbomComponent],
    resolved: dict[str, ResolveResponse],
    skipped: int = 0,
    removed: list[dict] | None = None,
) -> dict:
    if removed is None:
        removed = []
    removed_keys = {safe_normalize(r["purl"]) for r in removed}
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
        if key in removed_keys:
            continue
        resp = resolved.get(key)
        repo_url = resp.repository_url if resp is not None else None
        if repo_url is not None:
            found_count += 1
            results.append({"purl": key, "status": "found", "repository_url": repo_url})
        else:
            not_found_count += 1
            results.append({"purl": key, "status": "not_found", "repository_url": None})

    for r in removed:
        results.append({
            "purl": r["purl"],
            "status": "removed",
            "repository_url": None,
            "name": r["name"],
            "version": r["version"],
        })

    return {
        "summary": {
            "total_purls": found_count + not_found_count,
            "found": found_count,
            "not_found": not_found_count,
            "skipped": skipped,
            "removed": len(removed),
        },
        "results": results,
    }