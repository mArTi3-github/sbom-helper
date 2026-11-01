# SBOM Fixer — Component License Edits Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add three license rules to the "Исправить SBOM" section: strip non-`Proprietary` license entries, add `{"license": {"name": "Proprietary"}}` to components matched by a server-persisted field/value list, and drop `vcs`/`source-distribution` external references from proprietary components.

**Architecture:** The three rules live in `src/purl_resolver/sbom/fixer.py` as a new `_apply_licenses_rules` phase executed after the `components[]` rules and before issue collection, with options in a new `licenses` block of `SbomFixOptions` (persisted by the existing options store and endpoints). The frontend adds a fourth options card in `SbomFixer.vue` with an inline pattern-row editor, a rule catalog entry per rule in `sbomFixerRules.ts`, and i18n labels in both locales.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, pytest (`.venv`); Vue 3 `<script setup>`, Pinia, vue-i18n, Vitest, vue-tsc.

**Spec:** `docs/superpowers/specs/2026-11-01-sbom-fixer-licenses-design.md`

## Global Constraints

- Work in the current checkout on `main`; no worktree. Each task ends with a local commit (no push) whose message follows the repo style (`feat:` / `fix:` / `test:` / `docs:` plus a short description); the commit SHA goes into the task report.
- Python commands run as `.venv/bin/python -m pytest ...`; frontend commands as `npm --prefix frontend run test` / `npm --prefix frontend run build`.
- Proprietary licence detection is exact and case-sensitive: `entry.license.name == "Proprietary"`, where `entry` is a `dict` with a `dict` under `"license"`. `license.id` and `expression` never count as proprietary.
- All three new flags default to `False`; `add_patterns` defaults to `[]`.
- Matching uses the enrichment semantics: top-level component field, value must exist and not be `None`, substring check on `str(value)`, any matching pair is enough. `field` and `pattern` are stripped; incomplete pairs are ignored on both frontend and backend.
- Rule ids and execution order: `licenses.filter_non_proprietary`, `licenses.add_proprietary`, `licenses.remove_proprietary_source_references`, in that order, after the three `components.*` rules.
- `externalReferences` is never deleted; if it becomes empty it stays as `[]`.
- `metadata.component` is never touched by the license rules.
- No new endpoints, stores, or public API changes beyond the `licenses` block inside the existing options payload.
- Every user-facing string goes through `frontend/src/i18n/locales/ru.json` and `en.json`; API errors stay machine-readable codes.
- `fix_sbom()` keeps working on a deep copy of the input document.
- Russian UI labels are fixed by the spec: «Удалить все лицензии без поля с ключом `name`, равным «Proprietary»», «Добавить лицензию с ключом `name`, равным «Proprietary» для компонентов со следующими признаками:», «Удалить ссылки `vcs` и `source-distribution` у компонентов с проприетарной лицензией», card title «Правки, касающиеся лицензий компонентов».

## Review Focus

- A component whose `licenses` is `null`, a string, or an object must not crash the fixer: `null` is "absent" only for the add rule (an array is created), while non-list values leave the component untouched for all three rules.
- Components without the matched field, or with an explicit `null`, must not match a pattern (a naive `str(component.get(field))` makes `no` match `"None"` and can strip real source links).
- `licenses` arrays containing `license.id`-only or `expression` entries must be handled as non-proprietary both in the filter rule and when deciding whether a component already has a proprietary entry.
- An `externalReferences` array that contains only `vcs`/`source-distribution` entries must end up as `[]`, with the key still present.
- Deeply nested `components[]` (and `metadata.component.licenses`) must be handled correctly: recursion reaches every nesting level, and `metadata.component` is left byte-for-byte unchanged.
- An options JSON written before this change (no `licenses` block) must load with defaults, and an unknown/invalid `add_patterns` value must produce `400 invalid_options` rather than a 500.

---

### Task 1: Backend options model, rule ids, and persistence

**Files:**
- Modify: `src/purl_resolver/sbom/fixer.py:51-96` (constants and option models), `src/purl_resolver/sbom/fixer.py:140-148` (`_rule_enabled`)
- Modify: `src/purl_resolver/sbom/__init__.py`
- Test: `tests/test_sbom_fixer.py`, `tests/test_sbom_fix_options_store.py`, `tests/test_sbom_fix_api.py`

**Interfaces:**
- Consumes: existing `ComponentsFixOptions`, `SbomFixOptions`, `RULE_IDS`, `_rule_enabled`, `SbomFixOptionsStore`, endpoints `GET/POST /api/v1/sbom/fix/options`.
- Produces:
  ```python
  class LicensePatternItem(BaseModel):
      field: str = ""
      pattern: str = ""

  class LicensesFixOptions(BaseModel):
      filter_non_proprietary: bool = False
      add_proprietary: bool = False
      remove_proprietary_source_references: bool = False
      add_patterns: list[LicensePatternItem] = Field(default_factory=list)
  ```
  `SbomFixOptions.licenses: LicensesFixOptions`; `RULE_IDS` grows to 11 entries ending with the three `licenses.*` ids in the order above; `_rule_enabled("licenses.<name>", options)` returns `getattr(options.licenses, "<name>")`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_sbom_fixer.py`:

```python
from purl_resolver.sbom.fixer import (
    LicensePatternItem,
    LicensesFixOptions,
)


def test_licenses_options_default_to_disabled():
    options = SbomFixOptions()
    assert options.licenses.filter_non_proprietary is False
    assert options.licenses.add_proprietary is False
    assert options.licenses.remove_proprietary_source_references is False
    assert options.licenses.add_patterns == []


def test_license_rule_ids_come_last_in_execution_order():
    assert len(RULE_IDS) == 11
    assert RULE_IDS[-3:] == (
        "licenses.filter_non_proprietary",
        "licenses.add_proprietary",
        "licenses.remove_proprietary_source_references",
    )


def test_enabled_license_rule_gets_zero_stat_row():
    data = {"components": []}
    options = SbomFixOptions(licenses={"filter_non_proprietary": True})
    result = fix_sbom(data, options)
    stats = {stat.rule_id: stat.count for stat in result.stats}
    assert stats["licenses.filter_non_proprietary"] == 0
    assert "licenses.add_proprietary" not in stats


def test_license_pattern_item_defaults_are_empty_strings():
    item = LicensePatternItem()
    assert item.field == ""
    assert item.pattern == ""
```

Add to `tests/test_sbom_fix_options_store.py`:

```python
from purl_resolver.sbom.fixer import (
    LicensePatternItem,
    LicensesFixOptions,
)


