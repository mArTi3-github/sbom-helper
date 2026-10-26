# SBOM Fixing

## Description

Synchronous normalization of a CycloneDX SBOM JSON document. The domain applies an explicitly selected subset of 21 named rules, returns the fixed document together with per-rule statistics and a report of the defects that remain after the fixes were applied. It targets a fixed catalogue of formal defects (fields removed, `specVersion` set to `1.7`, external reference and property filters, optional GOST properties), not full FSTEC methodology compliance — producing a fully compliant SBOM is another service's responsibility. No database or background queue is involved. See `docs/superpowers/specs/2026-10-26-sbom-fixer-design.md` for the design rationale (git-ignored).

## Key Files

- `src/purl_resolver/sbom/fixer.py` — option models, the 21 rules, `fix_sbom()` orchestrator, `FixStat`, `FixIssue`, `SbomFixResult`, and the issue collector
- `src/purl_resolver/sbom/__init__.py` — public exports: `fix_sbom`, `SbomFixOptions`, `SbomFixResult`, `FixStat`, `FixIssue`
- `src/purl_resolver/sbom/parser.py` — `CycloneDXParser` / `SbomParseError`; validates the root object and `bomFormat == "CycloneDX"` before fixing
- `src/purl_resolver/sbom_fix_options_store.py` — `SbomFixOptionsStore`; JSON-file persistence of the option set
- `src/purl_resolver/routes/sbom_fix.py` — `POST /api/v1/sbom/fix`, `GET/POST /api/v1/sbom/fix/options`
- `src/purl_resolver/router.py` — includes the `sbom_fix` sub-router
- `src/purl_resolver/main.py` — creates `app.state.sbom_fix_options_store = SbomFixOptionsStore()` in the lifespan
- `frontend/src/views/SbomFixer.vue` — Fix SBOM page
- `frontend/src/api/sbom.ts` — `fixSbom()`, `getFixOptions()`, `saveFixOptions()`
- `frontend/src/types/api.ts` — `SbomFixOptions`, `SbomFixStat`, `SbomFixIssue`, `SbomFixResponse`, `SbomFixOptionsResponse`
- `tests/test_sbom_fixer.py` — rule, statistics, and issue unit tests
- `tests/test_sbom_fix_options_store.py` — store roundtrip and fallback tests
- `tests/test_sbom_fix_api.py` — endpoint tests

## Core Types

```python
ALLOWED_SPEC_VERSIONS = {"1.6", "1.7"}
SPEC_VERSION_PATTERN = re.compile(r"^\d+\.\d+$")

ROOT_PRIORITY = ("bomFormat", "specVersion", "serialNumber", "version",
                 "metadata", "components", "annotations")
METADATA_PRIORITY = ("timestamp", "component")
METADATA_COMPONENT_PRIORITY = ("type", "name", "version", "manufacturer")
COMPONENT_PRIORITY = ("type", "name", "version", "purl",
                      "externalReferences", "properties", "components")
ALLOWED_EXTERNAL_REFERENCE_TYPES = ("vcs", "source-distribution")
GOST_PROPERTY_PREFIX = "GOST:"
REQUIRED_GOST_PROPERTIES = (("GOST:attack_surface", "no"),
                            ("GOST:security_function", "no"))

class RootFixOptions(BaseModel):
    reorder: bool = True
    set_spec_version: bool = True
    spec_version: str = "1.7"          # must match ^\d+\.\d+$
    remove_dependencies: bool = True
    remove_services: bool = True
    increment_version: bool = True

class MetadataComponentFixOptions(BaseModel):
    reorder: bool = True
    remove_external_references: bool = True
    remove_properties: bool = True
    remove_purl: bool = False           # opt-in
    remove_scope: bool = True
    rename_supplier: bool = True

class MetadataFixOptions(BaseModel):
    add_timestamp: bool = True
    reorder: bool = True
    remove_properties: bool = True
    remove_tools: bool = True
    component: MetadataComponentFixOptions = Field(default_factory=MetadataComponentFixOptions)

class ComponentsFixOptions(BaseModel):
    reorder: bool = True
    remove_hashes: bool = True
    remove_scope: bool = True
    filter_external_references: bool = True
    filter_properties: bool = True
    fill_missing_gost_properties: bool = False  # opt-in

class SbomFixOptions(BaseModel):
    root: RootFixOptions = Field(default_factory=RootFixOptions)
    metadata: MetadataFixOptions = Field(default_factory=MetadataFixOptions)
    components: ComponentsFixOptions = Field(default_factory=ComponentsFixOptions)

@dataclass
class FixStat:
    rule_id: str
    count: int

@dataclass
class FixIssue:
    code: str
    path: str
    component: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

@dataclass
class SbomFixResult:
    changed: bool
    fixed_sbom: dict
    stats: list[FixStat]   # all enabled rules, canonical order, zeros included
    issues: list[FixIssue] # computed from fixed_sbom only
```

