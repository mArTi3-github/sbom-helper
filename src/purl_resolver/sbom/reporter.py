from __future__ import annotations

from ..purl_utils import safe_normalize
from ..schemas import ResolveResponse
from .collector import SbomComponent


def build_report(
    components: list[SbomComponent],
    resolved: dict[str, ResolveResponse],
    skipped: list[dict] | None = None,
    removed: list[dict] | None = None,
) -> dict:
    if removed is None:
        removed = []
    if skipped is None:
        skipped = []
    removed_keys = {safe_normalize(r["purl"]) for r in removed}
    seen: set[str] = set()
    results: list[dict] = []
    found_count = 0
    not_found_count = 0
    ignored_count = 0

    for comp in components:
        if comp.ignored:
            key = safe_normalize(comp.purl)
            if key in seen:
                continue
            seen.add(key)
            ignored_count += 1
            results.append({
                "purl": key,
                "status": "ignored",
                "repository_url": None,
                "found_by": "",
                "resolver": "",
                "name": comp.name,
                "version": comp.version,
            })
            continue

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
            results.append({
                "purl": key,
                "status": "found",
                "repository_url": repo_url,
                "found_by": resp.found_by if resp else "",
                "resolver": resp.resolver if resp else "",
            })
        else:
            not_found_count += 1
            results.append({
                "purl": key,
                "status": "not_found",
                "repository_url": None,
                "found_by": "",
                "resolver": "",
            })

    for r in removed:
        results.append({
            "purl": r["purl"],
            "status": "removed",
            "repository_url": None,
            "found_by": "",
            "resolver": "",
            "name": r["name"],
            "version": r["version"],
        })

    for s in skipped:
        results.append({
            "purl": s["purl"],
            "status": "skipped",
            "repository_url": None,
            "found_by": "",
            "resolver": "",
            "name": s["name"],
            "version": s["version"],
        })

    return {
        "summary": {
            "total_purls": found_count + not_found_count + ignored_count + len(skipped) + len(removed),
            "found": found_count,
            "not_found": not_found_count,
            "skipped": len(skipped),
            "removed": len(removed),
            "ignored": ignored_count,
        },
        "results": results,
    }
