# Fix SBOM Optional-Field Removal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the ten hard-coded field-removal rules with an analysis-driven "optional fields by white list" subsection, add the `add_manufacturer` rule, and keep the fixer deterministic and fully tested.

**Architecture:** A new stdlib-only module `sbom/optional_fields.py` owns the FSTEC field catalog, path grammar, analysis, and removal. `fixer.py` consumes it in the existing pipeline and gains dynamic per-path statistics. The FastAPI route exposes the catalog and analysis, accepts a per-request `remove_fields` list, and validates the persisted `keep` list strictly only on save. Vue renders the compact analysis result, filters candidates against the two white lists, and sends only accepted paths.

**Tech Stack:** Python 3.12, Pydantic v2, FastAPI, pytest, ruff; Vue 3, TypeScript, vue-i18n, Vitest.

**Spec:** `docs/superpowers/specs/2026-10-29-sbom-fixer-optional-fields-design.md`

## Global Constraints

- Backend has no new dependencies: `optional_fields.py` imports only `re`, `dataclasses`, `typing` and standard library; `fixer.py` keeps Pydantic + stdlib.
- Maximum uploaded file size stays `sbom_settings.max_file_size` (200 MB); analysis and fix share the same validation path.
- `fix_sbom` must not mutate its input (`copy.deepcopy`).
- All user-facing strings live in `frontend/src/i18n/locales/{ru,en}.json` with identical structure.
- Only enabled static rules appear in `stats`, in canonical order; removal rows follow with `field` set.
- Nothing is removed unless the user selected the path; the ten former removal options no longer exist.
- The field-removal vocabulary is limited to direct keys of root, `metadata`, `metadata.component`, and root-`components` recursively; `metadata.component.components` is never scanned or modified.
- Path grammar: `^(root|metadata|metadata\.component|components\[\])\.[A-Za-z0-9_$@.-]+$`.
- Default keep list has exactly 10 paths, including `metadata.component.bom-ref` and `components[].bom-ref`.
- Tests run with `.venv/bin/python -m pytest` and `.venv/bin/ruff check src tests`; frontend with `npm test --prefix frontend` and `npm run build --prefix frontend`.

## Review Focus

- An SBOM with `metadata.component.components`: removal must not touch that subtree, or removal counts exceed the analysis counts. Pinned in Task 2.
- A document key outside the path grammar (e.g. `"weird key"`): it must not appear as a checkbox that the server silently ignores. Pinned in Task 2.
- An old or hand-edited `data/sbom_fix_options.json` with former `remove_*` keys and invalid `keep` lines: loading must not fail or reset working options. Pinned in Tasks 3 and 4.
- A half-typed, not-yet-saved line in the keep textarea sent with "Исправить": it must be ignored, not turn the request into `400 invalid_options`. Pinned in Task 4.
- Removing `components[].licenses`: the issues report may then show `component.missing_source_reference`; this is expected and must not crash. Pinned in Task 3.

---

### Task 1: FSTEC catalog, path grammar, keep normalization

**Files:**
- Create: `src/purl_resolver/sbom/optional_fields.py`
- Test: `tests/test_sbom_optional_fields.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `FSTEC_FIELDS: tuple[FstecField, ...]`
  - `FstecField` frozen dataclass: `path: str`, `status: Literal["mandatory", "optional"]`, `condition_key: str | None = None`
  - `DEFAULT_KEEP_FIELDS: tuple[str, ...]` (10 entries)
  - `FSTEC_PATHS: frozenset[str]`
  - `FIELD_PATH_PATTERN: re.Pattern[str]`
  - `normalize_keep(entries: list[str]) -> list[str]`
  - `invalid_keep_entries(entries: list[str]) -> list[str]`
  - `canonical_sort_key(path: str) -> tuple[int, str]`

- [ ] **Step 1: Write the failing test**

```python
from purl_resolver.sbom.optional_fields import (
    DEFAULT_KEEP_FIELDS,
    FSTEC_FIELDS,
    canonical_sort_key,
    invalid_keep_entries,
    normalize_keep,
)


def test_fstec_catalog_covers_all_tables():
    paths = {f.path for f in FSTEC_FIELDS}
    assert len(FSTEC_FIELDS) == 29
    assert {
        "root.bomFormat", "root.specVersion", "root.serialNumber", "root.version",
        "root.metadata", "root.components", "root.annotations",
        "metadata.timestamp", "metadata.component",
        "metadata.component.type", "metadata.component.name",
        "metadata.component.version", "metadata.component.manufacturer",
        "metadata.component.manufacturer.name",
        "components[].type", "components[].name", "components[].version",
        "components[].purl", "components[].cpe",
        "components[].externalReferences", "components[].properties",
        "components[].components",
        "components[].externalReferences[].type",
        "components[].externalReferences[].url",
        "components[].externalReferences[].hashes",
        "components[].externalReferences[].hashes[].alg",
        "components[].externalReferences[].hashes[].content",
        "components[].properties[].name", "components[].properties[].value",
    } == paths
    statuses = {f.path: f.status for f in FSTEC_FIELDS}
    assert statuses["root.serialNumber"] == "optional"
    assert statuses["components[].cpe"] == "optional"
    assert statuses["components[].externalReferences[].hashes"] == "optional"
    assert statuses["root.bomFormat"] == "mandatory"
    conditions = {f.path: f.condition_key for f in FSTEC_FIELDS}
    assert conditions["root.components"] == "componentsPresent"
    assert conditions["components[].externalReferences[].hashes"] == "sourceDistributionHashes"


def test_default_keep_has_ten_paths_including_bom_ref():
    assert DEFAULT_KEEP_FIELDS == (
        "metadata.tools",
        "metadata.component.properties",
        "metadata.component.group",
        "metadata.component.purl",
        "metadata.component.externalReferences",
        "metadata.component.bom-ref",
        "components[].group",
        "components[].licenses",
        "components[].description",
        "components[].bom-ref",
    )


def test_normalize_keep_trims_drops_duplicates_and_invalid():
    entries = [
        "  components[].group  ",
        "components[].group",
        "",
        "not a path",
        "components[].licenses",
        "root.bomFormat",
        "metadata.timestamp",
    ]
    assert normalize_keep(entries) == [
        "components[].group",
        "components[].licenses",
    ]


