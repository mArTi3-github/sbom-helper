# SBOM Fixing

## Description

Synchronous normalization of a CycloneDX SBOM JSON document. The domain applies an explicitly selected subset of 8 named static rules plus an analysis-driven removal of optional fields, returns the fixed document together with per-rule statistics and a report of the defects that remain after the fixes were applied. It targets a fixed catalogue of formal defects (fields removed, `specVersion` set to `1.7`, external reference and property filters, optional GOST properties, missing `manufacturer`), not full FSTEC methodology compliance — producing a fully compliant SBOM is another service's responsibility. Removal of optional fields is a cosmetic cleanup of additional CycloneDX fields not described in the FSTEC tables, not a compliance pass. No database or background queue is involved. See `docs/superpowers/specs/2026-10-26-sbom-fixer-design.md`, `docs/superpowers/specs/2026-10-29-sbom-fixer-optional-fields-design.md` and `docs/superpowers/specs/2026-11-01-sbom-fixer-base-fixes-group-design.md` for the design rationale (git-ignored).

## Key Files

- `src/purl_resolver/sbom/fixer.py` — option models, the 8 static rules, `fix_sbom()` orchestrator, `FixStat`, `FixIssue`, `SbomFixResult`, and the issue collector
- `src/purl_resolver/sbom/optional_fields.py` — FSTEC field catalog (`FSTEC_FIELDS`, `FSTEC_PATHS`), the keep list (`DEFAULT_KEEP_FIELDS`), path grammar (`FIELD_PATH_PATTERN`), `normalize_keep`/`invalid_keep_entries`/`canonical_sort_key`, and the analysis/removal functions (`analyze_fields`, `remove_optional_fields`)
- `src/purl_resolver/sbom/__init__.py` — public exports: `fix_sbom`, `SbomFixOptions`, `SbomFixResult`, `FixStat`, `FixIssue`, `OptionalFieldsFixOptions`
- `src/purl_resolver/sbom/parser.py` — `CycloneDXParser` / `SbomParseError`; validates the root object and `bomFormat == "CycloneDX"` before fixing
- `src/purl_resolver/sbom_fix_options_store.py` — `SbomFixOptionsStore`; JSON-file persistence of the option set
- `src/purl_resolver/routes/sbom_fix.py` — `POST /api/v1/sbom/fix`, `GET/POST /api/v1/sbom/fix/options`, `GET /api/v1/sbom/fix/field-catalog`, `POST /api/v1/sbom/fix/analyze`
- `src/purl_resolver/router.py` — includes the `sbom_fix` sub-router
- `src/purl_resolver/main.py` — creates `app.state.sbom_fix_options_store = SbomFixOptionsStore()` in the lifespan
- `frontend/src/views/SbomFixer.vue` — Fix SBOM page
- `frontend/src/views/sbomFixerRules.ts` — catalog of the 8 static rules (`BASE_RULES` with 5 entries, `COMPONENTS_RULES` with 3; rule id, option key, before/after JSON examples) that drives the rule rows of the page
- `frontend/src/components/RuleHelp.vue` — inline rule help: "(i)" button and a panel with the rule description and before/after snippets
- `frontend/src/api/sbom.ts` — `fixSbom()`, `getFixOptions()`, `saveFixOptions()`, `analyzeSbom()`, `getFieldCatalog()`
- `frontend/src/types/api.ts` — `SbomFixOptions`, `SbomFixStat`, `SbomFixIssue`, `SbomFixResponse`, `SbomFixOptionsResponse`, `OptionalFieldsFixOptions`, `OptionalFieldStatus`, `OptionalFieldInfo`, `FstecField`, `FieldCatalogResponse`
- `tests/test_sbom_fixer.py` — rule, statistics, and issue unit tests
- `tests/test_sbom_optional_fields.py` — catalog, path grammar, analysis, and removal unit tests
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

RULE_IDS = (
    "reorder",
    "set_spec_version",
    "increment_version",
    "add_timestamp",
    "add_manufacturer",
    "components.filter_external_references",
    "components.filter_properties",
    "components.fill_missing_gost_properties",
)

class ComponentsFixOptions(BaseModel):
    filter_external_references: bool = True
    filter_properties: bool = True
    fill_missing_gost_properties: bool = False  # opt-in

class OptionalFieldsFixOptions(BaseModel):
    keep: list[str] = Field(default_factory=lambda: list(DEFAULT_KEEP_FIELDS))
    # validator (mode="before") rejects non-lists and otherwise applies normalize_keep()

