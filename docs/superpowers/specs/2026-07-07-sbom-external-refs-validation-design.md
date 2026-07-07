# SBOM External References Validation — Design

## Problem Summary

When `validate_sbom_refs` is enabled in Settings, the SBOM Updater validates pre-existing `externalReferences` found in SBOM components. The current implementation has two bugs:

1. **Unconditional `break`** — The inner loop over `existing_references` fires `break` after the first iteration regardless of whether the reference's `type` matched `SOURCE_REF_TYPES`. If a non-VCS reference (e.g. `website`) appears before a VCS reference, the VCS reference is never validated.

2. **All-or-nothing clearance** — When a VCS ref is found invalid, `comp.existing_references` is set to `[]` (clearing all refs including non-VCS ones) and the component is immediately marked for re-resolution. There is no support for multiple VCS refs.

## Scope

This design covers:

- New validation phase `_validate_external_references` in `SbomEnrichmentPipeline`
- New setting `sbom_multiple_vcs_behavior` (`keep-first` / `keep-all`)
- Frontend UI for the new setting
- Fix to `service.py:store_preexisting_references` (clean up filter expression)
- Removal of dead `RATE_LIMITED` check in `service.py`
- Corresponding tests

## Architecture

### Processing order (unchanged from current)

```
CycloneDXParser.parse(sbom_data)
        ↓
collect_components(sbom_data)
        ↓
ignore_patterns (components matching pattern → comp.ignored = True)
        ↓
validate_external_references ← NEW PHASE (if validate_sbom_refs=True)
        ↓
resolve_batch(purls_to_resolve)
        ↓
store_preexisting_references
        ↓
enrich_sbom
        ↓
build_report
```

The new phase is placed **after** ignore_patterns so that ignored components are skipped entirely.

## Detailed Design

### 1. Backend: `AppSettings` — new field

**File:** `src/purl_resolver/settings_store.py`

```python
class AppSettings(BaseModel):
    validate_db_urls: bool = False
    validate_sbom_refs: bool = False
    sbom_multiple_vcs_behavior: str = Field(default="keep-first", pattern="^(keep-first|keep-all)$")
    # ... existing fields unchanged ...
```

- Default: `"keep-first"`
- When `validate_sbom_refs = False`, this field is stored but has no effect on SBOM processing

### 2. Backend: Settings API

**File:** `src/purl_resolver/routes/settings.py`

**`SettingsUpdate`** — new optional field:
```python
sbom_multiple_vcs_behavior: str | None = Field(None, pattern="^(keep-first|keep-all)$")
```

**GET `/api/v1/settings`** — include in response:
```python
"sbom_multiple_vcs_behavior": app_settings.sbom_multiple_vcs_behavior,
```

**PATCH `/api/v1/settings`** — include in response:
```python
"sbom_multiple_vcs_behavior": updated.sbom_multiple_vcs_behavior,
```

When `sbom_multiple_vcs_behavior` is sent in PATCH while `validate_sbom_refs = False`, the value is stored but has no effect (defensive: the UI already disables the selector when the toggle is off).

### 3. Backend: New validation phase

**File:** `src/purl_resolver/sbom_enrichment.py`

New method on `SbomEnrichmentPipeline`:

```python
async def _validate_external_references(
    self, components: list[SbomComponent], app_settings: AppSettings
) -> None:
```

#### Algorithm