Default set: every option is `True` except `metadata_component.remove_purl` and `components.fill_missing_gost_properties` (both `False`); `spec_version` is `"1.7"`. With defaults `stats` contains 19 entries.

## Flow

```
HTTP client / SbomFixer.vue
  |
  | POST /api/v1/sbom/fix (multipart: file + options JSON string)
  v
routes/sbom_fix.py
  |-- size check (sbom_settings.max_file_size)      -> 413 file_too_large
  |-- json.loads(raw)                               -> 400 invalid_json
  |-- CycloneDXParser.parse(data)                   -> 400 invalid_sbom
  |-- SbomFixOptions.model_validate(json.loads(options)) -> 400 invalid_options
  v
sbom/fixer.py::fix_sbom(data, options, now=None)
  |  1. fixed_sbom = copy.deepcopy(data)            (input never mutated)
  |  2. root rules: set specVersion, remove dependencies, remove services,
  |     increment version
  |  3. metadata rules: add timestamp, remove properties, remove tools
  |  4. metadata.component rules: removes, supplier -> manufacturer
  |  5. components rules (recursive pre-order): remove hashes/scope,
  |     filter externalReferences/properties, fill GOST properties
  |  6. reorder pass LAST: root -> metadata -> metadata.component -> all components
  |  7. stats for every enabled rule; changed = any(count > 0)
  |  8. issues collected from the final fixed_sbom
  v
200 {changed, fixed_sbom, stats, issues}
```

`fix_sbom(data, options, now=None)` accepts an injectable `now: datetime | None` for deterministic timestamps; production uses `datetime.now(timezone.utc)` and formats as `YYYY-MM-DDTHH:MM:SSZ`. Naive datetimes are treated as UTC.

## Rules

Rules mutate a deep copy and never create issues; all issues come from a separate final-document check. Disabled rules leave their fields untouched. Canonical rule order (also the `stats` order):

| # | Rule ID | Default | Behavior | `count` |
|---|---|---|---|---|
| 1 | `root.reorder` | on | Root key order: `bomFormat`, `specVersion`, `serialNumber`, `version`, `metadata`, `components`, `annotations`, then other keys in original relative order | 1 if key order changed else 0 |
| 2 | `root.set_spec_version` | on | Set `specVersion` to trimmed `spec_version` (add if absent) | 1 if value changed/added else 0 |
| 3 | `root.remove_dependencies` | on | Remove root `dependencies` key | 1 if key existed |
| 4 | `root.remove_services` | on | Remove root `services` key | 1 if key existed |
| 5 | `root.increment_version` | on | Increment `version` by 1 when it is an integer (not `bool`) | 1 if incremented |
| 6 | `metadata.add_timestamp` | on | Add `metadata.timestamp` (current UTC, `YYYY-MM-DDTHH:MM:SSZ`) only when it is absent, `null`, or `""`; an existing non-empty value is never overwritten (a non-null, non-string value is left in place and reported) | 1 if added |
| 7 | `metadata.reorder` | on | Order `timestamp`, `component`, then other keys | 1/0 |
| 8 | `metadata.remove_properties` | on | Remove `metadata.properties` | 1/0 |
| 9 | `metadata.remove_tools` | on | Remove `metadata.tools` (array or object) | 1/0 |
| 10 | `metadata_component.reorder` | on | Order `type`, `name`, `version`, `manufacturer`, then other keys | 1/0 |
| 11 | `metadata_component.remove_external_references` | on | Remove `metadata.component.externalReferences` | 1/0 |
| 12 | `metadata_component.remove_properties` | on | Remove `metadata.component.properties` | 1/0 |
| 13 | `metadata_component.remove_purl` | **off** | Remove `metadata.component.purl` | 1/0 |
| 14 | `metadata_component.remove_scope` | on | Remove `metadata.component.scope` | 1/0 |
| 15 | `metadata_component.rename_supplier` | on | Remove `supplier`; move its value to `manufacturer` only when `manufacturer` is absent or `null` | 1 if `supplier` removed |
| 16 | `components.reorder` | on | Per component: `type`, `name`, `version`, `purl`, `externalReferences`, `properties`, `components`, then others; recursive | Number of components whose key order changed |
| 17 | `components.remove_hashes` | on | Remove the component's direct `hashes` key; hashes inside `externalReferences[]` are NOT touched | Number of components changed |
| 18 | `components.remove_scope` | on | Remove the component's direct `scope` key | Number of components changed |
| 19 | `components.filter_external_references` | on | Keep only array items whose `type` is exactly `vcs` or `source-distribution`; empty arrays stay empty | Number of removed items |
| 20 | `components.filter_properties` | on | Keep only array items whose `name` is a string starting exactly with `GOST:` (case-sensitive) | Number of removed items |
| 21 | `components.fill_missing_gost_properties` | **off** | Create `properties: []` when absent/`null`; add missing `{"name": "GOST:attack_surface", "value": "no"}` and `{"name": "GOST:security_function", "value": "no"}`; leave non-array `properties` untouched | Number of added properties |

