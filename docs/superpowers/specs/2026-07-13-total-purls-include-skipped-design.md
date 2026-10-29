# Total PURLs — include all statuses, add skipped rows to results

## Problem

`total_purls` in SbomSummary currently excludes `ignored`, `removed`, and `skipped` statuses — it only counts `found + not_found`. This is misleading: the total should reflect all unique PURLs in the processed component set.

Components with `skipped` status (PURL validation error) don't appear in the results table at all — they're only a counter in the summary, hidden behind `v-if="skipped > 0"`.

## Changes

### 1. `reporter.py` — change `skipped` from int to list[dict]

```python
# Before
def build_report(
    components: list[SbomComponent],
    resolved: dict[str, ResolveResponse],
    skipped: int = 0,
    removed: list[dict] | None = None,
) -> dict:
```

```python
# After
def build_report(
    components: list[SbomComponent],
    resolved: dict[str, ResolveResponse],
    skipped: list[dict] | None = None,
    removed: list[dict] | None = None,
) -> dict:
```

Each dict in `skipped` has keys `purl`, `name`, `version` — matching the `removed` pattern.

**Result rows:** after the `removed` loop, add:

```python
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
```

**Total formula:**

```python
# Before
"total_purls": found_count + not_found_count,
# After
"total_purls": found_count + not_found_count + ignored_count + len(skipped) + len(removed),
```

### 2. `sbom_enrichment.py` — collect skipped component info

```python
# Before
skipped = 0
for comp in purls_to_resolve:
    try:
        n = normalize(validate(comp.purl))
    except Exception:
        skipped += 1
        continue

# After
skipped_comps: list[dict] = []
for comp in purls_to_resolve:
    try:
        n = normalize(validate(comp.purl))
    except Exception:
        skipped_comps.append({"purl": comp.purl, "name": comp.name, "version": comp.version})
        continue
```

Pass `skipped=skipped_comps` to `build_report()`.

### 3. Frontend — `SbomUpdater.vue`

Add CSS class for skipped badge:

```css
.status-skipped {
  background: var(--color-table-header-bg);
  color: var(--color-muted-light);
}
```

i18n keys `status.skipped` already exist in both locales.

### 4. Summary cards — always show all statuses

Remove `v-if="... > 0"` from Skipped, Removed, and Ignored cards in `SbomUpdater.vue` so all six summary cards are always visible for a completed job — even with value 0. Currently `v-if` hides cards with zero values, which is confusing since the user doesn't know whether a status was absent or just not tracked.

**Lines to change (SbomUpdater.vue template):**
- Line 89: `v-if="activeJob.summary.skipped > 0"` → remove attribute
- Line 96: `v-if="activeJob.summary.removed > 0"` → remove attribute
- Line 103: `v-if="activeJob.summary.ignored > 0"` → remove attribute

## Test impact

Existing tests in `test_sbom_reporter.py` that assert `total_purls` values need updating:

- `test_build_report_ignored_not_counted_in_total`: `total_purls` changes from 0 → 1 (ignored now counts toward total)
- Any test where ignored/removed components exist and `total_purls` is hardcoded

## Key Files

- `src/purl_resolver/sbom/sbom_enrichment.py` — skipped component collection
- `src/purl_resolver/sbom/reporter.py` — build_report signature, results, total formula
- `frontend/src/views/SbomUpdater.vue` — CSS class for skipped badge