class SbomFixOptions(BaseModel):
    reorder: bool = True
    set_spec_version: bool = True
    spec_version: str = "1.7"          # validator: trim, must match ^\d+\.\d+$
    increment_version: bool = True
    add_timestamp: bool = True
    add_manufacturer: bool = True
    manufacturer: str = "Positive Technologies"  # validator: trim, non-empty
    components: ComponentsFixOptions = Field(default_factory=ComponentsFixOptions)
    optional_fields: OptionalFieldsFixOptions = Field(default_factory=OptionalFieldsFixOptions)

@dataclass(frozen=True)
class FstecField:
    path: str
    status: Literal["mandatory", "optional"]
    condition_key: str | None = None

@dataclass(frozen=True)
class FieldInfo:
    path: str
    status: str      # "mandatory" | "optional" | "additional"
    count: int

@dataclass
class FixStat:
    rule_id: str
    count: int
    field: str | None = None   # set only for optional_fields.remove rows

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

The field catalog, keep list, and path grammar live in `optional_fields.py`:

```python
FSTEC_FIELDS: tuple[FstecField, ...]        # 29 entries (tables П.1–П.8)
FSTEC_PATHS: frozenset[str]                 # {f.path for f in FSTEC_FIELDS}
DEFAULT_KEEP_FIELDS: tuple[str, ...]        # 10 entries, see "White lists"
FIELD_PATH_PATTERN = re.compile(
    r"^(root|metadata|metadata\.component|components\[\])\.[A-Za-z0-9_$@.-]+$")

def normalize_keep(entries) -> list[str]    # trim, dedupe, drop bad/grammar/FSTEC
def invalid_keep_entries(entries) -> list[str]  # report bad/grammar/FSTEC (strict)
def canonical_sort_key(path) -> tuple[int, str] # context order, then field
def analyze_fields(data) -> list[FieldInfo]
def remove_optional_fields(data, paths, keep) -> dict[str, int]
```

Default set: every static option is `True` except `components.fill_missing_gost_properties` (`False`); `spec_version` is `"1.7"`; `manufacturer` is `"Positive Technologies"`; `optional_fields.keep` equals `DEFAULT_KEEP_FIELDS`.

## White Lists

Optional-field removal is governed by two white lists and a path grammar.

**List 1 — FSTEC reference (read-only).** `FSTEC_FIELDS` is a 29-entry catalogue of the fields from tables П.1–П.8 with status `mandatory`/`optional` and an optional `condition_key` for conditionally-required fields (`root.components` → `componentsPresent`, `components[].externalReferences[].hashes` → `sourceDistributionHashes`). It is the single source of truth for list 1 and is exposed to the UI via `GET /api/v1/sbom/fix/field-catalog`. Fields in list 1 are never offered for removal and are dropped from `remove_fields` if requested.

**List 2 — "not recommended to remove" (editable).** Stored in options as `optional_fields.keep: list[str]`, defaulting to `DEFAULT_KEEP_FIELDS` (exactly 10 entries):

```
metadata.tools
metadata.component.properties
metadata.component.group
metadata.component.purl
metadata.component.externalReferences
metadata.component.bom-ref
components[].group
components[].licenses
components[].description
components[].bom-ref
```

A list-2 path is never removed: it is excluded from the candidate list and ignored by the server if it still arrives in `remove_fields`. List 2 may contain paths absent from the current document; that is not an error.

**Path grammar.** A path is `root.<field>`, `metadata.<field>`, `metadata.component.<field>`, or `components[].<field>`, where `<field>` matches `[A-Za-z0-9_$@.-]+`. Longest-prefix matching resolves `metadata.component.` before `metadata.`; case is significant.

**Two-tier keep validation.** The option model (used by fix and by loading persisted options) is tolerant: `normalize_keep` trims entries, drops empty/duplicate strings, strings outside the grammar, and list-1 strings — an invalid entry is simply not processed. `POST /options` is strict: before model validation the route checks the raw array with `invalid_keep_entries` and returns `400 invalid_options` naming the offending strings when any non-empty entry fails the grammar or is a list-1 path.

## Flow