Notes:

- All component rules (16–21) apply only to the root `components[]` tree (each root component plus its nested `components`, walked pre-order); `metadata.component` and its nested components are outside this tree and are never touched by these rules. Rules 19–21 likewise never touch `metadata.component`.
- `components.filter_properties` runs before `components.fill_missing_gost_properties`, so non-GOST properties are removed and then missing GOST properties are appended.
- The reorder pass (rules 1, 7, 10, 16) runs after every mutation so the final key order reflects the final set of fields.
- The `group` field is never modified anywhere.

## Statistics (`stats`)

- `stats` is a list of `{"rule_id": str, "count": int}` in the canonical order above.
- It contains **all enabled rules**, including entries with `count == 0`.
- Disabled rules are omitted.
- `changed` is `true` iff at least one `stat.count > 0`.
- Root removal counters are `1` (key removed), not the array length.

## Issue Codes (25)

Issues describe defects remaining in the **final** document after the selected rules. They are produced by a single collector, so a defect is reported once. Order is deterministic: root → metadata → metadata.component → components pre-order, codes in the order below within an object.

### Root (8)

| Code | Condition |
|---|---|
| `root.missing_spec_version` | `specVersion` absent, `null`, or empty string |
| `root.invalid_spec_version` | `specVersion` present, not `null`, not a string |
| `root.spec_version_not_allowed` | `specVersion` is a string outside `{"1.6", "1.7"}` |
| `root.missing_version` | `version` absent or `null` |
| `root.invalid_version` | `version` present, not `null`, not an integer (`bool` excluded) |
| `root.missing_metadata` | `metadata` absent or `null` |
| `root.invalid_metadata` | `metadata` present, not `null`, not an object |
| `root.invalid_components` | `components` present, not `null`, not an array |

### `metadata` (3)

| Code | Condition |
|---|---|
| `metadata.missing_timestamp` | `timestamp` absent, `null`, empty, or not a string (format not checked) |
| `metadata.missing_component` | `component` absent or `null` |
| `metadata.invalid_component` | `component` present, not `null`, not an object |

### `metadata.component` (4)

Only evaluated when `metadata.component` is an object; empty strings and `null` count as absent.

| Code | Condition |
|---|---|
| `metadata_component.missing_type` | `type` absent/empty/not a string |
| `metadata_component.missing_name` | `name` absent/empty/not a string |
| `metadata_component.missing_version` | `version` absent/empty/not a string |
| `metadata_component.missing_manufacturer` | `manufacturer` absent, not an object, or without a non-empty string `name` |

### Components (10)

| Code | Condition |
|---|---|
| `component.invalid_entry` | array item is not an object |
| `component.missing_type` | `type` absent/empty/not a string |
| `component.missing_name` | `name` absent/empty/not a string |
| `component.missing_version` | `version` absent/empty/not a string |
| `component.missing_purl` | `purl` absent/empty/not a string |
| `component.invalid_properties` | `properties` present, not `null`, not an array (GOST check skipped) |
| `component.missing_gost_properties` | `properties` absent/`null`, or array missing `GOST:attack_surface` and/or `GOST:security_function`; `details.missing` lists the missing names |
| `component.invalid_external_references` | `externalReferences` present, not `null`, not an array (source check skipped) |
| `component.missing_source_reference` | no `vcs` / `source-distribution` reference and the component is not exempt |
| `component.invalid_subcomponents` | nested `components` present, not `null`, not an array (nested walk skipped) |

`component.missing_source_reference` exemptions: (1) non-empty `components` array; (2) a `properties` entry `{"name": "GOST:provided_by", "value": <non-empty string>}`; (3) a `licenses` entry `{"license": {"name": "Proprietary"}}`.