def test_invalid_keep_entries_reports_bad_and_fstec_paths():
    entries = ["components[].group", "bad path", "root.bomFormat", "  "]
    assert invalid_keep_entries(entries) == ["bad path", "root.bomFormat"]


def test_canonical_sort_key_orders_contexts_then_paths():
    paths = [
        "components[].scope",
        "metadata.tools",
        "root.dependencies",
        "metadata.component.purl",
        "components[].hashes",
    ]
    assert sorted(paths, key=canonical_sort_key) == [
        "root.dependencies",
        "metadata.tools",
        "metadata.component.purl",
        "components[].hashes",
        "components[].scope",
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_sbom_optional_fields.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'purl_resolver.sbom.optional_fields'`.

- [ ] **Step 3: Implement the catalog and helpers**

In `src/purl_resolver/sbom/optional_fields.py`, add `from __future__ import annotations`, the frozen dataclass, the 29-row `FSTEC_FIELDS` exactly as in design §6.1, `FSTEC_PATHS = frozenset(f.path for f in FSTEC_FIELDS)`, the 10-entry `DEFAULT_KEEP_FIELDS`, and:

```python
FIELD_PATH_PATTERN = re.compile(
    r"^(root|metadata|metadata\.component|components\[\])\.[A-Za-z0-9_$@.-]+$"
)
CONTEXT_ORDER = {"root": 0, "metadata": 1, "metadata.component": 2, "components[]": 3}
```

`normalize_keep` trims each entry, drops empties, keeps the first occurrence, and drops entries that fail `FIELD_PATH_PATTERN.fullmatch` or are in `FSTEC_PATHS`. `invalid_keep_entries` trims and returns non-empty entries that fail the grammar or are in `FSTEC_PATHS`, preserving order. `canonical_sort_key` splits the path at the longest known prefix and returns `(CONTEXT_ORDER[prefix], field)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_sbom_optional_fields.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/purl_resolver/sbom/optional_fields.py tests/test_sbom_optional_fields.py
git commit -m "feat: add fstec field catalog and path grammar"
```

---

### Task 2: Analyze present fields and remove selected ones

**Files:**
- Modify: `src/purl_resolver/sbom/optional_fields.py`
- Test: `tests/test_sbom_optional_fields.py`

**Interfaces:**
- Consumes: Task 1 constants and helpers.
- Produces:
  - `FieldInfo` frozen dataclass: `path: str`, `status: str`, `count: int`
  - `analyze_fields(data: dict) -> list[FieldInfo]`
  - `remove_optional_fields(data: dict, paths: list[str], keep: list[str]) -> dict[str, int]`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_sbom_optional_fields.py`:

```python
import copy
from purl_resolver.sbom.optional_fields import analyze_fields, remove_optional_fields


def component_doc() -> dict:
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.7",
        "version": 1,
        "metadata": {
            "timestamp": "2026-01-01T00:00:00Z",
            "tools": [{"name": "gen"}],
            "component": {
                "type": "application",
                "name": "app",
                "version": "1.0",
                "purl": "pkg:generic/app@1.0",
                "bom-ref": "app",
                "components": [{"type": "library", "name": "inner", "scope": "required"}],
            },
        },
        "components": [
            {
                "type": "library",
                "name": "openssl",
                "version": "3.0",
                "purl": "pkg:generic/openssl@3.0",
                "bom-ref": "openssl",
                "scope": "required",
                "licenses": [{"license": {"name": "MIT"}}],
                "components": [
                    {"type": "library", "name": "zlib", "version": "1.2",
                     "purl": "pkg:generic/zlib@1.2", "bom-ref": "zlib", "scope": "required"}
                ],
            },
            {"name": "no-type", "weird key": True},
        ],
        "dependencies": [{"ref": "openssl"}],
    }


def test_analyze_fields_reports_contexts_counts_and_statuses():
    result = {item.path: item for item in analyze_fields(component_doc())}
    assert result["root.version"].status == "mandatory"
    assert result["root.version"].count == 1
    assert result["root.dependencies"].status == "additional"
    assert result["metadata.tools"].status == "additional"
    assert result["metadata.component.bom-ref"].count == 1
    assert result["components[].scope"].count == 2
    assert result["components[].bom-ref"].count == 2
    assert result["components[].licenses"].count == 1
    assert "components[].weird key" not in result
    assert "metadata.component.components.scope" not in result
    assert "metadata.component.components" in result


def test_analyze_fields_is_sorted_canonically():
    paths = [item.path for item in analyze_fields(component_doc())]
    assert paths.index("root.dependencies") < paths.index("metadata.tools")
    assert paths.index("metadata.tools") < paths.index("metadata.component.purl")
    assert paths.index("metadata.component.purl") < paths.index("components[].bom-ref")
    assert paths.index("components[].bom-ref") < paths.index("components[].licenses")


def test_analyze_fields_does_not_descend_into_field_values():
    result = {item.path for item in analyze_fields(component_doc())}
    assert "components[].externalReferences[].type" not in result
    assert "components[].properties[].name" not in result


def test_remove_optional_fields_removes_all_contexts_recursively():
    data = component_doc()
    counts = remove_optional_fields(
        data,
        ["root.dependencies", "metadata.tools", "metadata.component.purl",
         "components[].scope", "components[].licenses"],
        keep=[p for p in DEFAULT_KEEP_FIELDS
              if p not in {"metadata.tools", "metadata.component.purl",
                           "components[].licenses"}],
    )
    assert counts == {
        "root.dependencies": 1,
        "metadata.tools": 1,
        "metadata.component.purl": 1,
        "components[].scope": 2,
        "components[].licenses": 1,
    }
    assert "dependencies" not in data
    assert "tools" not in data["metadata"]
    assert "purl" not in data["metadata"]["component"]
    assert "scope" not in data["components"][0]
    assert "scope" not in data["components"][0]["components"][0]
    assert "licenses" not in data["components"][0]
    assert "type" in data["components"][0]


def test_remove_optional_fields_ignores_fstec_keep_and_invalid_paths():
    data = component_doc()
    counts = remove_optional_fields(
        data,
        ["root.version", "metadata.timestamp", "components[].bom-ref",
         "metadata.component.purl", "bad path", "components[].bom-ref".upper()],
        keep=[*DEFAULT_KEEP_FIELDS, "metadata.component.purl"],
    )
    assert counts == {}
    assert data["version"] == 1
    assert data["metadata"]["timestamp"] == "2026-01-01T00:00:00Z"
    assert data["components"][0]["bom-ref"] == "openssl"
    assert data["metadata"]["component"]["purl"] == "pkg:generic/app@1.0"


def test_remove_optional_fields_reports_zero_for_absent_path_and_does_not_mutate_input():
    data = component_doc()
    original = copy.deepcopy(data)
    counts = remove_optional_fields(data, ["root.services"], keep=list(DEFAULT_KEEP_FIELDS))
    assert counts == {"root.services": 0}
    assert data == original


def test_remove_optional_fields_does_not_touch_metadata_component_components():
    data = component_doc()
    counts = remove_optional_fields(data, ["components[].scope"], keep=list(DEFAULT_KEEP_FIELDS))
    assert counts == {"components[].scope": 2}
    assert data["metadata"]["component"]["components"][0]["scope"] == "required"


def test_remove_optional_fields_does_not_touch_external_reference_hashes():
    data = {
        "bomFormat": "CycloneDX", "specVersion": "1.7", "version": 1,
        "components": [{
            "type": "library", "name": "x", "version": "1", "purl": "pkg:generic/x@1",
            "hashes": [{"alg": "SHA-256", "content": "a"}],
            "externalReferences": [{
                "type": "source-distribution", "url": "https://x",
                "hashes": [{"alg": "STREEBOG-256", "content": "b"}],
            }],
        }],
    }
    remove_optional_fields(data, ["components[].hashes"], keep=[])
    assert "hashes" not in data["components"][0]
    assert data["components"][0]["externalReferences"][0]["hashes"][0]["alg"] == "STREEBOG-256"


def test_remove_optional_fields_can_delete_group_when_not_kept():
    data = component_doc()
    data["components"][0]["group"] = "vendor"
    counts = remove_optional_fields(data, ["components[].group"], keep=[])
    assert counts == {"components[].group": 1}
    assert "group" not in data["components"][0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_sbom_optional_fields.py -v`
Expected: FAIL with `ImportError: cannot import name 'analyze_fields'`.

- [ ] **Step 3: Implement `analyze_fields` and `remove_optional_fields`**

`analyze_fields` builds `{path: count}` by walking:
- root keys, `metadata` keys, `metadata.component` keys, each prefixed accordingly (only when the value is a dict);
- root `components` list recursively through nested `components` lists, counting each component dict that has the key and never descending into key values.
Skip keys that fail the field part of the grammar. Status is the `FSTEC_FIELDS` status when present, else `"additional"`. Return `FieldInfo` items sorted by `canonical_sort_key`.

`remove_optional_fields` filters the requested paths in this order: trim, grammar, not in `FSTEC_PATHS`, not in `normalize_keep(keep)`, deduplicate; sorts accepted paths by `canonical_sort_key`; pops `root.<field>`, `metadata.<field>`, `metadata.component.<field>`, or walks root components for `components[].<field>`. Returns `{path: removed_count}` for every accepted path, including zeros.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_sbom_optional_fields.py -v`
Expected: PASS (12 tests).

- [ ] **Step 5: Commit**

```bash
git add src/purl_resolver/sbom/optional_fields.py tests/test_sbom_optional_fields.py
git commit -m "feat: analyze and remove optional sbom fields"
```

---

### Task 3: Options model, `add_manufacturer`, pipeline, dynamic stats

**Files:**
- Modify: `src/purl_resolver/sbom/fixer.py`
- Modify: `src/purl_resolver/sbom/__init__.py`
- Test: `tests/test_sbom_fixer.py`

**Interfaces:**
- Consumes: `DEFAULT_KEEP_FIELDS`, `normalize_keep`, `remove_optional_fields` from Task 1–2.
- Produces:
  - `OptionalFieldsFixOptions` with `keep: list[str]`
  - `SbomFixOptions.optional_fields`
  - `MetadataComponentFixOptions.add_manufacturer: bool`, `manufacturer: str`
  - `RULE_IDS` with 11 ids
  - `FixStat.field: str | None = None`
  - `fix_sbom(data, options, now=None, remove_fields: Sequence[str] = ()) -> SbomFixResult`

- [ ] **Step 1: Rewrite the failing default and stats tests**

In `tests/test_sbom_fixer.py`, update the imports and replace the 21-rule assertions:

```python
from purl_resolver.sbom.optional_fields import DEFAULT_KEEP_FIELDS

NEW_RULE_IDS = (
    "root.reorder",
    "root.set_spec_version",
    "root.increment_version",
    "metadata.add_timestamp",
    "metadata.reorder",
    "metadata_component.reorder",
    "metadata_component.add_manufacturer",
    "components.reorder",
    "components.filter_external_references",
    "components.filter_properties",
    "components.fill_missing_gost_properties",
)


def test_defaults_expose_new_options_and_keep_list():
    o = SbomFixOptions()
    assert o.metadata.component.add_manufacturer is True
    assert o.metadata.component.manufacturer == "Positive Technologies"
    assert o.components.fill_missing_gost_properties is False
    assert o.optional_fields.keep == list(DEFAULT_KEEP_FIELDS)
    for removed in ("remove_dependencies", "remove_services"):
        assert not hasattr(o.root, removed)
    assert not hasattr(o.metadata, "remove_properties")
    assert not hasattr(o.metadata.component, "remove_purl")
    assert not hasattr(o.components, "remove_hashes")


def test_default_stats_contain_only_enabled_rules():
    result = fix_sbom({"bomFormat": "CycloneDX", "specVersion": "1.7", "version": 1},
                      SbomFixOptions())
    assert [stat.rule_id for stat in result.stats] == [
        rule for rule in NEW_RULE_IDS
        if rule != "components.fill_missing_gost_properties"
    ]


def test_all_enabled_rules_yield_eleven_stats_in_canonical_order():
    options = SbomFixOptions(components={"fill_missing_gost_properties": True})
    result = fix_sbom({"bomFormat": "CycloneDX", "specVersion": "1.7", "version": 1}, options)
    assert [stat.rule_id for stat in result.stats] == list(NEW_RULE_IDS)
```

- [ ] **Step 2: Add failing tests for `add_manufacturer`, removal, and licensing side effect**

```python
@pytest.mark.parametrize(
    "component",
    [
        {"type": "application", "name": "app", "version": "1.0"},
        {"type": "application", "name": "app", "version": "1.0", "manufacturer": None},
        {"type": "application", "name": "app", "version": "1.0", "manufacturer": {}},
        {"type": "application", "name": "app", "version": "1.0",
         "manufacturer": {"name": "  "}},
    ],
)
def test_add_manufacturer_fills_missing_or_empty(component):
    data = {
        "bomFormat": "CycloneDX", "specVersion": "1.7", "version": 1,
        "metadata": {"component": component},
    }
    options = SbomFixOptions(metadata={"component": {"manufacturer": "  Acme  "}})
    result = fix_sbom(data, options)
    assert data["metadata"]["component"].get("manufacturer") in (None, {}, {"name": "  "})
    assert result.fixed_sbom["metadata"]["component"]["manufacturer"] == {"name": "Acme"}
    stats = {stat.rule_id: stat.count for stat in result.stats}
    assert stats["metadata_component.add_manufacturer"] == 1


def test_add_manufacturer_keeps_existing_value_and_ignores_supplier():
    data = {
        "bomFormat": "CycloneDX", "specVersion": "1.7", "version": 1,
        "metadata": {"component": {
            "type": "application", "name": "app", "version": "1.0",
            "manufacturer": {"name": "Existing"}, "supplier": {"name": "Supplier"},
        }},
    }
    result = fix_sbom(data, SbomFixOptions())
    assert result.fixed_sbom["metadata"]["component"]["manufacturer"] == {"name": "Existing"}
    assert result.fixed_sbom["metadata"]["component"]["supplier"] == {"name": "Supplier"}


@pytest.mark.parametrize("value", ["", "   "])
def test_empty_manufacturer_value_is_rejected(value):
    with pytest.raises(ValidationError):
        SbomFixOptions(metadata={"component": {"manufacturer": value}})


def test_remove_fields_runs_before_add_manufacturer_and_appears_in_stats():
    data = {
        "bomFormat": "CycloneDX", "specVersion": "1.7", "version": 1,
        "metadata": {"component": {"type": "application", "name": "app", "version": "1.0"}},
        "components": [{"type": "library", "name": "openssl", "version": "3.0",
                        "purl": "pkg:generic/openssl@3.0", "scope": "required"}],
        "dependencies": [{"ref": "openssl"}],
    }
    result = fix_sbom(data, SbomFixOptions(), remove_fields=["root.dependencies",
                                                            "components[].scope"])
    removal_stats = [s for s in result.stats if s.rule_id == "optional_fields.remove"]
    assert [(s.field, s.count) for s in removal_stats] == [
        ("root.dependencies", 1),
        ("components[].scope", 1),
    ]
    assert "dependencies" not in result.fixed_sbom
    assert "scope" not in result.fixed_sbom["components"][0]
    assert result.fixed_sbom["metadata"]["component"]["manufacturer"] == {
        "name": "Positive Technologies"
    }
    assert result.changed is True


def test_protected_paths_are_ignored_by_fix():
    data = {
        "bomFormat": "CycloneDX", "specVersion": "1.7", "version": 1,
        "components": [{"type": "library", "name": "openssl", "version": "3.0",
                        "purl": "pkg:generic/openssl@3.0", "bom-ref": "openssl"}],
    }
    result = fix_sbom(data, SbomFixOptions(), remove_fields=["components[].bom-ref"])
    assert result.fixed_sbom["components"][0]["bom-ref"] == "openssl"
    assert not [s for s in result.stats if s.rule_id == "optional_fields.remove"]


def test_removing_licenses_can_surface_missing_source_reference():
    data = {
        "bomFormat": "CycloneDX", "specVersion": "1.7", "version": 1,
        "components": [{"type": "library", "name": "proprietary", "version": "1.0",
                        "purl": "pkg:generic/proprietary@1.0",
                        "licenses": [{"license": {"name": "Proprietary"}}]}],
    }
    options = SbomFixOptions(optional_fields={
        "keep": [p for p in DEFAULT_KEEP_FIELDS if p != "components[].licenses"]
    })
    result = fix_sbom(data, options, remove_fields=["components[].licenses"])
    codes = [issue.code for issue in result.issues]
    assert "component.missing_source_reference" in codes
```

Remove or rewrite the old tests that depend on the ten deleted options and `rename_supplier`. Run:

```bash
grep -nE "remove_dependencies|remove_services|remove_properties|remove_tools|remove_hashes|remove_scope|remove_purl|remove_external_references|rename_supplier|== 19|== 21|len\(result.stats\)|len\(data\['stats'\]\)" tests/test_sbom_fixer.py
```

Every match must be deleted or rewritten: removal scenarios become `remove_fields=[...]` calls (or move to `tests/test_sbom_optional_fields.py`), manufacturer scenarios become `add_manufacturer` tests, stat-count assertions become 10 (defaults) or 11 (all enabled). Keep the reorder, timestamp, filter, GOST, issue, and immutability tests, updating only the option names and expected stat counts they mention. `test_defaults_all_on_except_two_rules` and `test_all_enabled_rules_yield_21_stats_in_canonical_order` are replaced by the tests above.

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_sbom_fixer.py -v`
Expected: FAIL on missing `optional_fields`, `add_manufacturer`, and changed `RULE_IDS`/stats.

- [ ] **Step 4: Implement the model and pipeline changes**

In `fixer.py`:

- Delete the ten `remove_*` fields and `rename_supplier`; add to `MetadataComponentFixOptions`:
  ```python
  add_manufacturer: bool = True
  manufacturer: str = "Positive Technologies"

  @field_validator("manufacturer", mode="before")
  @classmethod
  def _validate_manufacturer(cls, value: object) -> str:
      if isinstance(value, str):
          value = value.strip()
      if not isinstance(value, str) or not value:
          raise ValueError("manufacturer must be a non-empty string")
      return value
  ```
- Add `OptionalFieldsFixOptions` with a `keep` validator in `mode="before"`: if the value is not a list, raise `ValueError`; otherwise return `normalize_keep(value)`. Add `optional_fields` to `SbomFixOptions`.
- Replace `RULE_IDS` with the 11 ids from `NEW_RULE_IDS`.
- `FixStat` becomes `rule_id: str`, `count: int`, `field: str | None = None`.
- Remove `_rename_supplier`; add:
  ```python
  def _add_manufacturer(component: dict, value: str) -> int:
      manufacturer = component.get("manufacturer")
      if isinstance(manufacturer, dict) and _is_non_empty_string(manufacturer.get("name")):
          return 0
      component["manufacturer"] = {"name": value}
      return 1
  ```
  Call it from `_apply_metadata_rules` after `add_timestamp` when the rule is enabled.
- Delete the `dependencies`/`services` loop in `_apply_root_rules`, the `properties`/`tools` loop in `_apply_metadata_rules`, the four `metadata_component` removals, and the two `components` removals. Keep `_apply_reorders` for `metadata_component.reorder`.
- Change the orchestrator:
  ```python
  def fix_sbom(data, options, now=None, remove_fields: Sequence[str] = ()) -> SbomFixResult:
      ...
      removal_counts = remove_optional_fields(fixed_sbom, list(remove_fields),
                                              options.optional_fields.keep)
      _apply_root_rules(...)
      _apply_metadata_rules(...)
      _apply_components_rules(...)
      fixed_sbom = _apply_reorders(...)
      stats = [FixStat(rule_id=r, count=counts.get(r, 0)) for r in _enabled_rule_ids(options)]
      stats.extend(FixStat(rule_id="optional_fields.remove", count=c, field=p)
                   for p, c in removal_counts.items())
      ...
  ```
- Export `OptionalFieldsFixOptions` from `sbom/__init__.py`; leave the other exports intact.

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_sbom_fixer.py tests/test_sbom_optional_fields.py -v`
Expected: PASS. Then run `.venv/bin/ruff check src tests`.

- [ ] **Step 6: Commit**

```bash
git add src/purl_resolver/sbom/fixer.py src/purl_resolver/sbom/__init__.py tests/test_sbom_fixer.py
git commit -m "feat: drive field removal from analysis and add manufacturer rule"
```

---

### Task 4: API catalog, analysis, `remove_fields`, strict keep validation

**Files:**
- Modify: `src/purl_resolver/routes/sbom_fix.py`
- Test: `tests/test_sbom_fix_api.py`

**Interfaces:**
- Consumes: `FSTEC_FIELDS`, `DEFAULT_KEEP_FIELDS`, `analyze_fields`, `invalid_keep_entries`, `fix_sbom(..., remove_fields=...)`.
- Produces:
  - `GET /api/v1/sbom/fix/field-catalog` → `{"fstec_fields": [...], "default_keep": [...]}`
  - `POST /api/v1/sbom/fix/analyze` (multipart `file`) → `{"fields": [...]}`
  - `POST /api/v1/sbom/fix` accepts optional form field `remove_fields`
  - `400 invalid_remove_fields` on malformed `remove_fields`
  - `400 invalid_options` for bad `keep` on `POST /options`

- [ ] **Step 1: Write the failing API tests**

Add to `tests/test_sbom_fix_api.py`:

```python
def upload_analyze(client, sbom):
    files = {"file": ("bom.json", json.dumps(sbom).encode("utf-8"), "application/json")}
    return client.post("/api/v1/sbom/fix/analyze", files=files)


def upload_fix(client, sbom, remove_fields=None, options=None):
    files = {"file": ("bom.json", json.dumps(sbom).encode("utf-8"), "application/json")}
    data = {}
    if options is not None:
        data["options"] = json.dumps(options)
    if remove_fields is not None:
        data["remove_fields"] = json.dumps(remove_fields)
    return client.post("/api/v1/sbom/fix", files=files, data=data)


def test_field_catalog_returns_fstec_fields_and_default_keep(client):
    response = client.get("/api/v1/sbom/fix/field-catalog")
    assert response.status_code == 200
    body = response.json()
    assert len(body["fstec_fields"]) == 29
    assert len(body["default_keep"]) == 10
    assert {"path": "root.bomFormat", "status": "mandatory"} in body["fstec_fields"]


def test_analyze_returns_compact_inventory(client):
    response = upload_analyze(client, make_sbom())
    assert response.status_code == 200
    fields = {item["path"]: item for item in response.json()["fields"]}
    assert fields["root.dependencies"]["status"] == "additional"
    assert fields["root.dependencies"]["count"] == 1
    assert fields["root.version"]["status"] == "mandatory"
    assert fields["components[].hashes"]["count"] == 1


def test_analyze_rejects_invalid_input(client):
    files = {"file": ("bom.json", b"not json", "application/json")}
    assert client.post("/api/v1/sbom/fix/analyze", files=files).status_code == 400
    files = {"file": ("bom.json", json.dumps({"bomFormat": "Other"}).encode(), "application/json")}
    assert client.post("/api/v1/sbom/fix/analyze", files=files).status_code == 400


def test_fix_removes_selected_fields_and_reports_them(client):
    response = upload_fix(
        client, make_sbom(),
        remove_fields=["root.dependencies", "root.services", "components[].hashes"],
    )
    assert response.status_code == 200
    body = response.json()
    assert "dependencies" not in body["fixed_sbom"]
    assert "services" not in body["fixed_sbom"]
    assert "hashes" not in body["fixed_sbom"]["components"][0]
    removal = [s for s in body["stats"] if s["rule_id"] == "optional_fields.remove"]
    assert {(s["field"], s["count"]) for s in removal} == {
        ("root.dependencies", 1), ("root.services", 1), ("components[].hashes", 1)
    }


def test_fix_ignores_protected_and_malformed_paths(client):
    response = upload_fix(
        client, make_sbom(),
        remove_fields=["root.version", "components[].purl", "bad path"],
        options={"optional_fields": {"keep": []}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["fixed_sbom"]["version"] == 1
    assert "purl" in body["fixed_sbom"]["components"][0]
    assert not [s for s in body["stats"] if s["rule_id"] == "optional_fields.remove"]


def test_fix_ignores_invalid_keep_lines_in_options(client):
    response = upload_fix(
        client, make_sbom(),
        remove_fields=["components[].hashes"],
        options={"optional_fields": {"keep": ["bad path", "root.version"]}},
    )
    assert response.status_code == 200
    assert "hashes" not in response.json()["fixed_sbom"]["components"][0]


def test_fix_rejects_malformed_remove_fields(client):
    response = upload_fix(client, make_sbom(), remove_fields="not-a-list")
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_remove_fields"


def test_save_options_rejects_invalid_keep(client):
    response = client.post(
        "/api/v1/sbom/fix/options",
        json={"options": {"optional_fields": {"keep": ["components[].group", "bad path"]}}},
    )
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_options"
    assert "bad path" in response.json()["detail"]


def test_save_and_load_options_keep_list(client):
    keep = ["components[].group", "components[].licenses"]
    assert client.post("/api/v1/sbom/fix/options",
                       json={"options": {"optional_fields": {"keep": keep}}}).status_code == 200
    body = client.get("/api/v1/sbom/fix/options").json()
    assert body["options"]["optional_fields"]["keep"] == keep
```

Add to `tests/test_sbom_fix_options_store.py`:

```python
def test_load_ignores_legacy_remove_keys(tmp_path):
    path = tmp_path / "legacy.json"
    path.write_text(
        json.dumps({
            "root": {"reorder": False, "remove_dependencies": True},
            "components": {"remove_hashes": True, "remove_scope": True},
            "metadata": {"component": {"rename_supplier": True}},
        }),
        encoding="utf-8",
    )
    options = SbomFixOptionsStore(path).load()
    assert options.root.reorder is False
    assert not hasattr(options.root, "remove_dependencies")
    assert not hasattr(options.components, "remove_hashes")
    assert options.optional_fields.keep == list(DEFAULT_KEEP_FIELDS)
```

Import `DEFAULT_KEEP_FIELDS` from `purl_resolver.sbom.optional_fields` in that file.

Adapt the existing tests in this file to the new contract: `test_fix_returns_expected_shape` and `test_fix_with_options_honors_them` must stop passing `metadata.component.remove_purl` and stop expecting 20 stats rows. Run `grep -nE "remove_|rename_supplier|== 20|len\(data\['stats'\]\)" tests/test_sbom_fix_api.py` and rewrite every match.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_sbom_fix_api.py -v`
Expected: FAIL on 404 for the new routes and on changed stats.

- [ ] **Step 3: Implement the routes**

- Extract the repeated upload handling into `async def _load_sbom(file: UploadFile) -> tuple[dict | None, JSONResponse | None]` that checks size, parses JSON, and runs `CycloneDXParser`; both fix and analyze use it.
- Add `_parse_remove_fields(raw: str | None) -> tuple[list[str] | None, JSONResponse | None]`: `None` → `([], None)`; invalid JSON, non-list, or a non-string element → `400 {"error": "invalid_remove_fields"}`.
- `GET /api/v1/sbom/fix/field-catalog` returns `{"fstec_fields": [{"path", "status", **({"condition_key": ...} if set)}], "default_keep": list(DEFAULT_KEEP_FIELDS)}`.
- `POST /api/v1/sbom/fix/analyze` reuses `_load_sbom`, then returns `{"fields": [{"path": f.path, "status": f.status, "count": f.count} for f in analyze_fields(data)]}`.
- `fix_sbom_endpoint` gains `remove_fields: str | None = Form(None)`, parses it, and passes `remove_fields` to `fix_sbom`; stats serialization includes `"field": stat.field` only when it is not `None`.
- `save_sbom_fix_options`: before `model_validate`, if `body["options"]` is a dict and `body["options"].get("optional_fields")` is a dict, read `keep`; when it is a list, `invalid_keep_entries` returns a non-empty list → `400 invalid_options` with `detail` naming the entries. Non-list `keep` falls through to Pydantic and its usual 400.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_sbom_fix_api.py tests/test_sbom_fix_options_store.py -v`
Expected: PASS. Then `.venv/bin/ruff check src tests`.

- [ ] **Step 5: Commit**

```bash
git add src/purl_resolver/routes/sbom_fix.py tests/test_sbom_fix_api.py tests/test_sbom_fix_options_store.py
git commit -m "feat: expose optional field catalog and analysis api"
```

---

### Task 5: Frontend contract, rule catalog, locales, page adaptation

**Files:**
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/api/sbom.ts`
- Modify: `frontend/src/views/sbomFixerRules.ts`
- Modify: `frontend/src/i18n/locales/ru.json`
- Modify: `frontend/src/i18n/locales/en.json`
- Modify: `frontend/src/views/SbomFixer.vue`
- Test: `frontend/src/views/sbomFixerRules.test.ts`
- Test: `frontend/src/views/SbomFixer.test.ts`

**Interfaces:**
- Consumes: the API shape from Task 4.
- Produces:
  - Types: `OptionalFieldStatus`, `FstecField`, `OptionalFieldInfo`, `FieldCatalogResponse`, `OptionalFieldsFixOptions`; `SbomFixOptions.optional_fields`; `SbomFixStat.field?: string | null`
  - `analyzeSbom(file: File): Promise<{ fields: OptionalFieldInfo[] }>`
  - `getFieldCatalog(): Promise<FieldCatalogResponse>`
  - `fixSbom(file, options, removeFields?: string[])`
  - 11-entry `ALL_FIX_RULES`

- [ ] **Step 1: Update the failing catalog test**

In `frontend/src/views/sbomFixerRules.test.ts`, change the group sizes and count:

```ts
const GROUPS = [
  { rules: ROOT_RULES, prefix: 'root.', size: 3 },
  { rules: METADATA_RULES, prefix: 'metadata.', size: 2 },
  { rules: METADATA_COMPONENT_RULES, prefix: 'metadata_component.', size: 2 },
  { rules: COMPONENTS_RULES, prefix: 'components.', size: 4 },
]

it('covers all 11 rules with unique ids', () => {
  expect(ALL_FIX_RULES).toHaveLength(11)
  expect(new Set(ALL_FIX_RULES.map((rule) => rule.id)).size).toBe(11)
})
```

Add a check that the removed ids are absent and the new one is present:

```ts
it('replaces rename_supplier with add_manufacturer and drops removal rules', () => {
  const ids = ALL_FIX_RULES.map((rule) => rule.id)
  expect(ids).toContain('metadata_component.add_manufacturer')
  for (const id of [
    'root.remove_dependencies', 'root.remove_services',
    'metadata.remove_properties', 'metadata.remove_tools',
    'metadata_component.remove_external_references', 'metadata_component.remove_purl',
    'metadata_component.remove_scope', 'metadata_component.rename_supplier',
    'components.remove_hashes', 'components.remove_scope',
  ]) {
    expect(ids).not.toContain(id)
  }
})
```

In `frontend/src/views/SbomFixer.test.ts`, mechanically adapt the existing suite to the new contract so the page keeps compiling and its current behavior stays covered:

- Replace `defaultOptions` with the Task 3 shape, including `manufacturer: 'Positive Technologies'` and `optional_fields: { keep: [...ten paths] }`.
- Change the help-button count from 21 to 11.
- Replace selectors for deleted rules with surviving ones: `components.remove_hashes` → `components.filter_properties`, `root.remove_services` → `root.increment_version`, `metadata_component.remove_purl` → `metadata_component.add_manufacturer`.
- In the master-checkbox tests, replace the deleted ids in the expected lists with the surviving ids of each group.
- Delete tests that assert behavior of deleted rules only; keep the master, select/clear, save, spec-version input, result, stats, issues, and download tests.
- Add one test: the manufacturer input is disabled when `add_manufacturer` is off and its value is saved with the options.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npm test --prefix frontend -- --run src/views/sbomFixerRules.test.ts src/views/SbomFixer.test.ts`
Expected: FAIL on the 21-rule count, missing `add_manufacturer`, and old option keys.

- [ ] **Step 3: Update types, client, catalog, locales, and adapt the page**

- `types/api.ts`: delete the removed booleans; add `add_manufacturer: boolean`, `manufacturer: string`; add the new interfaces and `optional_fields: { keep: string[] }`; add `field?: string | null` to `SbomFixStat`.
- `api/sbom.ts`: add `analyzeSbom` and `getFieldCatalog`; change `fixSbom` to accept `removeFields: string[] = []` and append `remove_fields` as `JSON.stringify(removeFields)`.
- `sbomFixerRules.ts`: keep `ROOT_RULES` = reorder, set_spec_version, increment_version; `METADATA_RULES` = reorder, add_timestamp; `METADATA_COMPONENT_RULES` = reorder, add_manufacturer (before/after examples: component without `manufacturer` → `manufacturer: {name: "Positive Technologies"}`); `COMPONENTS_RULES` = reorder, filter_external_references, filter_properties, fill_missing_gost_properties. Delete the ten removed entries.
- Locales: delete `rules`/`help` keys for the ten removed rules and `rename_supplier`; add `rules.metadata_component.add_manufacturer` and `help.metadata_component.add_manufacturer` in both languages. Add the new card keys:
  `optionalFields.title`, `description`, `analyze`, `analyzing`, `needFile`, `needAnalysis`, `empty`, `path`, `occurrences`, `fstecTitle`, `keepTitle`, `keepHint`, `fstecStatusMandatory`, `fstecStatusOptional`, `conditionComponentsPresent`, `conditionSourceDistributionHashes`, `remove`, `catalogLoadFailed`; plus `manufacturer`; plus `errors.invalid_remove_fields`. The catalog returns `condition_key` = `componentsPresent` or `sourceDistributionHashes`; the UI maps those to the two `condition*` keys.
- `SbomFixer.vue`: update `defaultFixOptions()` to the Task 3 shape with `optional_fields: { keep: [] }`; extend `applyOptions` to merge `optional_fields`; the rule rows shrink automatically because they iterate the catalog arrays. Add the `metadata_component.add_manufacturer` text input next to its checkbox, bound to `options.metadata.component.manufacturer` and disabled when the rule is off, mirroring the `specVersion` input. Do not add the analysis card yet.

- [ ] **Step 4: Run the tests and type check**

Run: `npm test --prefix frontend -- --run src/views/sbomFixerRules.test.ts src/views/SbomFixer.test.ts`
Expected: PASS (11 rules, adapted page tests).
Run: `npm run build --prefix frontend`
Expected: `vue-tsc` passes; this task must leave the frontend buildable on its own.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/api.ts frontend/src/api/sbom.ts frontend/src/views/sbomFixerRules.ts frontend/src/i18n/locales/ru.json frontend/src/i18n/locales/en.json frontend/src/views/SbomFixer.vue frontend/src/views/sbomFixerRules.test.ts frontend/src/views/SbomFixer.test.ts
git commit -m "feat: update fix sbom frontend contract and rule catalog"
```

---

### Task 6: Fix SBOM page — analysis card and keep lists

**Files:**
- Modify: `frontend/src/views/SbomFixer.vue`
- Test: `frontend/src/views/SbomFixer.test.ts`

**Interfaces:**
- Consumes: Task 5 types, client, catalog; Task 4 endpoints.
- Produces: the new card `data-group="optional-fields"`, analysis state, candidate filtering, `remove_fields` on fix.

- [ ] **Step 1: Update the failing page tests**

In `frontend/src/views/SbomFixer.test.ts`, keep the Task 5 fixture and add `analyzeSbom`/`getFieldCatalog` mocks. Add tests:

```ts
it('analyzes the file and renders unchecked candidates', async () => {
  // select file, click [data-action="analyze"]
  // analyzeSbom resolves { fields: [
  //   { path: 'root.dependencies', status: 'additional', count: 1 },
  //   { path: 'root.version', status: 'mandatory', count: 1 },
  //   { path: 'components[].scope', status: 'additional', count: 3 },
  //   { path: 'components[].group', status: 'additional', count: 2 },
  // ]}
  // expect rows for root.dependencies and components[].scope, counts shown
  // expect no row for root.version or components[].group (keep list)
  // expect all checkboxes unchecked
})

it('recomputes candidates immediately when the keep list is edited', async () => {
  // analyze, then type a textarea without 'components[].group'
  // expect the group row to appear without another analyze call
})

it('drops a selected path when it is added to the keep list', async () => {
  // select components[].scope, add it to the textarea, expect checkbox row gone
})

it('sends only selected candidates as remove_fields', async () => {
  // analyze, check root.dependencies, click fix
  // expect fixSbom called with file, options, ['root.dependencies']
})

it('select all and clear all only affect candidates', async () => {
  // analyze; click select-all; expect every candidate checked;
  // click clear-all; expect none checked; static rule checkboxes unchanged
})

it('renders the read-only fstec list with statuses', async () => {
  // getFieldCatalog resolves with root.bomFormat mandatory, root.serialNumber optional
  // open the details and expect both rows and localized statuses
})

it('reset defaults restores the ten keep paths and static options', async () => {
  // clear some options and the textarea, click reset-defaults,
  // expect manufacturer 'Positive Technologies' and the 10 paths
})

it('new file selection resets analysis and selection', async () => {
  // analyze + select, select another file, expect candidates gone
})

it('catalog failure does not block the page and keeps the list on reset', async () => {
  // getFieldCatalog rejects; page still renders, warning shown,
  // reset leaves the current keep textarea unchanged
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npm test --prefix frontend -- --run src/views/SbomFixer.test.ts`
Expected: FAIL on missing selectors and changed options.

- [ ] **Step 3: Implement the page**

- `defaultFixOptions()` was updated in Task 5; no change is needed here except keeping `optional_fields.keep` as `[]` until the mounted requests populate it.
- On mount, `Promise.allSettled([getFixOptions(), settingsStore.load(), getFieldCatalog()])`; store `fieldCatalog` and `catalogFailed`; do not block the page. If `getFixOptions` failed but the catalog loaded, set `options.optional_fields.keep = fieldCatalog.value.default_keep`; if both failed, leave it empty and show the warnings.
- Add `analysis = ref<OptionalFieldInfo[] | null>(null)`, `analysisLoading`, `selectedRemoveFields = ref<Set<string>>(new Set())`.
- `candidates = computed(() => (analysis.value ?? []).filter(f => f.status === 'additional' && !options.optional_fields.keep.includes(f.path)))`.
- `keepText = computed({ get: () => options.optional_fields.keep.join('\n'), set: v => options.optional_fields.keep = v.split('\n') })`; add a watcher that removes paths no longer in `candidates` from `selectedRemoveFields`.
- `handleAnalyze()`: guards on file, clears error/result, calls `analyzeSbom`, sets `analysis`, clears selection.
- `onFileSelected` additionally resets `analysis` and `selectedRemoveFields`.
- `handleFix()` passes `[...selectedRemoveFields]` as the third argument.
- `restoreDefaults()` uses `fieldCatalog.value?.default_keep ?? options.optional_fields.keep`.
- Template: new card after `components`, before `.toolbar`; table rows with `:data-field="field.path"`, `:data-count="field.count"`, checkbox `:data-remove-field="field.path"`; analyze button `data-action="analyze"`; keep `<textarea data-role="keep-list">`; list 1 in `<details data-role="fstec-list">`; select-all/clear-all buttons with `data-action="select-all-fields"` / `data-action="clear-all-fields"`.
- Statistics: render `stat.field ? `${t('sbomFixer.optionalFields.remove')}: ${stat.field}` : t('sbomFixer.rules.' + stat.rule_id)`.

- [ ] **Step 4: Run the tests and build**

Run: `npm test --prefix frontend -- --run src/views/SbomFixer.test.ts src/views/sbomFixerRules.test.ts`
Expected: PASS.
Run: `npm run build --prefix frontend`
Expected: `vue-tsc` passes.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/SbomFixer.vue frontend/src/views/SbomFixer.test.ts
git commit -m "feat: add optional field analysis card to fix sbom page"
```

---

### Task 7: Update project specifications

**Files:**
- Modify: `specs/domains/sbom-fixing.md`
- Modify: `specs/contracts/api-contract.md`
- Modify: `specs/domains/web-ui.md`
- Modify: `specs/architecture/layers.md`
- Modify: `specs/INDEX.md`

**Interfaces:**
- Consumes: the implemented behavior from Tasks 1–6.
- Produces: specs matching the code; no runtime behavior.

- [ ] **Step 1: Update `specs/domains/sbom-fixing.md`**

- Description: 11 static rules plus analysis-driven removal; cosmetic cleanup; list 1/list 2.
- Core Types: new models, `RULE_IDS`, `FSTEC_FIELDS`, `DEFAULT_KEEP_FIELDS`, `FixStat.field`, `fix_sbom` signature with `remove_fields`.
- Rules: remove the tables for the ten deleted rules and `rename_supplier`; add `metadata_component.add_manufacturer`; add the removal semantics, traversal boundaries, and pipeline order.
- Statistics: enabled-only static rows, then removal rows with `field`.
- API: catalog, analyze, `remove_fields`, `invalid_remove_fields`, strict keep validation on save.
- Invariants: nothing removed by default; protected paths ignored; input not mutated; `metadata.component.components` untouched.
- Key Files: add `sbom/optional_fields.py` and the test file.

- [ ] **Step 2: Update the other specs**

- `specs/contracts/api-contract.md`: document the two new endpoints, their payloads and error codes; extend `/fix` and `/options`.
- `specs/domains/web-ui.md`: describe the new card, analysis flow, two white lists, state, and page tests.
- `specs/architecture/layers.md`: add `sbom/optional_fields.py`, its stdlib-only dependency rule, and the new routes.
- `specs/INDEX.md`: add the new design doc and `optional_fields.py`.

- [ ] **Step 3: Verify cross-references and format**

Run: `grep -rn "remove_dependencies\|remove_hashes\|rename_supplier\|21 правил\|21 rules" specs/`
Expected: no stale references outside historical design docs under `docs/superpowers/`.

Run: `.venv/bin/python -m pytest && .venv/bin/ruff check src tests && npm test --prefix frontend && npm run build --prefix frontend`
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add specs/
git commit -m "docs: update specs for optional field removal"
```

---

## Self-Review Notes

- Spec coverage: catalog/list 1 (§6.1 → Task 1), list 2 and grammar (§6.2–6.3 → Tasks 1, 4, 6), analysis (§7 → Tasks 2, 4), removal and pipeline (§8 → Tasks 2–3), `add_manufacturer` (§9 → Task 3), options (§10 → Task 3), stats (§11 → Task 3), API (§12 → Task 4), frontend (§13 → Tasks 5–6), files (§14 → Tasks 1–7), tests (§15 → every task), specs (§16 → Task 7).
- Types are consistent across tasks: `FieldInfo`/`OptionalFieldInfo`, `remove_optional_fields`/`remove_fields`, `canonical_sort_key`, `DEFAULT_KEEP_FIELDS`, `invalid_keep_entries`.
- The five Review Focus items each have a pinned test: metadata.component.components and weird keys in Task 2; old options/invalid keep in Tasks 3–4; licenses side effect in Task 3.