```
HTTP client / SbomFixer.vue
  |
  | POST /api/v1/sbom/fix (multipart: file + options JSON string + remove_fields JSON string)
  v
routes/sbom_fix.py
  |-- size check (sbom_settings.max_file_size)      -> 413 file_too_large
  |-- json.loads(raw)                               -> 400 invalid_json
  |-- CycloneDXParser.parse(data)                   -> 400 invalid_sbom
  |-- SbomFixOptions.model_validate(json.loads(options)) -> 400 invalid_options
  |-- parse remove_fields JSON array of strings      -> 400 invalid_remove_fields
  v
sbom/fixer.py::fix_sbom(data, options, now=None, remove_fields=())
  |  1. fixed_sbom = copy.deepcopy(data)            (input never mutated)
  |  2. remove selected optional fields             (remove_optional_fields)
  |  3. root rules: set specVersion, increment version
  |  4. metadata rules: add timestamp; metadata.component: add manufacturer
  |  5. components rules (recursive pre-order): filter externalReferences/properties,
  |     fill GOST properties
  |  6. reorder rule LAST: root -> metadata -> metadata.component -> all components
  |  7. stats for every enabled rule + optional_fields.remove rows; changed = any(count > 0)
  |  8. issues collected from the final fixed_sbom
  v
200 {changed, fixed_sbom, stats, issues}
```

`fix_sbom(data, options, now=None, remove_fields=())` accepts an injectable `now: datetime | None` for deterministic timestamps; production uses `datetime.now(timezone.utc)` and formats as `YYYY-MM-DDTHH:MM:SSZ`. Naive datetimes are treated as UTC. `remove_fields` is a per-request sequence of paths that is not persisted in options.

## Analysis

`analyze_fields(data)` walks the direct keys of:

- the root object (`root.<key>`);
- `metadata` when it is an object (`metadata.<key>`);
- `metadata.component` when it is an object (`metadata.component.<key>`);
- every component in the root `components` array and recursively its nested `components` (pre-order, all levels → `components[].<key>`).

It does not descend into field values: `externalReferences`, `properties`, `licenses`, `hashes`, `manufacturer`, `supplier` and any other object/array are treated as a single field. `metadata.component.components` is a direct key of `metadata.component` (and can be removed whole); its subtree is never scanned. Keys whose canonical path does not match the grammar (spaces, colons, slashes, etc.) are skipped. The status is the catalogue status for list-1 paths, otherwise `additional`. The `count` is 1 for `root`/`metadata`/`metadata.component` when the key is present, and the number of component objects (all levels) containing the key for `components[]`. Results are sorted canonically (`root` → `metadata` → `metadata.component` → `components[]`, alphabetically within each group).

Candidates for the UI are the `additional` records whose path is not in `optional_fields.keep`.

## Rules

Rules mutate a deep copy and never create issues; all issues come from a separate final-document check. Disabled rules leave their fields untouched. Canonical static-rule order (also the `stats` order):

| # | Rule ID | Default | Behavior | `count` |
|---|---|---|---|---|
| 1 | `reorder` | on | Orders every covered object: root keys `bomFormat`, `specVersion`, `serialNumber`, `version`, `metadata`, `components`, `annotations`; then `metadata` keys `timestamp`, `component`; then `metadata.component` keys `type`, `name`, `version`, `manufacturer`; then each component of the root `components[]` tree recursively (pre-order): `type`, `name`, `version`, `purl`, `externalReferences`, `properties`, `components`. Remaining keys keep their original relative order; `metadata.component.components` is not traversed; non-object nodes are skipped | Number of objects whose key order changed: root, `metadata`, `metadata.component`, and each component of the `components[]` tree count 1 each |
| 2 | `set_spec_version` | on | Set `specVersion` to trimmed `spec_version` (add if absent) | 1 if value changed/added else 0 |
| 3 | `increment_version` | on | Increment `version` by 1 when it is an integer (not `bool`) | 1 if incremented |
| 4 | `add_timestamp` | on | Add `metadata.timestamp` (current UTC, `YYYY-MM-DDTHH:MM:SSZ`) only when it is absent, `null`, or `""`; an existing non-empty value is never overwritten (a non-null, non-string value is left in place and reported) | 1 if added |
| 5 | `add_manufacturer` | on | When `metadata.component` is an object: treat `manufacturer` as absent when it is not an object or its `name` is not a non-empty string, then write `{"name": "<manufacturer>"}`; an existing valid `manufacturer` is never changed and `supplier` is never read or modified | 1 if written else 0 |
| 6 | `components.filter_external_references` | on | Keep only array items whose `type` is exactly `vcs` or `source-distribution`; empty arrays stay empty | Number of removed items |
| 7 | `components.filter_properties` | on | Keep only array items whose `name` is a string starting exactly with `GOST:` (case-sensitive) | Number of removed items |
| 8 | `components.fill_missing_gost_properties` | **off** | Create `properties: []` when absent/`null`; add missing `{"name": "GOST:attack_surface", "value": "no"}` and `{"name": "GOST:security_function", "value": "no"}`; leave non-array `properties` untouched | Number of added properties |

