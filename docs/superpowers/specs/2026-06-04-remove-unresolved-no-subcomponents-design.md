# Design: Remove Unresolved Components Without Subcomponents

## Problem

During SBOM enrichment, some components cannot be matched to a repository URL via purl2repo. Currently these unresolved components remain in the SBOM with no VCS references. For compliance (FSTEC requirements), every component must have a VCS or source-distribution reference. Components that cannot be resolved and have no sub-components are effectively "dead weight" — they cannot satisfy the requirement and inflate the SBOM.

## Goal

Add an opt-in option to the SBOM enrichment page that removes components meeting **both** criteria:

1. `needs_enrichment = True` (no existing VCS/source-distribution external reference)
2. `has_subcomponents = False` (no nested `components` list)
3. Not resolved during enrichment (PURL not found in `resolved` dict)

When the option is disabled (default), current behavior is preserved.

## Design

### 1. Collector: `has_subcomponents` field

**File:** `src/purl_resolver/sbom/collector.py`

Add `has_subcomponents: bool` to `SbomComponent` dataclass. Computed during `_collect()` by checking whether `comp.get("components")` is a non-empty list.

```python
@dataclass
class SbomComponent:
    name: str
    version: str
    purl: str
    path: _COMPONENT_PATH
    needs_enrichment: bool
    has_subcomponents: bool = False
    existing_references: list[dict] = field(default_factory=list)
```

In `_collect()`:
```python
nested = comp.get("components")
has_subs = isinstance(nested, list) and len(nested) > 0
```

### 2. New module: `remover.py`

**File:** `src/purl_resolver/sbom/remover.py` (NEW)

Single function:

```python
def remove_unresolved_components(
    sbom: dict,
    components: list[SbomComponent],
    resolved: dict[str, str],
) -> list[dict]:
    """Remove components that are unresolved, have no subcomponents.

    Returns list of removed component info dicts.
    """
```

**Algorithm:**
1. Filter `components` to those where:
   - `needs_enrichment == True`
   - `has_subcomponents == False`
   - `safe_normalize(comp.purl) not in resolved`
2. Sort by path in **reverse** order (deepest paths first, then by descending index) — ensures removing a child doesn't shift indices of earlier siblings/parents
3. For each component, walk `comp.path` to reach the parent list, then `pop(path[-1])` if `path[-1]` is an `int`
4. Collect and return `[{purl, name, version}]` for removed components

### 3. Reporter: `removed` in report

**File:** `src/purl_resolver/sbom/reporter.py`

Add `removed: list[dict] = []` parameter to `build_report()`.

Report output changes:
```json
{
  "summary": {
    "total_purls": 10,
    "found": 8,
    "not_found": 1,
    "skipped": 0,
    "removed": 1
  },
  "results": [
    {"purl": "pkg:pypi/...", "status": "found", "repository_url": "..."},
    {"purl": "pkg:pypi/...", "status": "not_found", "repository_url": null},
    {"purl": "pkg:pypi/...", "status": "removed", "repository_url": null, "name": "...", "version": "..."}
  ]
}
```

### 4. Pipeline integration

**File:** `src/purl_resolver/sbom_enrichment.py`

`process()` gains parameter `remove_unresolved_no_subcomponents: bool = False`.

After `resolve_batch()` and `store_preexisting_references()`, if `True`:
```python
removed = []
if remove_unresolved_no_subcomponents:
    removed = remove_unresolved_components(sbom_data, components, resolved)
report = process_sbom(sbom_data, components, resolved, skipped=skipped, removed=removed)
```

Note: removal modifies `sbom_data` in-place (same pattern as `enricher.py`). The `sbom_data` dict passed to `process_sbom()` already has the removed components stripped out.

### 5. API endpoint

**File:** `src/purl_resolver/router.py`

Add form parameter to `resolve_sbom_endpoint`:

```python
async def resolve_sbom_endpoint(
    request: Request,
    file: UploadFile = File(...),
    remove_unresolved_no_subcomponents: bool = Form(False),
) -> JSONResponse:
```

Pass it through to pipeline:
```python
result = await pipeline.process(data, remove_unresolved_no_subcomponents=remove_unresolved_no_subcomponents)
```

### 6. Web UI

**File:** `src/purl_resolver/templates/sbom.html`

- Add checkbox `<input type="checkbox" id="remove-unresolved"> Удалять ненайденные компоненты без подкомпонентов` in toolbar next to "Обработать" button
- In `processBtn` click handler, append `remove_unresolved_no_subcomponents` to FormData
- In `renderResults()`, show `removed` summary card (yellow color like `skipped`)
- In results table, render `status: "removed"` with a distinct color (orange/yellow) and "Removed" label

## Files Changed

| File | Type | Change |
|---|---|---|
| `src/purl_resolver/sbom/collector.py` | Modify | Add `has_subcomponents` to `SbomComponent` |
| `src/purl_resolver/sbom/remover.py` | **New** | `remove_unresolved_components()` function |
| `src/purl_resolver/sbom/reporter.py` | Modify | Add `removed` parameter and `summary.removed` |
| `src/purl_resolver/sbom_enrichment.py` | Modify | Add `remove_unresolved_no_subcomponents` param, call remover |
| `src/purl_resolver/router.py` | Modify | Add `Form(False)` parameter |
| `src/purl_resolver/templates/sbom.html` | Modify | Checkbox + form-data + render removed |

## Testing

**IMPORTANT:** All Python commands MUST be run using the project's virtual environment:
```bash
.venv/bin/python ...
.venv/bin/pytest ...
```
Do NOT use system Python or bare `python`/`pytest` commands.

### Unit tests

- `tests/test_sbom_collector.py`: verify `has_subcomponents` is correctly computed for components with/without nested `components`
- `tests/test_sbom_remover.py` (NEW): test removal logic with various SBOM structures:
  - Flat SBOM (all components at top level, some unresolved)
  - Nested SBOM (components with subcomponents, some unresolved)
  - Mixed: parent with subcomponents (unresolved but kept) + children without references (removed)
  - Edge case: all components unresolved — verify correct subset removed
  - Edge case: no components need removal — verify SBOM unchanged
  - Verify removed components list contains correct `{purl, name, version}`
- `tests/test_sbom_reporter.py`: verify `removed` count appears in `summary.removed` and `status: "removed"` entries in `results[]`
- `tests/test_sbom_enricher.py`: verify `process_sbom()` passes `removed` list correctly to `build_report()`

### Integration tests

- `tests/test_sbom_integration.py`: end-to-end SBOM enrichment with `remove_unresolved_no_subcomponents=True`:
  - Use `sbom_example_missed_references.json` as test fixture
  - Verify components without VCS refs and without subcomponents are removed from enriched SBOM
  - Verify components WITH subcomponents are NOT removed even if unresolved
  - Verify response contains correct `summary.removed` count and `results[]` entries
  - Verify enriched SBOM JSON structure is valid CycloneDX after removal (version incremented, components array intact)

### SBOM validation tests

- Verify the enriched SBOM output is valid JSON with required CycloneDX fields (`bomFormat`, `specVersion`, `version`, `metadata`, `components`)
- Verify removed components no longer appear in `components` array at any nesting level
- Verify components that were NOT supposed to be removed are still present with correct data

## API Contract Changes

`POST /api/v1/resolve/sbom` gains optional form field:

```
remove_unresolved_no_subcomponents: boolean (default: false)
```

Response gains `summary.removed` (integer) and `results[]` entries with `status: "removed"`.

This is a **backward-compatible** addition — existing clients are unaffected (default is `false`).