def test_save_load_roundtrip_including_licenses(tmp_path):
    store = SbomFixOptionsStore(tmp_path / "options.json")
    options = SbomFixOptions(
        licenses=LicensesFixOptions(
            add_proprietary=True,
            add_patterns=[LicensePatternItem(field="name", pattern="vendor")],
        )
    )
    store.save(options)
    assert store.load() == options


def test_old_file_without_licenses_block_uses_defaults(tmp_path):
    path = tmp_path / "old.json"
    path.write_text('{"reorder": false}', encoding="utf-8")
    loaded = SbomFixOptionsStore(path).load()
    assert loaded.reorder is False
    assert loaded.licenses == LicensesFixOptions()
```

Add to `tests/test_sbom_fix_api.py`:

```python
def test_save_options_roundtrips_licenses_block(client):
    payload = {
        "options": {
            "licenses": {
                "add_proprietary": True,
                "add_patterns": [{"field": "name", "pattern": "vendor"}],
            }
        }
    }
    response = client.post("/api/v1/sbom/fix/options", json=payload)
    assert response.status_code == 200
    options = client.get("/api/v1/sbom/fix/options").json()["options"]
    assert options["licenses"]["add_proprietary"] is True
    assert options["licenses"]["add_patterns"] == [{"field": "name", "pattern": "vendor"}]


def test_save_options_rejects_non_list_patterns(client):
    response = client.post(
        "/api/v1/sbom/fix/options",
        json={"options": {"licenses": {"add_patterns": "name"}}},
    )
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_options"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_sbom_fixer.py tests/test_sbom_fix_options_store.py tests/test_sbom_fix_api.py -q`
Expected: FAIL — collection errors from `ImportError: cannot import name 'LicensePatternItem'` and the new `licenses`-related assertions.

- [ ] **Step 3: Add the models, ids, and dispatch**

In `src/purl_resolver/sbom/fixer.py`:

- Append the three ids to `RULE_IDS` in the order from Interfaces.
- Add `LicensePatternItem` and `LicensesFixOptions` before `SbomFixOptions`.
- Add `licenses: LicensesFixOptions = Field(default_factory=LicensesFixOptions)` to `SbomFixOptions` after `components`.
- Replace `_rule_enabled` with a prefix-aware version:

```python
def _rule_enabled(rule_id: str, options: SbomFixOptions) -> bool:
    prefix, _, name = rule_id.partition(".")
    if prefix == "components":
        return getattr(options.components, name)
    if prefix == "licenses":
        return getattr(options.licenses, name)
    return getattr(options, rule_id)
```

In `src/purl_resolver/sbom/__init__.py`, import and export `LicensePatternItem` and `LicensesFixOptions` alongside `OptionalFieldsFixOptions`.

No changes to `fix_sbom()` are needed in this task: enabled ids already get a zero-count `FixStat`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_sbom_fixer.py tests/test_sbom_fix_options_store.py tests/test_sbom_fix_api.py -q`
Expected: PASS.

---

### Task 2: `licenses.filter_non_proprietary` rule

**Files:**
- Modify: `src/purl_resolver/sbom/fixer.py` (constants near `ALLOWED_EXTERNAL_REFERENCE_TYPES`; helpers after `_fill_gost_properties`; new `_apply_licenses_rules`; call site in `fix_sbom`)
- Test: `tests/test_sbom_fixer.py`

**Interfaces:**
- Consumes: `LicensesFixOptions` from Task 1, existing `_walk_components`, `fix_sbom`.
- Produces:
  ```python
  PROPRIETARY_LICENSE_NAME = "Proprietary"

  def _is_proprietary_license_entry(entry: Any) -> bool: ...
  def _has_proprietary_license(component: dict) -> bool: ...
  def _filter_non_proprietary_licenses(component: dict) -> int: ...
  def _apply_licenses_rules(data: dict, options: SbomFixOptions, counts: dict[str, int]) -> None: ...
  ```

- [ ] **Step 1: Write the failing tests**

Add helpers and tests to `tests/test_sbom_fixer.py`:

```python
def _license_options(**licenses) -> SbomFixOptions:
    return SbomFixOptions(
        reorder=False,
        set_spec_version=False,
        increment_version=False,
        add_timestamp=False,
        add_manufacturer=False,
        components={
            "filter_external_references": False,
            "filter_properties": False,
        },
        licenses=licenses,
    )


def _stat(result, rule_id):
    return next(stat for stat in result.stats if stat.rule_id == rule_id)


def test_filter_non_proprietary_keeps_only_proprietary_entries():
    data = {
        "components": [
            {
                "type": "library",
                "name": "lib",
                "version": "1.0.0",
                "purl": "pkg:pypi/lib@1.0.0",
                "licenses": [
                    {"license": {"id": "MIT"}},
                    {"license": {"name": "Proprietary"}},
                    {"expression": "Apache-2.0"},
                ],
            }
        ]
    }
    result = fix_sbom(data, _license_options(filter_non_proprietary=True))
    component = result.fixed_sbom["components"][0]
    assert component["licenses"] == [{"license": {"name": "Proprietary"}}]
    assert _stat(result, "licenses.filter_non_proprietary").count == 2


def test_filter_non_proprietary_walks_nested_components():
    data = {
        "components": [
            {
                "name": "parent",
                "components": [
                    {"name": "child", "licenses": [{"license": {"id": "MIT"}}]}
                ],
            }
        ]
    }
    result = fix_sbom(data, _license_options(filter_non_proprietary=True))
    child = result.fixed_sbom["components"][0]["components"][0]
    assert "licenses" not in child
    assert _stat(result, "licenses.filter_non_proprietary").count == 1


def test_filter_non_proprietary_removes_emptied_array():
    data = {"components": [{"name": "lib", "licenses": [{"license": {"id": "MIT"}}]}]}
    result = fix_sbom(data, _license_options(filter_non_proprietary=True))
    assert "licenses" not in result.fixed_sbom["components"][0]


def test_filter_non_proprietary_leaves_preexisting_empty_array():
    data = {"components": [{"name": "lib", "licenses": []}]}
    result = fix_sbom(data, _license_options(filter_non_proprietary=True))
    assert result.fixed_sbom["components"][0]["licenses"] == []
    assert _stat(result, "licenses.filter_non_proprietary").count == 0