The former fixed field-removal options and the supplier-to-manufacturer rename rule no longer exist. Removal is now analysis-driven via the `optional_fields.remove` pseudo-rule described below; the full list of removed options is recorded in the historical design doc.

### Optional-field removal (`optional_fields.remove`)

`remove_optional_fields(data, paths, keep)` filters the requested paths in this order: trim, grammar match, not in `FSTEC_PATHS`, not in `normalize_keep(keep)`, deduplicate; it then sorts the accepted paths canonically and applies them:

- `root.<field>` → remove the root key;
- `metadata.<field>` → remove the key when `metadata` is an object;
- `metadata.component.<field>` → remove the key when `metadata.component` is an object;
- `components[].<field>` → remove the key from every component object at all nesting levels **inside the root `components` tree**. The `metadata.component.components` subtree is never traversed — exactly as in analysis, so a removal count can never exceed the analysis count. `metadata.component.components` itself is a direct key of `metadata.component` and is removed whole via the `metadata.component.<field>` rule.

The whole key is removed (with a value of any shape, including empty array/object). An absent key yields `count = 0`. Invalid, list-1, and list-2 paths are silently ignored and never appear in statistics. A `group` key is removable when the user drops it from list 2 — the former "group is never modified" rule is lifted for this path.

Notes:

- All `components.*` rules (6–8) apply only to the root `components[]` tree (each root component plus its nested `components`, walked pre-order); `metadata.component` and its nested components are outside this tree and are never touched by these rules.
- `components.filter_properties` runs before `components.fill_missing_gost_properties`, so non-GOST properties are removed and then missing GOST properties are appended.
- The `reorder` rule (rule 1) runs after every mutation so the final key order reflects the final set of fields.
- Removal runs before `add_manufacturer`, so a manufacturer added in the same run cannot be removed by it.

Every static rule is documented in the UI by an inline help panel that shows the rule's behaviour and a before/after SBOM fragment; the examples reflect the rule boundaries stated in the table above.

## Statistics (`stats`)

- `stats` is a list of `{"rule_id": str, "count": int}` for the enabled static rules in `RULE_IDS` order, followed by one removal row per accepted path.
- It contains **all enabled static rules**, including entries with `count == 0`.
- `reorder` is a single row regardless of how many objects it reordered; its `count` is the number of objects whose key order changed. With defaults there are 7 static rows (the 8 rules minus the opt-in `components.fill_missing_gost_properties`).
- Disabled rules are omitted.
- Removal rows use `{"rule_id": "optional_fields.remove", "count": int, "field": "<path>"}`; `field` is present only on removal rows, in canonical path order (`root` → `metadata` → `metadata.component` → `components[]`, alphabetically within a group), and is included even when `count == 0`.
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

Known side effect: removing `components[].licenses` can surface `component.missing_source_reference` for proprietary components (the "Proprietary" license exemption disappears); removing `bom-ref` while `dependencies` is preserved can leave dangling references, which the section does not check or warn about.

## API Behavior

`POST /api/v1/sbom/fix` — `multipart/form-data` with `file` (required CycloneDX JSON), optional `options` (JSON string), and optional `remove_fields` (JSON string holding an array of path strings). The endpoint never reads saved options itself; omitted `options` means built-in `SbomFixOptions()` defaults, and omitted `remove_fields` means an empty list. Response `200`:

```json
{
  "changed": true,
  "fixed_sbom": { "bomFormat": "CycloneDX", "...": "..." },
  "stats": [{ "rule_id": "reorder", "count": 3 }],
  "issues": [{
    "code": "component.missing_gost_properties",
    "path": "$.components[0]",
    "component": "openssl",
    "details": { "missing": ["GOST:security_function"] }
  }]
}
```

`fixed_sbom` is always returned, even when `changed` is `false` (all rules disabled → input copy plus a full issue report).

`GET /api/v1/sbom/fix/field-catalog` — returns `200` with `{"fstec_fields": [{"path", "status", "condition_key"?}, ...], "default_keep": [...]}` (list 1 plus the 10 default keep paths).

`POST /api/v1/sbom/fix/analyze` — `multipart/form-data` with `file`; returns `200` with `{"fields": [{"path", "status", "count"}, ...]}` (the compact analysis inventory). The document is not modified. It shares the fix validation path (`413 file_too_large`, `400 invalid_json`, `400 invalid_sbom`, `422` when `file` is missing).

