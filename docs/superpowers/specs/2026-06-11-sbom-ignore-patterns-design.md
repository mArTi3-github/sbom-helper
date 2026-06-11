# Spec: Ignore Patterns for SBOM Updater

**Date:** 2026-06-11
**Status:** Draft

## Overview

Add a filtering mechanism to the SBOM Updater that allows users to define patterns for excluding components from enrichment processing. Components matching any of the defined patterns are marked as "Ignored" instead of being resolved.

## Storage

- **File:** `data/sbom_components_ignore_patterns.json`
- **Format:** `[{"field": "purl", "pattern": "test"}, ...]`
- If file does not exist — no patterns are applied (empty list).
- Pattern: conventions follow `data/settings.json` (JSON file, read/written by a dedicated store class).

## API Endpoints

### `GET /api/v1/sbom/ignore-patterns`

- Reads `data/sbom_components_ignore_patterns.json`
- Returns `{"patterns": [{"field": "purl", "pattern": "test"}, ...]}`
- On missing file — returns `{"patterns": []}`

### `POST /api/v1/sbom/ignore-patterns`

- Accepts `{"patterns": [{"field": "purl", "pattern": "test"}, ...]}`
- Overwrites `data/sbom_components_ignore_patterns.json` with the provided array.
- Returns `{"status": "saved"}`

### Modified: `POST /api/v1/resolve/sbom`

- New optional form field: `ignore_patterns: str = Form(None)` — JSON string of `[{"field": "purl", "pattern": "test"}, ...]`
- Passed to `SbomEnrichmentPipeline.process()`.

## Backend: `SbomComponent` changes (`sbom/collector.py`)

Add field to `SbomComponent` dataclass:

```python
ignored: bool = False
```

## Backend: Pipeline changes (`sbom_enrichment.py`)

New step in `SbomEnrichmentPipeline.process()` after `collect_components()` and optional ref validation, before building the PURL list:

1. Accept `ignore_patterns: list[dict[str, str]]` parameter.
2. If empty — skip filtering.
3. For each `SbomComponent` in the flat list:
   - Navigate to the component dict in the SBOM tree via `comp.path`.
   - For each pattern `{field, pattern}`:
     - Get `component_dict.get(field)` — returns value or `None`.
     - If value exists and `pattern in str(value)` (substring match):
       - Set `comp.needs_enrichment = False`
       - Set `comp.ignored = True`
       - Break (no need to check other patterns for this component).
4. Components with `ignored=True` are excluded from the resolution PURL list.
5. **Independence rule:** Each component is checked against patterns independently. Ignoring a parent does NOT automatically ignore its children — children are evaluated separately.

## Backend: Reporter changes (`sbom/reporter.py`)

- `build_report()` now iterates components with `ignored=True` and adds them to results with status `"ignored"`.
- Summary gains an `"ignored"` counter.
- Results entries for ignored components include `name` and `version` from `SbomComponent` for clarity.

## Backend: New module `ignore_patterns_store.py`

```python
class IgnorePatternsStore:
    def __init__(self, path: str | Path = "./data/sbom_components_ignore_patterns.json")
    def load(self) -> list[dict[str, str]]
    def save(self, patterns: list[dict[str, str]]) -> None
```

## Frontend: UI changes (`sbom.html`)

New subsection is rendered after the checkboxes and before the results section:

```
Игнорировать компоненты с перечисленными признаками:

  [purl       ] содержит [test                 ]
    или
  [group      ] содержит [test                 ]
    или
  [___________] содержит [_____________________]

[Сохранить]
```

Behavior:
- On page load: `GET /api/v1/sbom/ignore-patterns` — renders saved patterns as rows.
- An empty row with blank inputs is always present at the bottom.
- When user types into any field of the last empty row, a new empty row is added below it.
- Between rows: a visual "или" (or) line (non-interactive, CSS-styled).
- "Сохранить" button: `POST /api/v1/sbom/ignore-patterns` with current UI state.
- On "Обработать": patterns from UI are serialized to JSON and added to FormData as `ignore_patterns`.
- Visual style matches the rest of the page: consistent spacing, border-radius, font, color scheme (primary `#2563eb`).

## Results Table

Ignored components appear in the results table with:
- Status: `"Ignored"` (class `status-ignored`)
- Color: muted/gray (`#6b7280` suggested)
- Repository URL: `—`
- Summary includes `ignored` count

## Files Changed

| File | Change |
|---|---|
| `src/purl_resolver/sbom/collector.py` | Add `ignored: bool` field to `SbomComponent` |
| `src/purl_resolver/sbom_enrichment.py` | Add ignore-patterns filtering step in `process()` |
| `src/purl_resolver/sbom/reporter.py` | Add `"ignored"` status handling |
| `src/purl_resolver/routes/resolve.py` | Add `ignore_patterns` form field, pass to pipeline |
| `src/purl_resolver/templates/sbom.html` | Add UI subsection, auto-load, save logic |
| `src/purl_resolver/router.py` | Register new ignore-patterns routes |

**New files:**
| `src/purl_resolver/ignore_patterns_store.py` | Read/write `data/sbom_components_ignore_patterns.json` |
| (routes likely inline in router or a dedicated route file) | API endpoints for GET/POST ignore-patterns |

**Data file** (created at runtime):
| `data/sbom_components_ignore_patterns.json` | Persisted ignore patterns |

## Test Strategy

- Unit test for ignore patterns matching (substring contains, case-sensitive).
- Unit test for reporter with ignored components.
- Integration test with `sbom_example_missed_references.json`:
  - Patterns `[{"field": "purl", "pattern": "test"}, {"field": "group", "pattern": "test"}]`
  - `configure_interfaces-amd64` (purl contains "test") should be ignored.
  - Children (`altgraph`, `black`, etc.) should NOT be ignored — they are processed normally.