def test_filter_non_proprietary_leaves_non_list_licenses():
    data = {"components": [{"name": "lib", "licenses": "MIT"}]}
    result = fix_sbom(data, _license_options(filter_non_proprietary=True))
    assert result.fixed_sbom["components"][0]["licenses"] == "MIT"
    assert _stat(result, "licenses.filter_non_proprietary").count == 0


def test_filter_non_proprietary_does_not_touch_metadata_component():
    data = {
        "metadata": {
            "component": {"name": "app", "licenses": [{"license": {"id": "MIT"}}]}
        }
    }
    result = fix_sbom(data, _license_options(filter_non_proprietary=True))
    assert result.fixed_sbom["metadata"]["component"]["licenses"] == [
        {"license": {"id": "MIT"}}
    ]
    assert _stat(result, "licenses.filter_non_proprietary").count == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_sbom_fixer.py -k filter_non_proprietary -q`
Expected: FAIL — `AssertionError` (licenses untouched, stat absent or zero).

- [ ] **Step 3: Implement the filter rule**

In `src/purl_resolver/sbom/fixer.py`:

```python
PROPRIETARY_LICENSE_NAME = "Proprietary"


def _is_proprietary_license_entry(entry: Any) -> bool:
    return (
        isinstance(entry, dict)
        and isinstance(entry.get("license"), dict)
        and entry["license"].get("name") == PROPRIETARY_LICENSE_NAME
    )


def _has_proprietary_license(component: dict) -> bool:
    licenses = component.get("licenses")
    return isinstance(licenses, list) and any(
        _is_proprietary_license_entry(entry) for entry in licenses
    )


def _filter_non_proprietary_licenses(component: dict) -> int:
    licenses = component.get("licenses")
    if not isinstance(licenses, list):
        return 0
    kept = [entry for entry in licenses if _is_proprietary_license_entry(entry)]
    removed = len(licenses) - len(kept)
    if not removed:
        return 0
    if kept:
        component["licenses"] = kept
    else:
        del component["licenses"]
    return removed


def _apply_licenses_rules(
    data: dict,
    options: SbomFixOptions,
    counts: dict[str, int],
) -> None:
    filter_non_proprietary = options.licenses.filter_non_proprietary

    def apply(component: dict) -> None:
        if filter_non_proprietary:
            counts["licenses.filter_non_proprietary"] = (
                counts.get("licenses.filter_non_proprietary", 0)
                + _filter_non_proprietary_licenses(component)
            )

    _walk_components(data, apply)
```

In `fix_sbom()`, call `_apply_licenses_rules(fixed_sbom, options, counts)` immediately after `_apply_components_rules(fixed_sbom, options, counts)` and before `_apply_reorder(...)`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_sbom_fixer.py -q`
Expected: PASS.

---

### Task 3: `licenses.add_proprietary` rule

**Files:**
- Modify: `src/purl_resolver/sbom/fixer.py` (helpers next to the Task 2 helpers; extend `_apply_licenses_rules`)
- Test: `tests/test_sbom_fixer.py`

**Interfaces:**
- Consumes: `PROPRIETARY_LICENSE_NAME`, `_is_proprietary_license_entry`, `_has_proprietary_license`, `_apply_licenses_rules` from Task 2; `LicensePatternItem` from Task 1.
- Produces:
  ```python
  def _matches_license_patterns(component: dict, patterns: list[tuple[str, str]]) -> bool: ...
  def _add_proprietary_license(component: dict, patterns: list[tuple[str, str]]) -> int: ...
  ```
  `_apply_licenses_rules` applies the add step after the filter step for every component.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_sbom_fixer.py`:

```python
def test_add_proprietary_matches_any_pattern_by_substring():
    data = {
        "components": [
            {"name": "vendor-lib", "licenses": [{"license": {"id": "MIT"}}]},
            {"name": "other"},
        ]
    }
    options = _license_options(
        add_proprietary=True,
        add_patterns=[
            {"field": "name", "pattern": "vendor"},
            {"field": "version", "pattern": "9.9"},
        ],
    )
    result = fix_sbom(data, options)
    components = result.fixed_sbom["components"]
    assert components[0]["licenses"] == [
        {"license": {"id": "MIT"}},
        {"license": {"name": "Proprietary"}},
    ]
    assert "licenses" not in components[1]
    assert _stat(result, "licenses.add_proprietary").count == 1


def test_add_proprietary_skips_missing_and_null_fields():
    data = {"components": [{"name": "no"}, {"name": "lib", "scope": None}]}
    options = _license_options(
        add_proprietary=True,
        add_patterns=[
            {"field": "scope", "pattern": "no"},
            {"field": "author", "pattern": "no"},
        ],
    )
    result = fix_sbom(data, options)
    assert "licenses" not in result.fixed_sbom["components"][0]
    assert "licenses" not in result.fixed_sbom["components"][1]
    assert _stat(result, "licenses.add_proprietary").count == 0


def test_add_proprietary_ignores_blank_pairs():
    data = {"components": [{"name": "lib"}]}
    options = _license_options(
        add_proprietary=True,
        add_patterns=[
            {"field": "  ", "pattern": "lib"},
            {"field": "name", "pattern": "   "},
        ],
    )
    result = fix_sbom(data, options)
    assert "licenses" not in result.fixed_sbom["components"][0]
    assert _stat(result, "licenses.add_proprietary").count == 0


def test_add_proprietary_creates_array_for_absent_and_null_licenses():
    data = {"components": [{"name": "lib"}, {"name": "lib2", "licenses": None}]}
    options = _license_options(
        add_proprietary=True,
        add_patterns=[{"field": "name", "pattern": "lib"}],
    )
    result = fix_sbom(data, options)
    for component in result.fixed_sbom["components"]:
        assert component["licenses"] == [{"license": {"name": "Proprietary"}}]
    assert _stat(result, "licenses.add_proprietary").count == 2


def test_add_proprietary_does_not_duplicate_existing_entry():
    data = {
        "components": [
            {
                "name": "lib",
                "licenses": [{"license": {"name": "Proprietary"}}],
            }
        ]
    }
    options = _license_options(
        add_proprietary=True,
        add_patterns=[{"field": "name", "pattern": "lib"}],
    )
    result = fix_sbom(data, options)
    assert result.fixed_sbom["components"][0]["licenses"] == [
        {"license": {"name": "Proprietary"}}
    ]
    assert _stat(result, "licenses.add_proprietary").count == 0