Codes for the same field are mutually exclusive (`missing_*` / `invalid_*` / `not_allowed`). When `externalReferences` is a non-array, only `invalid_external_references` is emitted, not `missing_source_reference`. Absent or `null` `properties` / `externalReferences` are treated as empty arrays for checking. Missing/invalid `metadata` suppresses `metadata.*` checks; missing/invalid `metadata.component` suppresses its nested checks.

## API Behavior

`POST /api/v1/sbom/fix` — `multipart/form-data` with `file` (required CycloneDX JSON) and optional `options` (JSON string). The endpoint never reads saved options itself; omitted `options` means built-in `SbomFixOptions()` defaults. Response `200`:

```json
{
  "changed": true,
  "fixed_sbom": { "bomFormat": "CycloneDX", "...": "..." },
  "stats": [{ "rule_id": "root.reorder", "count": 1 }],
  "issues": [{
    "code": "component.missing_gost_properties",
    "path": "$.components[0]",
    "component": "openssl",
    "details": { "missing": ["GOST:security_function"] }
  }]
}
```

`fixed_sbom` is always returned, even when `changed` is `false` (all rules disabled → input copy plus a full issue report).

| Condition | HTTP | Error |
|---|---|---|
| File is not valid JSON (including non-UTF-8) | 400 | `invalid_json` |
| Root not an object or `bomFormat != "CycloneDX"` | 400 | `invalid_sbom` (+ `detail`) |
| `options` is invalid JSON or fails Pydantic validation | 400 | `invalid_options` (+ `detail`) |
| File exceeds `sbom_settings.max_file_size` | 413 | `file_too_large` (+ `max_size_mb`) |
| Missing `file` field | 422 | standard FastAPI/Pydantic response |

`GET /api/v1/sbom/fix/options` — returns `200 {"options": {...}}`; unreadable/corrupt file yields built-in defaults with a logged warning (still 200).

`POST /api/v1/sbom/fix/options` — body `{"options": {...}}`; validates via `SbomFixOptions.model_validate`; returns `200 {"status": "saved"}`; malformed JSON, missing `options` key, or validation failure → `400 invalid_options` (+ `detail`); write failure → `500 options_save_failed`.

## Invariants

- The input document is never mutated: `fix_sbom()` works on `copy.deepcopy(data)`.
- Every enabled rule appears in `stats` in canonical order, including zero counts; disabled rules do not appear.
- `changed == any(stat.count > 0 for stat in stats)`.
- Issues are collected **only** from the final fixed document; rules never emit issues, so there are no cascading duplicates.
- The reorder pass is the final mutation; no rule runs after it.
- `spec_version` is validated as `^\d+\.\d+$` regardless of `set_spec_version`; values outside `1.6`/`1.7` are allowed but reported as `root.spec_version_not_allowed`.
- `metadata.timestamp` is added only when absent, `null`, or empty string. It is reported as `metadata.missing_timestamp` when absent, `null`, empty, or a non-string value. An existing non-empty string is never overwritten, and its format is not validated or reported.
- The `group` field is unchanged at every level.
- `components.remove_hashes` removes only the component's own `hashes`; `hashes` inside `externalReferences[]` are preserved.
- `components.fill_missing_gost_properties` applies only to `components[]` items, never to `metadata.component`.
- Unexpected field types never raise and never produce HTTP 500; the affected rule skips the node and the collector reports an `invalid_*` issue.
- A structurally invalid SBOM is not silently reported as fixed — remaining defects appear in `issues`.
- No PostgreSQL and no background queue are required; the operation is synchronous and stateless apart from the options file.
- Statistics and issues are complete; the UI may collapse them, but the API always returns the full lists.

## Configuration

`SbomFixOptionsStore` (in `sbom_fix_options_store.py`, instantiated once in `main.py`):

- File path default: `./data/sbom_fix_options.json`; the constructor accepts an override `path` (used by tests).
- `load() → SbomFixOptions`: missing file → built-in defaults; corrupt JSON, I/O error, or Pydantic validation failure → log warning and return built-in defaults; a partial JSON object is completed by Pydantic field defaults.
- `save(options) → None`: creates the parent directory, writes JSON with `indent=2`, `ensure_ascii=False`, and a trailing newline.
- The whole option object (including `spec_version`) is persisted. No database is used. The store is exposed to routes via `request.app.state.sbom_fix_options_store`.

Upload limit: `sbom_settings.max_file_size` (environment `SBOM_MAX_FILE_SIZE`, default 200 MB).