```
for each comp in components:
    if comp.ignored:
        continue

    # Step 1 — classify refs
    vcs_refs     = [r for r in comp.existing_references if r["type"] == "vcs" and r.get("url")]
    other_refs   = [r for r in comp.existing_references if not (r["type"] == "vcs" and r.get("url"))]

    # Step 2 — validate each VCS ref
    valid_vcs = []
    for ref in vcs_refs:
        voutput = await validation_service.validate_url(...)  # or validate_url_with_retry
        if voutput.result in (UrlValidationResult.INVALID, UrlValidationResult.NETWORK_ERROR):
            logger.info("Removed VCS ref %s for %s (reason=%s)", ref["url"], comp.purl, voutput.result.value)
            continue
        if voutput.final_url and voutput.final_url != ref["url"]:
            ref["url"] = voutput.final_url
        valid_vcs.append(ref)

    # Step 3 — apply keep-first if 2+ valid
    if len(valid_vcs) >= 2 and app_settings.sbom_multiple_vcs_behavior == "keep-first":
        for extra in valid_vcs[1:]:
            logger.info("Removed extra valid VCS ref %s for %s (keep-first)", extra["url"], comp.purl)
        valid_vcs = valid_vcs[:1]

    # Step 4 — rebuild existing_references
    comp.existing_references = other_refs + valid_vcs

    # Step 5 — decide enrichment
    if not valid_vcs:
        comp.needs_enrichment = True
```

#### Changes to `process()`

The old validation loop (current lines 69-89) is **removed entirely** and replaced with:

```python
if settings:
    app_settings = settings.load()
    if app_settings.validate_sbom_refs:
        await self._validate_external_references(components, app_settings)
```

### 4. Backend: `store_preexisting_references` cleanup

**File:** `src/purl_resolver/service.py`

Replace the inner for/break with a direct list comprehension + index access:

```python
async def store_preexisting_references(
    self,
    components: list[SbomComponent],
    resolver: str = "",
) -> None:
    for comp in components:
        if comp.needs_enrichment:
            continue
        vcs_refs = [ref for ref in comp.existing_references if ref.get("type") == "vcs" and ref.get("url")]
        if not vcs_refs:
            continue
        purl_key = safe_normalize(comp.purl)
        try:
            existing = await self._storage.lookup(purl_key)
        except Exception:
            existing = None
        if existing is None:
            await self._storage.store(ResolveResponse(
                purl=purl_key,
                repository_url=vcs_refs[0]["url"],
                evidence=["from SBOM externalReferences"],
                resolver=resolver,
            ))
```

Always stores the **first** VCS ref regardless of `sbom_multiple_vcs_behavior` — the local DB schema stores one URL per PURL.

### 5. Backend: Remove dead `RATE_LIMITED` check

**File:** `src/purl_resolver/service.py` (line 134)

```python
# Before:
if voutput.result in (UrlValidationResult.NETWORK_ERROR, UrlValidationResult.RATE_LIMITED):

# After:
if voutput.result == UrlValidationResult.NETWORK_ERROR:
```

`RATE_LIMITED` is defined in the `UrlValidationResult` enum but never returned by `validate_url()`. Removing the dead branch.

### 6. Backend: `enrich_sbom` — no changes

**File:** `src/purl_resolver/sbom/enricher.py`

No changes needed. The existing code:

```python
obj["externalReferences"] = list(comp.existing_references) + [new_ref]
```

Is correct because:
- After validation, `comp.existing_references` contains only non-VCS refs + valid VCS refs (possibly pruned to 1)
- If 0 valid VCS refs remain → `needs_enrichment = True` → enricher appends the resolved URL
- If 1+ valid VCS refs remain → `needs_enrichment = False` → enricher skips the component

### 7. Frontend: Settings UI

**File:** `frontend/src/views/Settings.vue`

New element below the "Validate pre-existing URLs from SBOM" toggle:

```html
<div class="setting-row" :class="{ 'setting-disabled': !validateSbomRefs }">
  <div>
    <div class="setting-label">Behavior when multiple valid VCS-links are found</div>
    <div class="setting-desc">
      When multiple VCS references are valid, choose whether to keep only the
      first one or keep all of them in the SBOM.
    </div>
  </div>
  <select
    v-model="sbomMultipleVcsBehavior"
    :disabled="!validateSbomRefs"
    @change="debouncedAutoSave({ sbom_multiple_vcs_behavior: sbomMultipleVcsBehavior })"
    class="select-input"
  >
    <option value="keep-first">keep only first</option>
    <option value="keep-all">keep all</option>
  </select>
</div>
```