def test_add_proprietary_skips_non_list_licenses():
    data = {"components": [{"name": "lib", "licenses": "MIT"}]}
    options = _license_options(
        add_proprietary=True,
        add_patterns=[{"field": "name", "pattern": "lib"}],
    )
    result = fix_sbom(data, options)
    assert result.fixed_sbom["components"][0]["licenses"] == "MIT"
    assert _stat(result, "licenses.add_proprietary").count == 0


def test_add_proprietary_does_not_touch_metadata_component():
    data = {"metadata": {"component": {"name": "vendor-app"}}}
    options = _license_options(
        add_proprietary=True,
        add_patterns=[{"field": "name", "pattern": "vendor"}],
    )
    result = fix_sbom(data, options)
    assert "licenses" not in result.fixed_sbom["metadata"]["component"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_sbom_fixer.py -k add_proprietary -q`
Expected: FAIL — no licenses added.

- [ ] **Step 3: Implement the add rule**

In `src/purl_resolver/sbom/fixer.py`:

```python
def _matches_license_patterns(
    component: dict, patterns: list[tuple[str, str]]
) -> bool:
    for field, pattern in patterns:
        value = component.get(field)
        if value is not None and pattern in str(value):
            return True
    return False


def _add_proprietary_license(
    component: dict, patterns: list[tuple[str, str]]
) -> int:
    if not patterns or not _matches_license_patterns(component, patterns):
        return 0
    if _has_proprietary_license(component):
        return 0
    licenses = component.get("licenses")
    if licenses is None:
        licenses = []
        component["licenses"] = licenses
    elif not isinstance(licenses, list):
        return 0
    licenses.append({"license": {"name": PROPRIETARY_LICENSE_NAME}})
    return 1
```

Extend `_apply_licenses_rules` — build the normalized pattern list once, before `apply`:

```python
    add_proprietary = options.licenses.add_proprietary
    patterns = [
        (item.field.strip(), item.pattern.strip())
        for item in options.licenses.add_patterns
        if item.field.strip() and item.pattern.strip()
    ]
```

and inside `apply`, after the filter step:

```python
        if add_proprietary:
            counts["licenses.add_proprietary"] = (
                counts.get("licenses.add_proprietary", 0)
                + _add_proprietary_license(component, patterns)
            )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_sbom_fixer.py -q`
Expected: PASS.

---

### Task 4: `licenses.remove_proprietary_source_references` rule and cross-rule ordering

**Files:**
- Modify: `src/purl_resolver/sbom/fixer.py` (helper next to the Task 3 helpers; extend `_apply_licenses_rules`)
- Test: `tests/test_sbom_fixer.py`, `tests/test_sbom_fix_api.py`

**Interfaces:**
- Consumes: `ALLOWED_EXTERNAL_REFERENCE_TYPES`, `_has_proprietary_license`, `_apply_licenses_rules`, `fix_sbom`.
- Produces:
  ```python
  def _remove_proprietary_source_references(component: dict) -> int: ...
  ```
  `_apply_licenses_rules` applies the reference step after the add step for every component, in the same single walk.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_sbom_fixer.py`:

```python
def test_remove_proprietary_source_references_keeps_other_types():
    data = {
        "components": [
            {
                "name": "lib",
                "licenses": [{"license": {"name": "Proprietary"}}],
                "externalReferences": [
                    {"type": "vcs", "url": "https://example.com/repo"},
                    {"type": "website", "url": "https://example.com"},
                    {"type": "source-distribution", "url": "https://example.com/archive"},
                ],
            }
        ]
    }
    options = _license_options(remove_proprietary_source_references=True)
    result = fix_sbom(data, options)
    component = result.fixed_sbom["components"][0]
    assert component["externalReferences"] == [
        {"type": "website", "url": "https://example.com"}
    ]
    assert _stat(result, "licenses.remove_proprietary_source_references").count == 2


def test_remove_proprietary_source_references_keeps_emptied_array():
    data = {
        "components": [
            {
                "name": "lib",
                "licenses": [{"license": {"name": "Proprietary"}}],
                "externalReferences": [
                    {"type": "vcs", "url": "https://example.com/repo"}
                ],
            }
        ]
    }
    options = _license_options(remove_proprietary_source_references=True)
    result = fix_sbom(data, options)
    component = result.fixed_sbom["components"][0]
    assert component["externalReferences"] == []


def test_remove_proprietary_source_references_skips_non_proprietary():
    data = {
        "components": [
            {
                "name": "lib",
                "licenses": [{"license": {"id": "MIT"}}],
                "externalReferences": [
                    {"type": "vcs", "url": "https://example.com/repo"}
                ],
            }
        ]
    }
    options = _license_options(remove_proprietary_source_references=True)
    result = fix_sbom(data, options)
    assert result.fixed_sbom["components"][0]["externalReferences"] == [
        {"type": "vcs", "url": "https://example.com/repo"}
    ]
    assert _stat(result, "licenses.remove_proprietary_source_references").count == 0


def test_add_proprietary_then_removes_source_references_and_exempts_issue():
    data = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.7",
        "version": 1,
        "metadata": {
            "timestamp": "2026-01-01T00:00:00Z",
            "component": {
                "type": "application",
                "name": "app",
                "version": "1.0.0",
                "manufacturer": {"name": "Example"},
            },
        },
        "components": [
            {
                "type": "library",
                "name": "vendor-lib",
                "version": "1.0.0",
                "purl": "pkg:pypi/vendor-lib@1.0.0",
                "properties": [
                    {"name": "GOST:attack_surface", "value": "no"},
                    {"name": "GOST:security_function", "value": "no"},
                ],
                "externalReferences": [
                    {"type": "vcs", "url": "https://example.com/repo"}
                ],
            }
        ],
    }
    options = SbomFixOptions(
        reorder=False,
        set_spec_version=False,
        increment_version=False,
        add_timestamp=False,
        add_manufacturer=False,
        licenses={
            "add_proprietary": True,
            "remove_proprietary_source_references": True,
            "add_patterns": [{"field": "name", "pattern": "vendor"}],
        },
    )
    result = fix_sbom(data, options)
    component = result.fixed_sbom["components"][0]
    assert component["licenses"] == [{"license": {"name": "Proprietary"}}]
    assert component["externalReferences"] == []
    assert not any(
        issue.code == "component.missing_source_reference" for issue in result.issues
    )
```

Add to `tests/test_sbom_fix_api.py`:

```python
def test_fix_endpoint_applies_license_options(client):
    sbom = make_sbom()
    sbom["components"][0]["name"] = "vendor-lib"
    options = {
        "licenses": {
            "add_proprietary": True,
            "add_patterns": [{"field": "name", "pattern": "vendor"}],
        }
    }
    response = upload_fix(client, sbom, options=options)
    assert response.status_code == 200
    body = response.json()
    assert body["fixed_sbom"]["components"][0]["licenses"] == [
        {"license": {"name": "Proprietary"}}
    ]
    stat = next(
        stat for stat in body["stats"] if stat["rule_id"] == "licenses.add_proprietary"
    )
    assert stat["count"] == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_sbom_fixer.py -k remove_proprietary -q` and then `.venv/bin/python -m pytest tests/test_sbom_fix_api.py -k license -q`
Expected: FAIL — references are not removed and the API test finds no `licenses` entry.

- [ ] **Step 3: Implement the reference rule and ordering**

In `src/purl_resolver/sbom/fixer.py`:

```python
def _remove_proprietary_source_references(component: dict) -> int:
    if not _has_proprietary_license(component):
        return 0
    references = component.get("externalReferences")
    if not isinstance(references, list):
        return 0
    kept = [
        reference
        for reference in references
        if not (
            isinstance(reference, dict)
            and reference.get("type") in ALLOWED_EXTERNAL_REFERENCE_TYPES
        )
    ]
    removed = len(references) - len(kept)
    if removed:
        component["externalReferences"] = kept
    return removed
```

Extend `_apply_licenses_rules` with `remove_source_references = options.licenses.remove_proprietary_source_references` and, inside `apply`, after the add step:

```python
        if remove_source_references:
            counts["licenses.remove_proprietary_source_references"] = (
                counts.get("licenses.remove_proprietary_source_references", 0)
                + _remove_proprietary_source_references(component)
            )
```

The per-component order inside `apply` must be filter → add → remove references.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_sbom_fixer.py tests/test_sbom_fix_api.py -q`
Expected: PASS.

- [ ] **Step 5: Run the full backend suite**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS. If only `tests/e2e/` fail on network timeouts, rerun with `SKIP_E2E=1 .venv/bin/python -m pytest -q` and report the network failure.

---

### Task 5: Frontend types, rule catalog, locales, and license card

**Files:**
- Modify: `frontend/src/types/api.ts:134-214` (`IgnorePatternItem` area and `SbomFixOptions`)
- Modify: `frontend/src/views/sbomFixerRules.ts`
- Modify: `frontend/src/views/SbomFixer.vue` (`defaultFixOptions`, `applyOptions`, new card template without the pattern editor)
- Modify: `frontend/src/i18n/locales/ru.json`, `frontend/src/i18n/locales/en.json`
- Test: `frontend/src/views/sbomFixerRules.test.ts`, `frontend/src/views/SbomFixer.test.ts`

**Interfaces:**
- Consumes: `IgnorePatternItem`, `ComponentsFixOptions`, existing `FixRule`, `BASE_RULES`, `COMPONENTS_RULES`, `ALL_FIX_RULES`, `RuleHelp`.
- Produces:
  ```ts
  export interface LicensesFixOptions {
    filter_non_proprietary: boolean
    add_proprietary: boolean
    remove_proprietary_source_references: boolean
    add_patterns: IgnorePatternItem[]
  }
  ```
  `SbomFixOptions.licenses: LicensesFixOptions`; `LicensesRuleKey`, `LICENSES_RULES` (3 entries), `ALL_FIX_RULES` (11 entries); `defaultFixOptions()` returns `licenses` with three `false` flags and `add_patterns: []`; `applyOptions()` deep-copies `licenses` including a fresh `add_patterns` array; a `data-group="licenses"` card with three `data-rule-row`/`data-rule` rules, a `.master-checkbox`, `.select-all`/`.clear-all`, and a `RuleHelp` per rule.


- [ ] **Step 1: Write the failing tests**

Update `frontend/src/views/sbomFixerRules.test.ts`:

```ts
import { ALL_FIX_RULES, BASE_RULES, COMPONENTS_RULES, LICENSES_RULES } from './sbomFixerRules'

const GROUPS = [
  { rules: BASE_RULES, prefix: '', size: 5, flat: true },
  { rules: COMPONENTS_RULES, prefix: 'components.', size: 3, flat: false },
  { rules: LICENSES_RULES, prefix: 'licenses.', size: 3, flat: false },
]
```

and replace the counts in the first test:

```ts
  it('covers all 11 rules with unique ids', () => {
    expect(ALL_FIX_RULES).toHaveLength(11)
    expect(new Set(ALL_FIX_RULES.map((rule) => rule.id)).size).toBe(11)
    for (const rule of ALL_FIX_RULES) {
      expect(rule.key, rule.id).toBe(rule.id.split('.').pop())
    }
  })
```

Add to the group test:

```ts
    expect(LICENSES_RULES.map((rule) => rule.id)).toEqual([
      'licenses.filter_non_proprietary',
      'licenses.add_proprietary',
      'licenses.remove_proprietary_source_references',
    ])
```

Also update the existing `'renders help for every rule'` test in `frontend/src/views/SbomFixer.test.ts`: change `toHaveLength(8)` to `toHaveLength(11)`.

Add to `frontend/src/views/SbomFixer.test.ts` — first extend the `defaultOptions` fixture with

```ts
  licenses: {
    filter_non_proprietary: false,
    add_proprietary: false,
    remove_proprietary_source_references: false,
    add_patterns: [],
  },
```

then add inside `describe`:

```ts
  it('renders the licenses card with three rules and help', async () => {
    const wrapper = await mountFixer()
    const card = wrapper.find('.group-card[data-group="licenses"]')
    expect(card.exists()).toBe(true)
    expect(card.findAll('[data-rule-row]')).toHaveLength(3)
    expect(card.findAll('.rule-help-button')).toHaveLength(3)
    for (const rule of LICENSES_RULES) {
      expect(card.find(`[data-help-for="${rule.id}"]`).exists(), rule.id).toBe(true)
    }
  })

  it('toggles all three license rules with the master checkbox', async () => {
    const wrapper = await mountFixer()
    const master = masterFor(wrapper, 'licenses')
    await master.setValue(true)
    for (const id of LICENSES_RULES.map((item) => item.id)) {
      expect((wrapper.find(rule(id)).element as HTMLInputElement).checked, id).toBe(true)
    }
    await master.setValue(false)
    for (const id of LICENSES_RULES.map((item) => item.id)) {
      expect((wrapper.find(rule(id)).element as HTMLInputElement).checked, id).toBe(false)
    }
  })

  it('selects and clears all license rules with the card buttons', async () => {
    const wrapper = await mountFixer()
    await wrapper.find('.group-card[data-group="licenses"] .select-all').trigger('click')
    for (const id of LICENSES_RULES.map((item) => item.id)) {
      expect((wrapper.find(rule(id)).element as HTMLInputElement).checked, id).toBe(true)
    }
    await wrapper.find('.group-card[data-group="licenses"] .clear-all').trigger('click')
    for (const id of LICENSES_RULES.map((item) => item.id)) {
      expect((wrapper.find(rule(id)).element as HTMLInputElement).checked, id).toBe(false)
    }
  })

  it('saves the licenses block loaded from the server', async () => {
    getFixOptionsMock.mockResolvedValue({
      options: {
        ...cloneOptions(),
        licenses: {
          filter_non_proprietary: true,
          add_proprietary: false,
          remove_proprietary_source_references: false,
          add_patterns: [{ field: 'name', pattern: 'vendor' }],
        },
      },
    })
    const wrapper = await mountFixer()
    await wrapper.find('.save-settings').trigger('click')
    await flushPromises()
    const saved = saveFixOptionsMock.mock.calls[0][0] as SbomFixOptions
    expect(saved.licenses.filter_non_proprietary).toBe(true)
    expect(saved.licenses.add_patterns).toEqual([{ field: 'name', pattern: 'vendor' }])
  })
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npm --prefix frontend run test -- src/views/sbomFixerRules.test.ts src/views/SbomFixer.test.ts`
Expected: FAIL — `LICENSES_RULES` is not exported, the licenses card is absent, and the saved `licenses` block differs.

- [ ] **Step 3: Implement types, catalog, locales, card, and wiring**

`frontend/src/types/api.ts`: add `LicensesFixOptions` after `IgnorePatternItem` and a `licenses: LicensesFixOptions` field in `SbomFixOptions`.

`frontend/src/views/sbomFixerRules.ts`:

```ts
import type { ComponentsFixOptions, LicensesFixOptions } from '../types/api'

export type LicensesRuleKey = Exclude<keyof LicensesFixOptions, 'add_patterns'>

export const LICENSES_RULES: readonly FixRule<LicensesRuleKey>[] = [
  { id: 'licenses.filter_non_proprietary', key: 'filter_non_proprietary', example: { before: '...', after: '...' } },
  { id: 'licenses.add_proprietary', key: 'add_proprietary', example: { before: '...', after: '...' } },
  { id: 'licenses.remove_proprietary_source_references', key: 'remove_proprietary_source_references', example: { before: '...', after: '...' } },
]

export const ALL_FIX_RULES: readonly FixRule<string>[] = [
  ...BASE_RULES,
  ...COMPONENTS_RULES,
  ...LICENSES_RULES,
]
```

Replace the example placeholders with valid JSON that differs between `before` and `after` and illustrates the rule (a license array losing its MIT entry; a matched component gaining the `Proprietary` entry; a proprietary component losing its `vcs`/`source-distribution` references).

Locales, namespace `sbomFixer` in both files:

- `groups.licenses`: «Правки, касающиеся лицензий компонентов» / "Component license edits".
- `rules.licenses.filter_non_proprietary`, `rules.licenses.add_proprietary`, `rules.licenses.remove_proprietary_source_references`: the three Russian labels from Global Constraints and their English equivalents.
- `help.licenses.filter_non_proprietary`, `help.licenses.add_proprietary`, `help.licenses.remove_proprietary_source_references`: at least 20 characters each, covering what counts as proprietary, the emptied-array behavior, the `[]` external-references behavior, matching semantics, and that blank pairs are ignored.
- `licenses.contains` («содержит» / "contains"), `licenses.fieldPlaceholder` («Поле» / "Field"), `licenses.valuePlaceholder` («Значение» / "Value"), `licenses.addRow` («Добавить строку» / "Add row"), `licenses.removeRow` («Удалить строку» / "Remove row").

`frontend/src/views/SbomFixer.vue`:

```ts
function defaultFixOptions(): SbomFixOptions {
  return {
    // ...existing fields unchanged
    licenses: {
      filter_non_proprietary: false,
      add_proprietary: false,
      remove_proprietary_source_references: false,
      add_patterns: [],
    },
    // optional_fields unchanged
  }
}

function applyOptions(next: SbomFixOptions): void {
  // ...existing assignments unchanged
  options.licenses = {
    filter_non_proprietary: next.licenses.filter_non_proprietary,
    add_proprietary: next.licenses.add_proprietary,
    remove_proprietary_source_references: next.licenses.remove_proprietary_source_references,
    add_patterns: [...(next.licenses.add_patterns ?? [])],
  }
}
```

The `defaultOptions` fixture added in Step 1 mirrors this block.

Add the card to the template between the `data-group="components"` card and `data-group="optional-fields"` card (the pattern editor is added in Task 6):

```vue
      <div class="group-card" data-group="licenses">
        <div class="group-header">
          <label class="master-label">
            <input
              v-model="licensesMaster"
              type="checkbox"
              class="master-checkbox"
              :indeterminate.prop="licensesIndeterminate"
            />
            <span>{{ t('sbomFixer.groups.licenses') }}</span>
          </label>
          <div class="group-actions">
            <button type="button" class="btn btn-small select-all" @click="licensesMaster = true">{{ t('sbomFixer.selectAll') }}</button>
            <button type="button" class="btn btn-small clear-all" @click="licensesMaster = false">{{ t('sbomFixer.clearAll') }}</button>
          </div>
        </div>
        <div class="group-options">
          <div
            v-for="rule in LICENSES_RULES"
            :key="rule.id"
            class="rule-row"
            :data-rule-row="rule.id"
          >
            <label class="rule-label">
              <input v-model="options.licenses[rule.key]" type="checkbox" :data-rule="rule.id" />
              <span>{{ t(`sbomFixer.rules.${rule.id}`) }}</span>
            </label>
            <RuleHelp
              :rule-id="rule.id"
              :description="t(`sbomFixer.help.${rule.id}`)"
              :before="rule.example.before"
              :after="rule.example.after"
              :before-label="t('sbomFixer.exampleBefore')"
              :after-label="t('sbomFixer.exampleAfter')"
              :rule-title="t(`sbomFixer.rules.${rule.id}`)"
              :open="openHelpId === rule.id"
              @toggle="toggleHelp(rule.id)"
              @close="openHelpId = null"
            />
          </div>
        </div>
      </div>
```

and the matching script additions:

```ts
import { BASE_RULES, COMPONENTS_RULES, LICENSES_RULES } from './sbomFixerRules'

const licenseValues = () => LICENSES_RULES.map((rule) => options.licenses[rule.key])

const licensesMaster = computed({
  get: () => licenseValues().every(Boolean),
  set: (value: boolean) => {
    for (const rule of LICENSES_RULES) options.licenses[rule.key] = value
  },
})

const licensesIndeterminate = computed(
  () => !licensesMaster.value && licenseValues().some(Boolean),
)
```


- [ ] **Step 4: Run the tests to verify they pass**

Run: `npm --prefix frontend run test -- src/views/sbomFixerRules.test.ts src/views/SbomFixer.test.ts`
Expected: PASS.

- [ ] **Step 5: Verify the build**

Run: `npm --prefix frontend run build`
Expected: type-check and build succeed.

---

### Task 6: Pattern editor and payload normalization in `SbomFixer.vue`

**Files:**
- Modify: `frontend/src/views/SbomFixer.vue` (template inside the licenses card, script, scoped styles)
- Test: `frontend/src/views/SbomFixer.test.ts`

**Interfaces:**
- Consumes: the `data-group="licenses"` card, `LICENSES_RULES`, `options.licenses`, `IgnorePatternItem` from Task 5; `t('sbomFixer.licenses.*')` labels.
- Produces: `patternRows: Ref<IgnorePatternItem[]>`, `addPatternRow()`, `removePatternRow(index: number)`, `normalizedPatterns()`, `withNormalizedPatterns()`; a pattern editor with `data-action="add-pattern"`, `data-action="remove-pattern"`, `data-pattern-row`, `data-pattern-field`, `data-pattern-value`; save and fix payloads carrying trimmed, non-empty `add_patterns`.


- [ ] **Step 1: Write the failing tests**

Add to `frontend/src/views/SbomFixer.test.ts`:

```ts
  it('shows one empty pattern row when no patterns are saved', async () => {
    const wrapper = await mountFixer()
    const rows = wrapper.findAll('[data-group="licenses"] [data-pattern-row]')
    expect(rows).toHaveLength(1)
    expect((rows[0].find('[data-pattern-field]').element as HTMLInputElement).value).toBe('')
    expect((rows[0].find('[data-pattern-value]').element as HTMLInputElement).value).toBe('')
  })

  it('fills pattern rows from the loaded options', async () => {
    getFixOptionsMock.mockResolvedValue({
      options: {
        ...cloneOptions(),
        licenses: {
          ...cloneOptions().licenses,
          add_patterns: [{ field: 'name', pattern: 'vendor' }],
        },
      },
    })
    const wrapper = await mountFixer()
    const rows = wrapper.findAll('[data-group="licenses"] [data-pattern-row]')
    expect(rows).toHaveLength(1)
    expect((rows[0].find('[data-pattern-field]').element as HTMLInputElement).value).toBe('name')
    expect((rows[0].find('[data-pattern-value]').element as HTMLInputElement).value).toBe('vendor')
  })

  it('adds and removes pattern rows', async () => {
    const wrapper = await mountFixer()
    await wrapper.find('[data-action="add-pattern"]').trigger('click')
    expect(wrapper.findAll('[data-group="licenses"] [data-pattern-row]')).toHaveLength(2)
    await wrapper.findAll('[data-action="remove-pattern"]')[1].trigger('click')
    expect(wrapper.findAll('[data-group="licenses"] [data-pattern-row]')).toHaveLength(1)
  })

  it('disables the pattern editor while the add rule is off', async () => {
    const wrapper = await mountFixer()
    expect(wrapper.find('[data-pattern-field]').attributes('disabled')).toBeDefined()
    await wrapper.find(rule('licenses.add_proprietary')).setValue(true)
    expect(wrapper.find('[data-pattern-field]').attributes('disabled')).toBeUndefined()
  })

  it('saves normalized non-empty patterns', async () => {
    getFixOptionsMock.mockResolvedValue({
      options: {
        ...cloneOptions(),
        licenses: {
          ...cloneOptions().licenses,
          add_proprietary: true,
          add_patterns: [
            { field: ' name ', pattern: ' vendor ' },
            { field: '', pattern: 'ignored' },
          ],
        },
      },
    })
    const wrapper = await mountFixer()
    await wrapper.find('.save-settings').trigger('click')
    await flushPromises()
    const saved = saveFixOptionsMock.mock.calls[0][0] as SbomFixOptions
    expect(saved.licenses.add_patterns).toEqual([{ field: 'name', pattern: 'vendor' }])
  })

  it('sends normalized patterns with the fix request', async () => {
    const wrapper = await mountFixer()
    await wrapper.find(rule('licenses.add_proprietary')).setValue(true)
    await wrapper.find('[data-pattern-field]').setValue(' name ')
    await wrapper.find('[data-pattern-value]').setValue(' vendor ')
    await selectFile(wrapper)
    await wrapper.find('.fix-button').trigger('click')
    await flushPromises()
    const sentOptions = fixSbomMock.mock.calls[0][1] as SbomFixOptions
    expect(sentOptions.licenses.add_patterns).toEqual([{ field: 'name', pattern: 'vendor' }])
  })

  it('restores defaults for the licenses card', async () => {
    getFixOptionsMock.mockResolvedValue({
      options: {
        ...cloneOptions(),
        licenses: {
          filter_non_proprietary: true,
          add_proprietary: true,
          remove_proprietary_source_references: true,
          add_patterns: [{ field: 'name', pattern: 'vendor' }],
        },
      },
    })
    const wrapper = await mountFixer()
    await wrapper.find('.reset-defaults').trigger('click')
    for (const id of LICENSES_RULES.map((rule) => rule.id)) {
      expect((wrapper.find(rule(id)).element as HTMLInputElement).checked, id).toBe(false)
    }
    const rows = wrapper.findAll('[data-group="licenses"] [data-pattern-row]')
    expect(rows).toHaveLength(1)
    expect((rows[0].find('[data-pattern-field]').element as HTMLInputElement).value).toBe('')
  })
```

`LICENSES_RULES` is already imported from `./sbomFixerRules` by the Task 5 tests.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npm --prefix frontend run test -- src/views/SbomFixer.test.ts`
Expected: FAIL — no `[data-pattern-row]` elements.

- [ ] **Step 3: Implement the pattern editor and normalization**

Insert the editor inside the licenses card's `.group-options`, right after the rule `v-for`:

```vue
          <div class="pattern-rows">
            <div v-for="(row, idx) in patternRows" :key="idx" class="pattern-row" data-pattern-row>
              <input v-model="row.field" type="text" class="pattern-input" data-pattern-field :placeholder="t('sbomFixer.licenses.fieldPlaceholder')" :disabled="!options.licenses.add_proprietary" :aria-label="t('sbomFixer.licenses.fieldPlaceholder')" />
              <span class="pattern-label">{{ t('sbomFixer.licenses.contains') }}</span>
              <input v-model="row.pattern" type="text" class="pattern-input" data-pattern-value :placeholder="t('sbomFixer.licenses.valuePlaceholder')" :disabled="!options.licenses.add_proprietary" :aria-label="t('sbomFixer.licenses.valuePlaceholder')" />
              <button type="button" class="btn-delete" data-action="remove-pattern" :disabled="!options.licenses.add_proprietary" :aria-label="t('sbomFixer.licenses.removeRow')" @click="removePatternRow(idx)">✕</button>
            </div>
            <button type="button" class="btn btn-small" data-action="add-pattern" :disabled="!options.licenses.add_proprietary" @click="addPatternRow">{{ t('sbomFixer.licenses.addRow') }}</button>
          </div>
```

Script additions (`IgnorePatternItem` goes into the existing `import type { ... } from '../types/api'`):

```ts
const patternRows = ref<IgnorePatternItem[]>([{ field: '', pattern: '' }])

function addPatternRow(): void {
  patternRows.value.push({ field: '', pattern: '' })
}

function removePatternRow(index: number): void {
  patternRows.value.splice(index, 1)
}

function normalizedPatterns(): IgnorePatternItem[] {
  return patternRows.value
    .map((row) => ({ field: row.field.trim(), pattern: row.pattern.trim() }))
    .filter((row) => row.field !== '' && row.pattern !== '')
}

function withNormalizedPatterns(): SbomFixOptions {
  const next = plainOptions()
  next.licenses.add_patterns = normalizedPatterns()
  return next
}
```

Wire the rows:

- `applyOptions()` sets `patternRows.value = next.licenses.add_patterns.length > 0 ? [...next.licenses.add_patterns] : [{ field: '', pattern: '' }]` after copying `options.licenses`.
- `handleSave()` calls `saveFixOptions(withNormalizedPatterns())` instead of `plainOptions()`.
- `handleFix()` passes `withNormalizedPatterns()` instead of `plainOptions()`.
- `restoreDefaults()` resets `patternRows.value = [{ field: '', pattern: '' }]` after `applyOptions(defaultFixOptions())`.
- `onFileSelected()` does not touch the rows.

Styles: reuse the existing pattern-row layout from `SbomUpdater.vue` (`.pattern-rows`, `.pattern-row`, `.pattern-input`, `.pattern-label`, `.btn-delete`), scoped to this view; align the editor under the rule row with a small left indent so it reads as part of the `add_proprietary` item.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npm --prefix frontend run test -- src/views/SbomFixer.test.ts`
Expected: PASS.

- [ ] **Step 5: Run all frontend tests and the build**

Run: `npm --prefix frontend run test`
Expected: PASS.

Run: `npm --prefix frontend run build`
Expected: type-check and build succeed.

---

### Task 7: Update project specifications

**Files:**
- Modify: `specs/domains/sbom-fixing.md`
- Modify: `specs/contracts/api-contract.md`
- Modify: `specs/domains/web-ui.md`

**Interfaces:**
- Consumes: the finished implementation and the design doc.
- Produces: specs describing 11 static rules, the `licenses` options block, execution order, statistics units, and the fourth UI card.

- [ ] **Step 1: Load the spec update skill**

Use the `vibespec-update` skill for the edits.

- [ ] **Step 2: Update `specs/domains/sbom-fixing.md`**

- Change "8 named static rules" to "11 named static rules" (and the Key Files description of `sbomFixerRules.ts` rule counts only where it refers to this domain).
- Add `LicensePatternItem` and `LicensesFixOptions` to Core Types and the `licenses` field to `SbomFixOptions`.
- Extend `RULE_IDS` to the 11 ids in execution order.
- Document the three rules, their detection predicate (`entry.license.name == "Proprietary"`), the emptied-`licenses` deletion, `licenses: null` handling, pattern matching semantics, `externalReferences` staying `[]`, the single-walk order, and the three statistics units.

- [ ] **Step 3: Update `specs/contracts/api-contract.md`**

- Extend the `options` JSON in `POST /api/v1/sbom/fix`, `GET /api/v1/sbom/fix/options`, and `POST /api/v1/sbom/fix/options` with the `licenses` block example from the design doc.
- Note that `add_patterns` entries with blank `field`/`pattern` are ignored and that an invalid `add_patterns` type yields `400 invalid_options` through the existing validation path.
- Update the `/fix-sbom` page description from three sections to four.

- [ ] **Step 4: Update `specs/domains/web-ui.md`**

- Update the `SbomFixer.vue` Key File line and the `/fix-sbom` flow description: four option cards, the license card between `components[]` and the optional-fields card, the inline pattern editor, and the shared save button.

- [ ] **Step 5: Review the specs for consistency**

Use the `vibespec-check` skill or re-read the three files and confirm: rule counts match the code, option JSON matches the model, no stale "8 rules"/"three sections" mentions remain, and `INDEX.md` needs no change.

- [ ] **Step 6: Run the full verification**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS (or `SKIP_E2E=1` if only network e2e tests fail; report which).

Run: `npm --prefix frontend run test`
Expected: PASS.

Run: `npm --prefix frontend run build`
Expected: PASS.

---

## Self-Review Notes

- Spec coverage: options model and persistence (Task 1), the three rules and their single-walk order (Tasks 2–4), API tolerance and payload (Tasks 1, 4), rule catalog, locales and the license card (Task 5), pattern editor and payload normalization (Task 6), project specs (Task 7).
- Type consistency: `LicensesFixOptions` / `LicensePatternItem` names are used identically in backend, types, and rules catalog; `add_patterns` keeps `IgnorePatternItem`'s `field`/`pattern` keys end to end; rule ids are identical in `RULE_IDS`, `LICENSES_RULES`, i18n keys, and test selectors.
- Review Focus coverage: `licenses: null` / non-list values — Tasks 2 and 3; missing or `null` matched field and blank pairs — Task 3; emptied `externalReferences` and untouched `metadata.component` — Task 4; old options file and invalid `add_patterns` — Task 1; nested `components[]` traversal — Task 2.