| Condition | HTTP | Error |
|---|---|---|
| File is not valid JSON (including non-UTF-8) | 400 | `invalid_json` |
| Root not an object or `bomFormat != "CycloneDX"` | 400 | `invalid_sbom` (+ `detail`) |
| `options` is invalid JSON or fails Pydantic validation | 400 | `invalid_options` (+ `detail`) |
| `remove_fields` is invalid JSON or not an array of strings | 400 | `invalid_remove_fields` |
| File exceeds `sbom_settings.max_file_size` | 413 | `file_too_large` (+ `max_size_mb`) |
| Missing `file` field | 422 | standard FastAPI/Pydantic response |

`GET /api/v1/sbom/fix/options` — returns `200 {"options": {...}}`; unreadable/corrupt file yields built-in defaults with a logged warning (still 200). The response includes `optional_fields.keep`.

`POST /api/v1/sbom/fix/options` — body `{"options": {...}}`; validates via `SbomFixOptions.model_validate`; returns `200 {"status": "saved"}`. A `keep` array containing a non-empty entry outside the path grammar or a list-1 path yields `400 invalid_options` whose `detail` names the offending entries (strict check runs before model validation). Malformed JSON, missing `options` key, or validation failure → `400 invalid_options` (+ `detail`); write failure → `500 options_save_failed`. In fix and on settings load, invalid `keep` entries are dropped tolerantly without error.

## Invariants

- The input document is never mutated: `fix_sbom()` works on `copy.deepcopy(data)`.
- Every enabled static rule appears in `stats` in canonical order, including zero counts; disabled rules do not appear. Removal rows follow with `field` set, one per accepted path, in canonical order.
- `changed == any(stat.count > 0 for stat in stats)`.
- Issues are collected **only** from the final fixed document; rules never emit issues, so there are no cascading duplicates.
- The `reorder` rule (rule 1) is the final mutation; no rule runs after it.
- `spec_version` is validated as `^\d+\.\d+$` regardless of `set_spec_version`; values outside `1.6`/`1.7` are allowed but reported as `root.spec_version_not_allowed`.
- `manufacturer` is trimmed and must be a non-empty string regardless of `add_manufacturer`; an empty/whitespace value is rejected by the model validator.
- `metadata.timestamp` is added only when absent, `null`, or empty string. It is reported as `metadata.missing_timestamp` when absent, `null`, empty, or a non-string value. An existing non-empty string is never overwritten, and its format is not validated or reported.
- Nothing is removed by default: removal requires an explicit `remove_fields` selection, and no selection survives a file change.
- Protected paths are never removed: list-1 paths and paths in `optional_fields.keep` are dropped from `remove_fields` without error.
- `metadata.component.components` is a direct key of `metadata.component` that can be removed whole; its subtree is never scanned by analysis and never touched by `components[].<field>` removal.
- The `group` field is modified nowhere except by `optional_fields.remove` when the user drops it from list 2.
- `components[].hashes` removal removes only the component's own `hashes`; `hashes` inside `externalReferences[]` are preserved.
- `components.fill_missing_gost_properties` applies only to `components[]` items, never to `metadata.component`.
- Unexpected field types never raise and never produce HTTP 500; the affected rule skips the node and the collector reports an `invalid_*` issue.
- A structurally invalid SBOM is not silently reported as fixed — remaining defects appear in `issues`.
- No PostgreSQL and no background queue are required; the operation is synchronous and stateless apart from the options file.
- Statistics and issues are complete; the UI may collapse them, but the API always returns the full lists.

## Configuration

`SbomFixOptionsStore` (in `sbom_fix_options_store.py`, instantiated once in `main.py`):

- File path default: `./data/sbom_fix_options.json`; the constructor accepts an override `path` (used by tests).
- `load() → SbomFixOptions`: missing file → built-in defaults; corrupt JSON, I/O error, or Pydantic validation failure → log warning and return built-in defaults; a partial JSON object is completed by Pydantic field defaults. The persisted JSON is flat: `reorder`, `set_spec_version`, `spec_version`, `increment_version`, `add_timestamp`, `add_manufacturer`, `manufacturer`, plus the nested `components` and `optional_fields` objects. Legacy keys — the former nested `root`, `metadata`, and `metadata.component` objects with their per-object `reorder` flags, the former `remove_*` options, and the supplier rename rule — are unknown fields to Pydantic and are silently ignored; there is no migration code or compatibility branch.
- `save(options) → None`: creates the parent directory, writes JSON with `indent=2`, `ensure_ascii=False`, and a trailing newline.
- The whole option object (including `spec_version`, `manufacturer`, and `optional_fields.keep`) is persisted. No database is used. The store is exposed to routes via `request.app.state.sbom_fix_options_store`.

Upload limit: `sbom_settings.max_file_size` (environment `SBOM_MAX_FILE_SIZE`, default 200 MB).