CSS class `.setting-disabled` applies reduced opacity when the parent toggle is off.

**File:** `frontend/src/types/api.ts`

```typescript
export interface SettingsResponse {
  // ...
  sbom_multiple_vcs_behavior: string
}

export interface SettingsUpdate {
  // ...
  sbom_multiple_vcs_behavior?: string
}
```

**File:** `frontend/src/stores/useSettingsStore.ts`

```typescript
const sbomMultipleVcsBehavior = ref('keep-first')

// in load():
sbomMultipleVcsBehavior.value = data.sbom_multiple_vcs_behavior

// in return:
sbomMultipleVcsBehavior
```

### 8. `SOURCE_REF_TYPES` — no changes

**File:** `src/purl_resolver/sbom/collector.py`

`SOURCE_REF_TYPES = frozenset({"vcs", "source-distribution"})` remains unchanged. The collector uses it to determine initial `needs_enrichment`. The new validation phase operates independently and re-evaluates `needs_enrichment` based only on `vcs` refs.

### 9. Logging

| Event | Level | Location |
|---|---|---|
| VCS ref removed (INVALID or NETWORK_ERROR) | `INFO` | `_validate_external_references` |
| Extra valid VCS ref removed (keep-first) | `INFO` | `_validate_external_references` |

## Files Changed

| File | Change |
|------|--------|
| `src/purl_resolver/settings_store.py` | Add `sbom_multiple_vcs_behavior` field to `AppSettings` |
| `src/purl_resolver/routes/settings.py` | Add field to `SettingsUpdate`, GET response, PATCH response |
| `src/purl_resolver/sbom_enrichment.py` | Replace validation loop with `_validate_external_references()` |
| `src/purl_resolver/service.py` | Clean up `store_preexisting_references`; remove `RATE_LIMITED` check |
| `frontend/src/types/api.ts` | Add `sbom_multiple_vcs_behavior` to `SettingsResponse` and `SettingsUpdate` |
| `frontend/src/stores/useSettingsStore.ts` | Add `sbomMultipleVcsBehavior` ref |
| `frontend/src/views/Settings.vue` | Add dropdown for the new setting |
| `frontend/src/views/Settings.test.ts` | Add `sbom_multiple_vcs_behavior: 'keep-first'` to default mock response |
| `tests/test_sbom_integration.py` | Update tests for new validation behavior; add `keep-all` test case |
| `tests/test_service_validation.py` | Remove `RATE_LIMITED` assertions |

## Testing Strategy

| Scenario | Expected |
|---|---|
| Component with `[vcs_valid, vcs_valid]` + default (`keep-first`) | Only first VCS retained, second removed (INFO log) |
| Component with `[vcs_valid, vcs_valid]` + `keep-all` | Both VCS retained |
| Component with `[website, vcs_invalid, vcs_valid]` | Website kept, invalid removed, valid retained; 1 valid → no enrichment |
| Component with `[vcs_invalid, vcs_invalid]` | Both removed, `needs_enrichment = True` |
| Component with `[vcs_network_error]` | Ref removed (INFO log), `needs_enrichment = True` |
| Component with `[source-distribution, vcs_valid]` | source-distribution kept, VCS retained, no enrichment |
| Ignored component with VCS refs | Skipped by validation phase, unchanged |
| `store_preexisting_references` with `keep-all` | Only first VCS stored in DB |
| `RATE_LIMITED` usage removed | No references to `RATE_LIMITED` in `service.py` |

## Invariants

- Non-VCS refs (`website`, `documentation`, `issue-tracker`, `source-distribution`, etc.) are **never removed** by the validation phase
- `source-distribution` refs are preserved but not validated (will be handled in a future iteration)
- The validation phase runs on **all** components (not just `needs_enrichment = False`), but skipped for `ignored` components
- After validation, `comp.needs_enrichment` is always `True` if 0 valid VCS refs remain, otherwise unchanged
- `enrich_sbom` has no logic changes — it appends the resolved URL to whatever `existing_references` remains