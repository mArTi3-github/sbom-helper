# Add `GOST:provided_by` Rule Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the `components.add_provided_by` rule to the Fix SBOM section: an enabled-by-default, configurable three-column matcher that adds `{"name": "GOST:provided_by", "value": "<certified product>"}` to matching components.

**Architecture:** Mirror the existing `licenses.add_proprietary` option pattern. `ComponentsFixOptions` gains a boolean and a list of `{field, pattern, provided_by}` rows with an Astra default row. A new helper walks the root `components[]` tree after the existing property rules, picks the first matching row top-down, skips components with a filled `GOST:provided_by`, and fills or appends the property. The Vue page gets a local three-input row editor next to the new rule row.

**Tech Stack:** Python 3, Pydantic, pytest, FastAPI; Vue 3, TypeScript, Vitest (`npm --prefix frontend`).

**Spec:** `docs/superpowers/specs/2026-11-02-sbom-fixer-provided-by-design.md`

## Global Constraints

- Rule id and option key: `components.add_provided_by` / `add_provided_by`.
- The rule is enabled by default (`True`).
- Default row, copied verbatim: `field="purl"`, `pattern="pkg:deb/astra"`, `provided_by='Операционная система специального назначения "Astra Linux Special Edition"'`.
- Row fields are trimmed; a row is active only when all three values are non-empty after trimming.
- Matching is a case-sensitive substring of `str(component[field])`; a missing field or `null` never matches.
- The first active matching row top-down wins; exactly one property is added per component.
- A component is processed only when it has no `GOST:provided_by` or every such entry has an "empty" value (absent, `null`, empty/whitespace-only string, or a non-string). A non-empty string value excludes the component.
- An existing `GOST:provided_by` entry with an empty value is updated in place; no duplicate entry is created.
- Scope is the root `components[]` tree at all nesting levels; `metadata.component` and its subtree are never touched.
- `properties` absent/`null` becomes `[]` only when a property is actually added; a non-array `properties` skips the component without overwriting.
- The rule runs after `components.fill_missing_gost_properties` and before `licenses.*` and issue collection.
- `stats` count is the number of components changed; the rule is always present in stats when enabled, even with `count = 0`.
- Blank rows are ignored; invalid option types yield `400 invalid_options` through the existing Pydantic path.
- Backend commands use `.venv`: `.venv/bin/python -m pytest ...`. Frontend: `npm --prefix frontend run test` and `npm --prefix frontend run build`.

## Review Focus

- A component whose `properties` is a string/object: the rule must leave it untouched and not crash (test in Task 2 and Task 3).
- A component with an already filled `GOST:provided_by`: the existing value must survive verbatim (Task 2).
- Multiple matching rows: the first row in configuration order must decide the value (Task 2 and Task 3).
- A component with an empty/`null`/non-string `GOST:provided_by` value: it must be filled in place with no duplicate (Task 2).
- `metadata.component` and its nested components: they must never receive the property (Task 3).

---

### Task 1: Backend options model and default row

**Files:**
- Modify: `src/purl_resolver/sbom/fixer.py` (component option models around lines 52, 79–98)
- Modify: `src/purl_resolver/sbom/__init__.py`
- Test: `tests/test_sbom_fixer.py`
- Test: `tests/test_sbom_fix_api.py`
- Test: `tests/test_sbom_fix_options_store.py`

**Interfaces:**
- Produces: `ProvidedByPatternItem(field: str = "", pattern: str = "", provided_by: str = "")`
- Produces: `ComponentsFixOptions.add_provided_by: bool = True`
- Produces: `ComponentsFixOptions.provided_by_patterns: list[ProvidedByPatternItem]` with one Astra default row
- Produces: `purl_resolver.sbom.ProvidedByPatternItem` export

- [ ] **Step 1: Write failing model/default tests in `tests/test_sbom_fixer.py`**

Add `ComponentsFixOptions` and `ProvidedByPatternItem` to the existing import from `purl_resolver.sbom.fixer`, then add:

```python
def test_components_provided_by_defaults():
    options = SbomFixOptions()
    assert options.components.add_provided_by is True
    assert options.components.provided_by_patterns == [
        ProvidedByPatternItem(
            field="purl",
            pattern="pkg:deb/astra",
            provided_by=(
                'Операционная система специального назначения "Astra Linux Special Edition"'
            ),
        )
    ]


def test_provided_by_pattern_item_defaults_are_empty_strings():
    item = ProvidedByPatternItem()
    assert item.field == ""
    assert item.pattern == ""
    assert item.provided_by == ""
```

- [ ] **Step 2: Write failing API tests in `tests/test_sbom_fix_api.py`**

Add after `test_fix_options_endpoint_returns_leaf_flags_disabled`:

```python
def test_fix_options_endpoint_returns_provided_by_defaults(client):
    response = client.get("/api/v1/sbom/fix/options")
    assert response.status_code == 200
    components = response.json()["options"]["components"]
    assert components["add_provided_by"] is True
    assert components["provided_by_patterns"] == [
        {
            "field": "purl",
            "pattern": "pkg:deb/astra",
            "provided_by": (
                'Операционная система специального назначения "Astra Linux Special Edition"'
            ),
        }
    ]


def test_save_options_roundtrips_provided_by_patterns(client):
    payload = {
        "options": {
            "components": {
                "add_provided_by": False,
                "provided_by_patterns": [
                    {
                        "field": "name",
                        "pattern": "vendor",
                        "provided_by": "Vendor SZI",
                    }
                ],
            }
        }
    }
    response = client.post("/api/v1/sbom/fix/options", json=payload)
    assert response.status_code == 200
    components = client.get("/api/v1/sbom/fix/options").json()["options"]["components"]
    assert components["add_provided_by"] is False
    assert components["provided_by_patterns"] == [
        {"field": "name", "pattern": "vendor", "provided_by": "Vendor SZI"}
    ]


def test_save_options_rejects_non_list_provided_by_patterns(client):
    response = client.post(
        "/api/v1/sbom/fix/options",
        json={"options": {"components": {"provided_by_patterns": "purl"}}},
    )
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_options"
```

- [ ] **Step 3: Write failing persistence tests in `tests/test_sbom_fix_options_store.py`**

Add `ProvidedByPatternItem` to the existing fixer import and add:

```python
def test_save_load_roundtrip_including_provided_by(tmp_path):
    store = SbomFixOptionsStore(tmp_path / "options.json")
    options = SbomFixOptions(
        components=ComponentsFixOptions(
            add_provided_by=False,
            provided_by_patterns=[
                ProvidedByPatternItem(
                    field="name", pattern="vendor", provided_by="Vendor SZI"
                )
            ],
        )
    )
    store.save(options)
    assert store.load() == options


def test_old_file_without_provided_by_uses_defaults(tmp_path):
    path = tmp_path / "old.json"
    path.write_text(
        '{"components": {"filter_properties": false}}', encoding="utf-8"
    )
    loaded = SbomFixOptionsStore(path).load()
    assert loaded.components.filter_properties is False
    assert loaded.components.add_provided_by is True
    assert loaded.components.provided_by_patterns == [
        ProvidedByPatternItem(
            field="purl",
            pattern="pkg:deb/astra",
            provided_by=(
                'Операционная система специального назначения "Astra Linux Special Edition"'
            ),
        )
    ]
```

- [ ] **Step 4: Run the new tests to verify they fail**

Run: `.venv/bin/python -m pytest -q tests/test_sbom_fixer.py::test_components_provided_by_defaults tests/test_sbom_fix_api.py::test_fix_options_endpoint_returns_provided_by_defaults tests/test_sbom_fix_options_store.py::test_old_file_without_provided_by_uses_defaults`

Expected: FAIL with an import/attribute error for `ProvidedByPatternItem` or `add_provided_by`.

- [ ] **Step 5: Implement the model and export**

In `src/purl_resolver/sbom/fixer.py`:

- Add near `PROPRIETARY_LICENSE_NAME`:

```python
PROVIDED_BY_PROPERTY_NAME = "GOST:provided_by"
DEFAULT_PROVIDED_BY_VALUE = (
    'Операционная система специального назначения "Astra Linux Special Edition"'
)
```

- Add before `ComponentsFixOptions`:

```python
class ProvidedByPatternItem(BaseModel):
    field: str = ""
    pattern: str = ""
    provided_by: str = ""


def _default_provided_by_patterns() -> list[ProvidedByPatternItem]:
    return [
        ProvidedByPatternItem(
            field="purl",
            pattern="pkg:deb/astra",
            provided_by=DEFAULT_PROVIDED_BY_VALUE,
        )
    ]
```

- Add the two fields to `ComponentsFixOptions`:

```python
    add_provided_by: bool = True
    provided_by_patterns: list[ProvidedByPatternItem] = Field(
        default_factory=_default_provided_by_patterns
    )
```

- In `src/purl_resolver/sbom/__init__.py`, import and export `ProvidedByPatternItem` next to `LicensePatternItem`.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest -q tests/test_sbom_fixer.py::test_components_provided_by_defaults tests/test_sbom_fixer.py::test_provided_by_pattern_item_defaults_are_empty_strings tests/test_sbom_fix_api.py::test_fix_options_endpoint_returns_provided_by_defaults tests/test_sbom_fix_api.py::test_save_options_roundtrips_provided_by_patterns tests/test_sbom_fix_api.py::test_save_options_rejects_non_list_provided_by_patterns tests/test_sbom_fix_options_store.py::test_save_load_roundtrip_including_provided_by tests/test_sbom_fix_options_store.py::test_old_file_without_provided_by_uses_defaults`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/purl_resolver/sbom/fixer.py src/purl_resolver/sbom/__init__.py tests/test_sbom_fixer.py tests/test_sbom_fix_api.py tests/test_sbom_fix_options_store.py
git commit -m "feat: add provided_by fix options model"
```

---

### Task 2: Backend matching and property helpers

**Files:**
- Modify: `src/purl_resolver/sbom/fixer.py` (around `_matches_license_patterns`, lines 672–690)
- Test: `tests/test_sbom_fixer.py`

**Interfaces:**
- Consumes: `PROVIDED_BY_PROPERTY_NAME`, `ProvidedByPatternItem` from Task 1
- Produces: `_field_contains_pattern(component: dict, field: str, pattern: str) -> bool`
- Produces: `_first_matching_provided_by(component: dict, patterns: list[tuple[str, str, str]]) -> str | None`
- Produces: `_has_filled_provided_by(properties: list) -> bool`
- Produces: `_add_provided_by(component: dict, patterns: list[tuple[str, str, str]]) -> int`

- [ ] **Step 1: Write failing helper tests in `tests/test_sbom_fixer.py`**

Add `_add_provided_by` and `_field_contains_pattern` to the existing private-helper import, then add:

```python
def test_field_contains_pattern_is_case_sensitive_and_skips_null():
    assert _field_contains_pattern(
        {"purl": "pkg:deb/astra/x"}, "purl", "pkg:deb/astra"
    )
    assert not _field_contains_pattern(
        {"purl": "pkg:deb/Astra/x"}, "purl", "pkg:deb/astra"
    )
    assert not _field_contains_pattern({"purl": None}, "purl", "pkg:deb/astra")
    assert not _field_contains_pattern({}, "purl", "pkg:deb/astra")


def test_add_provided_by_appends_property_for_matching_purl():
    component = {"purl": "pkg:deb/astra/astra-utils@1.0"}
    patterns = [("purl", "pkg:deb/astra", "Astra Linux SE")]
    assert _add_provided_by(component, patterns) == 1
    assert component["properties"] == [
        {"name": "GOST:provided_by", "value": "Astra Linux SE"}
    ]


def test_add_provided_by_uses_first_matching_pattern():
    component = {
        "purl": "pkg:deb/astra/astra-utils@1.0",
        "name": "astra-utils",
    }
    patterns = [
        ("purl", "pkg:deb/astra", "Astra Linux SE"),
        ("name", "astra", "Other SZI"),
    ]
    assert _add_provided_by(component, patterns) == 1
    assert component["properties"][0]["value"] == "Astra Linux SE"


def test_add_provided_by_keeps_existing_filled_value():
    component = {
        "purl": "pkg:deb/astra/x",
        "properties": [{"name": "GOST:provided_by", "value": "Manual"}],
    }
    assert _add_provided_by(
        component, [("purl", "pkg:deb/astra", "Astra")]
    ) == 0
    assert component["properties"] == [
        {"name": "GOST:provided_by", "value": "Manual"}
    ]


@pytest.mark.parametrize("value", ["", "   ", None, 5, ["x"]])
def test_add_provided_by_fills_empty_existing_value_in_place(value):
    component = {
        "purl": "pkg:deb/astra/x",
        "properties": [
            {"name": "other", "value": 1},
            {"name": "GOST:provided_by", "value": value},
        ],
    }
    assert _add_provided_by(
        component, [("purl", "pkg:deb/astra", "Astra")]
    ) == 1
    assert component["properties"] == [
        {"name": "other", "value": 1},
        {"name": "GOST:provided_by", "value": "Astra"},
    ]


def test_add_provided_by_does_not_create_properties_without_match():
    component = {"purl": "pkg:npm/x@1"}
    assert _add_provided_by(
        component, [("purl", "pkg:deb/astra", "Astra")]
    ) == 0
    assert "properties" not in component


def test_add_provided_by_skips_non_list_properties():
    component = {"purl": "pkg:deb/astra/x", "properties": "bad"}
    assert _add_provided_by(
        component, [("purl", "pkg:deb/astra", "Astra")]
    ) == 0
    assert component["properties"] == "bad"
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `.venv/bin/python -m pytest -q tests/test_sbom_fixer.py::test_field_contains_pattern_is_case_sensitive_and_skips_null tests/test_sbom_fixer.py::test_add_provided_by_appends_property_for_matching_purl`

Expected: FAIL with an import error for `_add_provided_by` / `_field_contains_pattern`.

- [ ] **Step 3: Implement the helpers**

In `src/purl_resolver/sbom/fixer.py`:

- Add `_field_contains_pattern` before `_matches_license_patterns` and rewrite `_matches_license_patterns` to use it, preserving current behavior exactly:

```python
def _field_contains_pattern(component: dict, field: str, pattern: str) -> bool:
    value = component.get(field)
    return value is not None and pattern in str(value)


def _matches_license_patterns(
    component: dict, patterns: list[tuple[str, str]]
) -> bool:
    return any(
        _field_contains_pattern(component, name, pattern)
        for name, pattern in patterns
    )
```

- Add the new helpers next to it:

```python
def _first_matching_provided_by(
    component: dict, patterns: list[tuple[str, str, str]]
) -> str | None:
    for field, pattern, provided_by in patterns:
        if _field_contains_pattern(component, field, pattern):
            return provided_by
    return None


def _has_filled_provided_by(properties: list) -> bool:
    for prop in properties:
        if isinstance(prop, dict) and prop.get("name") == PROVIDED_BY_PROPERTY_NAME:
            value = prop.get("value")
            if isinstance(value, str) and value.strip():
                return True
    return False


def _add_provided_by(
    component: dict, patterns: list[tuple[str, str, str]]
) -> int:
    if not patterns:
        return 0
    properties = component.get("properties")
    if isinstance(properties, list) and _has_filled_provided_by(properties):
        return 0
    value = _first_matching_provided_by(component, patterns)
    if value is None:
        return 0
    if properties is None:
        properties = []
        component["properties"] = properties
    elif not isinstance(properties, list):
        return 0
    for prop in properties:
        if isinstance(prop, dict) and prop.get("name") == PROVIDED_BY_PROPERTY_NAME:
            prop["value"] = value
            return 1
    properties.append({"name": PROVIDED_BY_PROPERTY_NAME, "value": value})
    return 1
```

The order matters: match before creating `properties`, so a non-matching component never gains an empty array.

- [ ] **Step 4: Run the helper tests and the existing license tests**

Run: `.venv/bin/python -m pytest -q tests/test_sbom_fixer.py -k "provided_by or license_pattern or proprietary"`

Expected: PASS, including the unchanged proprietary matching tests.

- [ ] **Step 5: Commit**

```bash
git add src/purl_resolver/sbom/fixer.py tests/test_sbom_fixer.py
git commit -m "feat: add provided_by matching helpers"
```

---

### Task 3: Wire the rule into components fixes and stats

**Files:**
- Modify: `src/purl_resolver/sbom/fixer.py` (`RULE_IDS` around line 65; `_apply_components_rules` around lines 721–757)
- Test: `tests/test_sbom_fixer.py`
- Test: `tests/test_sbom_fix_api.py`

**Interfaces:**
- Consumes: `_add_provided_by`, `ProvidedByPatternItem`, `ComponentsFixOptions` from Tasks 1–2
- Produces: `RULE_IDS` entry `"components.add_provided_by"` after `"components.fill_missing_gost_properties"`
- Produces: stats row `components.add_provided_by` with the number of changed components

- [ ] **Step 1: Update the existing rule-order/count tests to the new expectation**

In `tests/test_sbom_fixer.py`:

- Insert `"components.add_provided_by"` into `NEW_RULE_IDS` after `"components.fill_missing_gost_properties"`.
- Rename `test_all_enabled_rules_yield_fourteen_stats_in_canonical_order` to `...fifteen...`; add `"add_provided_by": True` to the `components` dict (it is already the default, the explicit value documents intent).
- In `test_fix_sbom_copies_input_and_emits_zero_stats_for_enabled_rules`, change `len(result.stats) == 7` to `== 8`.
- In `test_license_rule_ids_come_last_in_execution_order`, change `len(RULE_IDS) == 14` to `== 15`.

- [ ] **Step 2: Write the failing integration tests in `tests/test_sbom_fixer.py`**

Add a helper and tests:

```python
def _component_rules_options(**components):
    return SbomFixOptions(
        reorder=False,
        set_spec_version=False,
        increment_version=False,
        add_timestamp=False,
        add_manufacturer=False,
        components=ComponentsFixOptions(**components),
    )


def _astra_component(**overrides):
    component = {
        "type": "library",
        "name": "astra-utils",
        "version": "1.0",
        "purl": "pkg:deb/astra/astra-utils@1.0",
    }
    component.update(overrides)
    return component


def test_add_provided_by_rule_adds_property_and_counts():
    data = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.7",
        "version": 1,
        "components": [_astra_component()],
    }
    result = fix_sbom(data, _component_rules_options())
    component = result.fixed_sbom["components"][0]
    assert component["properties"] == [
        {
            "name": "GOST:provided_by",
            "value": (
                'Операционная система специального назначения '
                '"Astra Linux Special Edition"'
            ),
        }
    ]
    stats = {stat.rule_id: stat.count for stat in result.stats}
    assert stats["components.add_provided_by"] == 1


def test_add_provided_by_walks_nested_components_but_not_metadata():
    data = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.7",
        "version": 1,
        "metadata": {"component": _astra_component(name="meta")},
        "components": [
            {
                "type": "application",
                "name": "app",
                "version": "1.0",
                "purl": "pkg:npm/app@1.0",
                "components": [_astra_component(name="nested")],
            }
        ],
    }
    result = fix_sbom(data, _component_rules_options())
    root = result.fixed_sbom["components"][0]
    assert root["components"][0]["properties"][0]["name"] == "GOST:provided_by"
    assert "properties" not in result.fixed_sbom["metadata"]["component"]


def test_add_provided_by_ignores_blank_rows_and_uses_next_match():
    options = _component_rules_options(
        provided_by_patterns=[
            ProvidedByPatternItem(field="purl", pattern="pkg:deb/astra", provided_by=""),
            ProvidedByPatternItem(field="", pattern="astra", provided_by="A"),
            ProvidedByPatternItem(field="name", pattern="astra", provided_by="B"),
        ]
    )
    data = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.7",
        "version": 1,
        "components": [_astra_component()],
    }
    result = fix_sbom(data, options)
    assert result.fixed_sbom["components"][0]["properties"] == [
        {"name": "GOST:provided_by", "value": "B"}
    ]


def test_add_provided_by_first_row_wins_across_fields():
    options = _component_rules_options(
        provided_by_patterns=[
            ProvidedByPatternItem(
                field="purl", pattern="pkg:deb/astra", provided_by="From purl"
            ),
            ProvidedByPatternItem(
                field="name", pattern="astra", provided_by="From name"
            ),
        ]
    )
    data = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.7",
        "version": 1,
        "components": [_astra_component()],
    }
    result = fix_sbom(data, options)
    assert result.fixed_sbom["components"][0]["properties"] == [
        {"name": "GOST:provided_by", "value": "From purl"}
    ]


def test_add_provided_by_without_active_rows_is_a_noop():
    options = _component_rules_options(
        provided_by_patterns=[
            ProvidedByPatternItem(field="purl", pattern="", provided_by="A"),
            ProvidedByPatternItem(field="purl", pattern="pkg:deb/astra", provided_by=""),
        ]
    )
    data = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.7",
        "version": 1,
        "components": [_astra_component()],
    }
    result = fix_sbom(data, options)
    assert "properties" not in result.fixed_sbom["components"][0]
    stats = {stat.rule_id: stat.count for stat in result.stats}
    assert stats["components.add_provided_by"] == 0


def test_add_provided_by_suppresses_missing_source_reference_in_same_run():
    data = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.7",
        "version": 1,
        "components": [_astra_component()],
    }
    result = fix_sbom(data, _component_rules_options())
    codes = [issue.code for issue in result.issues]
    assert "component.missing_source_reference" not in codes


def test_add_provided_by_runs_after_fill_and_keeps_all_gost_properties():
    data = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.7",
        "version": 1,
        "components": [_astra_component()],
    }
    options = _component_rules_options(fill_missing_gost_properties=True)
    result = fix_sbom(data, options)
    names = [
        prop["name"]
        for prop in result.fixed_sbom["components"][0]["properties"]
    ]
    assert names == [
        "GOST:attack_surface",
        "GOST:security_function",
        "GOST:provided_by",
    ]
```

- [ ] **Step 3: Write the failing fix-endpoint test in `tests/test_sbom_fix_api.py`**

Append after `test_fix_endpoint_applies_license_options`:

```python
def test_fix_endpoint_applies_provided_by_options(client):
    sbom = make_sbom()
    sbom["components"][0]["purl"] = "pkg:deb/astra/astra-utils@1.0"
    options = {
        "components": {
            "provided_by_patterns": [
                {
                    "field": "purl",
                    "pattern": "pkg:deb/astra",
                    "provided_by": "Astra Linux SE",
                }
            ]
        }
    }
    response = upload_fix(client, sbom, options=options)
    assert response.status_code == 200
    body = response.json()
    assert body["fixed_sbom"]["components"][0]["properties"] == [
        {"name": "GOST:provided_by", "value": "Astra Linux SE"}
    ]
    stat = next(
        stat
        for stat in body["stats"]
        if stat["rule_id"] == "components.add_provided_by"
    )
    assert stat["count"] == 1
```

- [ ] **Step 4: Run the integration tests to verify they fail**

Run: `.venv/bin/python -m pytest -q tests/test_sbom_fixer.py -k "add_provided_by" tests/test_sbom_fix_api.py::test_fix_endpoint_applies_provided_by_options`

Expected: FAIL because `add_provided_by` is not in `RULE_IDS` and is not applied by `_apply_components_rules`.

- [ ] **Step 5: Implement the wiring**

In `src/purl_resolver/sbom/fixer.py`:

- Add `"components.add_provided_by",` to `RULE_IDS` immediately after `"components.fill_missing_gost_properties"`.
- In `_apply_components_rules`, add after the `fill_gost` flag:

```python
    add_provided_by = _rule_enabled("components.add_provided_by", options)
    provided_by_patterns = (
        [
            (item.field.strip(), item.pattern.strip(), item.provided_by.strip())
            for item in options.components.provided_by_patterns
            if item.field.strip()
            and item.pattern.strip()
            and item.provided_by.strip()
        ]
        if add_provided_by
        else []
    )
```

- Inside the `apply` callback, after the `fill_gost` block:

```python
        if add_provided_by:
            counts["components.add_provided_by"] = (
                counts.get("components.add_provided_by", 0)
                + _add_provided_by(component, provided_by_patterns)
            )
```

- [ ] **Step 6: Run the targeted backend tests to verify they pass**

Run: `.venv/bin/python -m pytest -q tests/test_sbom_fixer.py tests/test_sbom_fix_api.py tests/test_sbom_fix_options_store.py`

Expected: PASS. If existing count assertions fail, update only the expected numbers, not production behavior.

- [ ] **Step 7: Commit**

```bash
git add src/purl_resolver/sbom/fixer.py tests/test_sbom_fixer.py tests/test_sbom_fix_api.py
git commit -m "feat: apply provided_by rule in sbom fixes"
```

---

### Task 4: Frontend types, rule catalog, and translations

**Files:**
- Modify: `frontend/src/types/api.ts` (around lines 134–145, 202–209)
- Modify: `frontend/src/views/sbomFixerRules.ts`
- Modify: `frontend/src/i18n/locales/ru.json`
- Modify: `frontend/src/i18n/locales/en.json`
- Test: `frontend/src/views/sbomFixerRules.test.ts`

**Interfaces:**
- Produces: `ProvidedByPatternItem { field: string; pattern: string; provided_by: string }`
- Produces: `ComponentsFixOptions.add_provided_by: boolean`, `.provided_by_patterns: ProvidedByPatternItem[]`
- Produces: `ComponentsRuleKey = Exclude<keyof ComponentsFixOptions, 'provided_by_patterns'>`
- Produces: catalog rule `components.add_provided_by` with key `add_provided_by`
- Produces: i18n paths `sbomFixer.rules.components.add_provided_by`, `sbomFixer.help.components.add_provided_by`, and `sbomFixer.providedBy.*`

- [ ] **Step 1: Update the failing catalog tests**

In `frontend/src/views/sbomFixerRules.test.ts`:

- Change `size: 6` to `size: 7` for `COMPONENTS_RULES`.
- Change `it('covers all 14 rules with unique ids')` and both `14` values to `15`.
- Add `'components.add_provided_by'` at the end of the expected `COMPONENTS_RULES` id array.

- [ ] **Step 2: Run the catalog tests to verify they fail**

Run: `npm --prefix frontend run test -- src/views/sbomFixerRules.test.ts`

Expected: FAIL on the rule count and the missing expected id.

- [ ] **Step 3: Implement types, catalog entry, and translations**

In `frontend/src/types/api.ts`:

```ts
export interface ProvidedByPatternItem {
  field: string
  pattern: string
  provided_by: string
}
```

Add to `ComponentsFixOptions`:

```ts
  add_provided_by: boolean
  provided_by_patterns: ProvidedByPatternItem[]
```

In `frontend/src/views/sbomFixerRules.ts`:

- Change the key type to `export type ComponentsRuleKey = Exclude<keyof ComponentsFixOptions, 'provided_by_patterns'>`.
- Append this rule after `components.fill_missing_gost_properties`:

```ts
  {
    id: 'components.add_provided_by',
    key: 'add_provided_by',
    example: {
      before: `{
  "components": [
    {
      "type": "library",
      "name": "astra-utils",
      "version": "1.0.0",
      "purl": "pkg:deb/astra/astra-utils@1.0.0"
    }
  ]
}`,
      after: `{
  "components": [
    {
      "type": "library",
      "name": "astra-utils",
      "version": "1.0.0",
      "purl": "pkg:deb/astra/astra-utils@1.0.0",
      "properties": [
        {
          "name": "GOST:provided_by",
          "value": "Операционная система специального назначения \\"Astra Linux Special Edition\\""
        }
      ]
    }
  ]
}`,
    },
  },
```

In `frontend/src/i18n/locales/ru.json`, inside `sbomFixer`:

```json
"providedBy": {
  "contains": "содержит",
  "fieldPlaceholder": "Поле",
  "valuePlaceholder": "Значение",
  "namePlaceholder": "Название сертифицированного СЗИ",
  "addRow": "Добавить строку",
  "removeRow": "Удалить строку"
}
```

Add the rule label under `rules.components`:

```json
"add_provided_by": "Добавить свойство GOST:provided_by для компонентов со следующими признаками:"
```

Add the help text under `help.components`:

```json
"add_provided_by": "Для компонентов, у которых поле содержит заданное значение (подстрока с учётом регистра), добавляет в properties[] свойство GOST:provided_by со значением из столбца «Название сертифицированного СЗИ». Строки с пустым любым из трёх полей игнорируются; при нескольких совпадениях используется первая сверху строка. Компоненты с уже заполненным GOST:provided_by не меняются; пустое значение заполняется в существующем элементе без создания дубля. Свойства отсутствующего массива properties создаются; нестроковый properties не изменяется. metadata.component не затрагивается."
```

Mirror the same three additions in `en.json`:

```json
"add_provided_by": "Add the GOST:provided_by property to components with the following characteristics:"
```

```json
"add_provided_by": "For components whose field contains the configured value (case-sensitive substring), adds a GOST:provided_by entry to properties[] with the value from the \"Certified security product name\" column. Rows with any blank field are ignored; when several rows match, the first one wins. Components with an already filled GOST:provided_by are unchanged; an empty value is filled in the existing entry without creating a duplicate. A missing properties array is created; a non-array properties value is left untouched. metadata.component is not affected."
```

```json
"providedBy": {
  "contains": "contains",
  "fieldPlaceholder": "Field",
  "valuePlaceholder": "Value",
  "namePlaceholder": "Certified security product name",
  "addRow": "Add row",
  "removeRow": "Remove row"
}
```

- [ ] **Step 4: Run the catalog tests to verify they pass**

Run: `npm --prefix frontend run test -- src/views/sbomFixerRules.test.ts`

Expected: PASS, including the per-locale label/help checks.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/api.ts frontend/src/views/sbomFixerRules.ts frontend/src/i18n/locales/ru.json frontend/src/i18n/locales/en.json frontend/src/views/sbomFixerRules.test.ts
git commit -m "feat: add provided_by rule to sbom fixer catalog"
```

---

### Task 5: Frontend editor, defaults, save, and fix wiring

**Files:**
- Modify: `frontend/src/views/SbomFixer.vue` (components card template around lines 105–140; script around lines 400–500; state/reset around lines 640–660; styles if needed)
- Test: `frontend/src/views/SbomFixer.test.ts`

**Interfaces:**
- Consumes: `ProvidedByPatternItem`, `add_provided_by`, `provided_by_patterns` from Task 4
- Produces: local state `providedByRows`, functions `defaultProvidedByRow()`, `emptyProvidedByRow()`, `addProvidedByRow()`, `removeProvidedByRow(index)`, `normalizedProvidedByPatterns()`

- [ ] **Step 1: Update the test fixture and failing editor tests**

In `frontend/src/views/SbomFixer.test.ts`:

- Add to `defaultOptions.components`:

```ts
    add_provided_by: true,
    provided_by_patterns: [
      {
        field: 'purl',
        pattern: 'pkg:deb/astra',
        provided_by:
          'Операционная система специального назначения "Astra Linux Special Edition"',
      },
    ],
```

- Change `expect(wrapper.findAll('.rule-help-button')).toHaveLength(14)` to `.toHaveLength(ALL_FIX_RULES.length)`.
- Add these tests inside `describe('SbomFixer.vue', ...)`:

```ts
  it('renders the provided_by editor with the Astra default row', async () => {
    const wrapper = await mountFixer()
    const rows = wrapper.findAll(
      '[data-group="components"] [data-provided-by-row]',
    )
    expect(rows).toHaveLength(1)
    expect(
      (rows[0].find('[data-provided-by-field]').element as HTMLInputElement).value,
    ).toBe('purl')
    expect(
      (rows[0].find('[data-provided-by-value]').element as HTMLInputElement).value,
    ).toBe('pkg:deb/astra')
    expect(
      (rows[0].find('[data-provided-by-name]').element as HTMLInputElement).value,
    ).toContain('Astra Linux Special Edition')
  })

  it('fills provided_by rows from the loaded options', async () => {
    getFixOptionsMock.mockResolvedValue({
      options: {
        ...cloneOptions(),
        components: {
          ...cloneOptions().components,
          provided_by_patterns: [
            { field: 'name', pattern: 'vendor', provided_by: 'Vendor SZI' },
          ],
        },
      },
    })
    const wrapper = await mountFixer()
    const row = wrapper.find('[data-group="components"] [data-provided-by-row]')
    expect(
      (row.find('[data-provided-by-field]').element as HTMLInputElement).value,
    ).toBe('name')
    expect(
      (row.find('[data-provided-by-value]').element as HTMLInputElement).value,
    ).toBe('vendor')
    expect(
      (row.find('[data-provided-by-name]').element as HTMLInputElement).value,
    ).toBe('Vendor SZI')
  })

  it('adds and removes provided_by rows', async () => {
    const wrapper = await mountFixer()
    await wrapper.find('[data-action="add-provided-by"]').trigger('click')
    expect(
      wrapper.findAll('[data-group="components"] [data-provided-by-row]'),
    ).toHaveLength(2)
    await wrapper
      .findAll('[data-action="remove-provided-by"]')[1]
      .trigger('click')
    expect(
      wrapper.findAll('[data-group="components"] [data-provided-by-row]'),
    ).toHaveLength(1)
  })

  it('disables the provided_by editor while the rule is off', async () => {
    const wrapper = await mountFixer()
    expect(
      wrapper.find('[data-provided-by-field]').attributes('disabled'),
    ).toBeUndefined()
    await wrapper.find(rule('components.add_provided_by')).setValue(false)
    expect(
      wrapper.find('[data-provided-by-field]').attributes('disabled'),
    ).toBeDefined()
    expect(
      wrapper.find('[data-provided-by-value]').attributes('disabled'),
    ).toBeDefined()
    expect(
      wrapper.find('[data-provided-by-name]').attributes('disabled'),
    ).toBeDefined()
    expect(
      wrapper.find('[data-action="add-provided-by"]').attributes('disabled'),
    ).toBeDefined()
    expect(
      wrapper.find('[data-action="remove-provided-by"]').attributes('disabled'),
    ).toBeDefined()
  })

  it('keeps provided_by values when the rule is turned off', async () => {
    const wrapper = await mountFixer()
    await wrapper.find('[data-provided-by-name]').setValue('Vendor SZI')
    await wrapper.find(rule('components.add_provided_by')).setValue(false)
    expect(
      (wrapper.find('[data-provided-by-name]').element as HTMLInputElement).value,
    ).toBe('Vendor SZI')
  })

  it('normalizes provided_by rows and drops incomplete ones', async () => {
    getFixOptionsMock.mockResolvedValue({
      options: {
        ...cloneOptions(),
        components: {
          ...cloneOptions().components,
          provided_by_patterns: [
            { field: ' name ', pattern: ' vendor ', provided_by: ' SZI ' },
            { field: '', pattern: 'x', provided_by: 'ignored' },
            { field: 'purl', pattern: 'pkg:deb/astra', provided_by: '' },
          ],
        },
      },
    })
    const wrapper = await mountFixer()
    await wrapper.find('.save-settings').trigger('click')
    await flushPromises()
    const saved = saveFixOptionsMock.mock.calls[0][0] as SbomFixOptions
    expect(saved.components.provided_by_patterns).toEqual([
      { field: 'name', pattern: 'vendor', provided_by: 'SZI' },
    ])
  })

  it('sends provided_by options with the fix request', async () => {
    const wrapper = await mountFixer()
    await wrapper.find('[data-provided-by-name]').setValue('Vendor SZI')
    await selectFile(wrapper)
    await wrapper.find('.fix-button').trigger('click')
    await flushPromises()
    const sent = fixSbomMock.mock.calls[0][1] as SbomFixOptions
    expect(sent.components.provided_by_patterns).toEqual([
      {
        field: 'purl',
        pattern: 'pkg:deb/astra',
        provided_by: 'Vendor SZI',
      },
    ])
  })

  it('restores the Astra provided_by row on reset', async () => {
    const wrapper = await mountFixer()
    await wrapper.find('[data-provided-by-field]').setValue('name')
    await wrapper.find('.reset-defaults').trigger('click')
    const row = wrapper.find('[data-group="components"] [data-provided-by-row]')
    expect(
      (row.find('[data-provided-by-field]').element as HTMLInputElement).value,
    ).toBe('purl')
    expect(
      (row.find('[data-provided-by-name]').element as HTMLInputElement).value,
    ).toContain('Astra Linux Special Edition')
  })

  it('clears the Saved status when a provided_by row changes', async () => {
    const wrapper = await mountFixer()
    await wrapper.find('.save-settings').trigger('click')
    await flushPromises()
    expect(wrapper.find('.save-status').text()).toContain('Saved')
    await wrapper.find('[data-provided-by-name]').setValue('Vendor SZI')
    await flushPromises()
    expect(wrapper.find('.save-status').text()).not.toContain('Saved')
  })
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `npm --prefix frontend run test -- src/views/SbomFixer.test.ts`

Expected: FAIL because no `data-provided-by-*` elements exist.

- [ ] **Step 3: Implement the editor template**

In the components card, replace the plain `v-for` over `COMPONENTS_RULES` with a `<template v-for>` that keeps the existing rule row and adds a sibling editor for the new rule, mirroring the licenses card structure:

```html
            <div
              v-if="rule.key === 'add_provided_by'"
              class="pattern-rows"
              data-provided-by-editor
            >
              <div
                v-for="(row, idx) in providedByRows"
                :key="idx"
                class="pattern-row"
                data-provided-by-row
              >
                <input v-model="row.field" type="text" class="pattern-input" data-provided-by-field :placeholder="t('sbomFixer.providedBy.fieldPlaceholder')" :disabled="!options.components.add_provided_by" :aria-label="t('sbomFixer.providedBy.fieldPlaceholder')" />
                <span class="pattern-label">{{ t('sbomFixer.providedBy.contains') }}</span>
                <input v-model="row.pattern" type="text" class="pattern-input" data-provided-by-value :placeholder="t('sbomFixer.providedBy.valuePlaceholder')" :disabled="!options.components.add_provided_by" :aria-label="t('sbomFixer.providedBy.valuePlaceholder')" />
                <input v-model="row.provided_by" type="text" class="pattern-input" data-provided-by-name :placeholder="t('sbomFixer.providedBy.namePlaceholder')" :disabled="!options.components.add_provided_by" :aria-label="t('sbomFixer.providedBy.namePlaceholder')" />
                <button type="button" class="btn-delete" data-action="remove-provided-by" :disabled="!options.components.add_provided_by" :aria-label="t('sbomFixer.providedBy.removeRow')" @click="removeProvidedByRow(idx)">✕</button>
              </div>
              <button type="button" class="btn btn-small" data-action="add-provided-by" :disabled="!options.components.add_provided_by" @click="addProvidedByRow">{{ t('sbomFixer.providedBy.addRow') }}</button>
            </div>
```

- [ ] **Step 4: Implement the state, defaults, normalization, and reset**

In the script section of `SbomFixer.vue`:

- Add the default constant and helpers next to `emptyPatternRow`:

```ts
const DEFAULT_PROVIDED_BY_PATTERN: ProvidedByPatternItem = {
  field: 'purl',
  pattern: 'pkg:deb/astra',
  provided_by:
    'Операционная система специального назначения "Astra Linux Special Edition"',
}

function defaultProvidedByRow(): ProvidedByPatternItem {
  return { ...DEFAULT_PROVIDED_BY_PATTERN }
}

function emptyProvidedByRow(): ProvidedByPatternItem {
  return { field: '', pattern: '', provided_by: '' }
}

const providedByRows = ref<ProvidedByPatternItem[]>([defaultProvidedByRow()])
```

- In `defaultFixOptions()`, add to `components`:

```ts
      add_provided_by: true,
      provided_by_patterns: [defaultProvidedByRow()],
```

- In `applyOptions`, replace the `options.components = { ... }` line with a merge that clones the pattern list, then set rows:

```ts
  options.components = {
    ...options.components,
    ...next.components,
    provided_by_patterns: [
      ...(next.components.provided_by_patterns ?? []),
    ],
  }
```

After the existing `patternRows.value = ...` assignment, add:

```ts
  const providedByPatterns = next.components.provided_by_patterns ?? []
  providedByRows.value =
    providedByPatterns.length > 0
      ? providedByPatterns.map((row) => ({ ...row }))
      : [emptyProvidedByRow()]
```

- Add row actions and normalization next to the license equivalents:

```ts
function addProvidedByRow(): void {
  providedByRows.value.push(emptyProvidedByRow())
}

function removeProvidedByRow(index: number): void {
  providedByRows.value.splice(index, 1)
}

function normalizedProvidedByPatterns(): ProvidedByPatternItem[] {
  return providedByRows.value
    .map((row) => ({
      field: row.field.trim(),
      pattern: row.pattern.trim(),
      provided_by: row.provided_by.trim(),
    }))
    .filter(
      (row) =>
        row.field !== '' && row.pattern !== '' && row.provided_by !== '',
    )
}
```

- In `withNormalizedPatterns`, add:

```ts
  next.components.provided_by_patterns = normalizedProvidedByPatterns()
```

- Add a deep watch on `providedByRows` mirroring the `patternRows` watch.
- In `restoreDefaults`, add:

```ts
  providedByRows.value = [defaultProvidedByRow()]
```

- Import `ProvidedByPatternItem` in the existing type import from `../types/api`.

- [ ] **Step 5: Run the frontend tests to verify they pass**

Run: `npm --prefix frontend run test -- src/views/SbomFixer.test.ts src/views/sbomFixerRules.test.ts`

Expected: PASS. Fix only regressions in the new editor wiring.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/views/SbomFixer.vue frontend/src/views/SbomFixer.test.ts
git commit -m "feat: add provided_by editor to sbom fixer"
```

---

### Task 6: Full verification

**Files:**
- No production changes expected.

- [ ] **Step 1: Run the full backend suite**

Run: `.venv/bin/python -m pytest -q`

Expected: PASS. If only `tests/e2e/` fail because ecosyste.ms is unreachable, rerun with `SKIP_E2E=1 .venv/bin/python -m pytest -q` and require that run to pass.

- [ ] **Step 2: Run the frontend suite and build**

Run: `npm --prefix frontend run test && npm --prefix frontend run build`

Expected: PASS and a successful `vue-tsc`/Vite build.

- [ ] **Step 3: Fix any failures in the owning task and commit**

If a failure requires a code change, return to the task that owns the code, apply the fix, rerun the full commands, and commit with a `fix:` message scoped to that change. Do not create an empty commit when everything passes.

---

### Task 7: Update project specifications

**Files:**
- Modify: `specs/domains/sbom-fixing.md`
- Modify: `specs/domains/web-ui.md`
- Modify: `specs/contracts/api-contract.md`
- Modify: `specs/architecture/layers.md`

**Interfaces:**
- Consumes: the implemented behavior and test names from Tasks 1–6.

- [ ] **Step 1: Invoke the `vibespec-update` skill and read `specs/META.md`**

Use the `vibespec-update` skill before editing; preserve the existing document structure, table formatting, and cross-reference style.

- [ ] **Step 2: Update `specs/domains/sbom-fixing.md`**

- Change references from 14 to 15 static rules (intro, file list, `RULE_IDS`, UI catalog counts).
- Add `components.add_provided_by` to the `RULE_IDS` snippet after `components.fill_missing_gost_properties`.
- Add `ProvidedByPatternItem` and the two `ComponentsFixOptions` fields to the model snippet.
- Update the default-set paragraph: the new rule is `True` and carries the Astra default row; the default static stats row count becomes 8.
- Insert the rule as row 12 in the rule table and renumber the licenses rows to 13–15. Update every rule-number reference (`6–11` becomes `6–12`, `12–14` becomes `13–15`).
- Add a prose subsection `**components.add_provided_by.**` covering: active-row trimming, case-sensitive substring on top-level fields, first match top-down, components-only scope, filled-value skip, in-place fill, non-list `properties`, match-before-create, and the pipeline position after `fill_missing_gost_properties`.
- Update the notes list, statistics units (count = changed components), default-row count, API defaults, invariants, and the design-doc reference list.

- [ ] **Step 3: Update `specs/domains/web-ui.md`**

- Change 14 to 15 rules and `COMPONENTS_RULES` from 6 to 7 in the catalog description and rule-row rendering notes.
- Update the defaults sentence to include `add_provided_by = true` and the Astra default row.
- Add a sentence describing the local three-column editor under the new rule: inputs are disabled while the rule is off, rows survive toggling, empty saved list renders one empty row, incomplete rows are dropped on save, and reset restores the Astra row.

- [ ] **Step 4: Update `specs/contracts/api-contract.md`**

- Add the new options to the built-in defaults description.
- Extend the `components` example block with `add_provided_by` and `provided_by_patterns`.
- Note that a legacy file without the new keys loads with the enabled rule and the Astra row; explicitly saved empty list stays empty.

- [ ] **Step 5: Update `specs/architecture/layers.md`**

- Change 14 to 15 in the `fixer.py` description.
- Add `add_provided_by` and `provided_by_patterns` to the persisted `components.*` field list.

- [ ] **Step 6: Verify spec consistency**

Run: `grep -rn "14 static\|14 rules\|fourteen\|COMPONENTS_RULES with 6\|7 static rows\|6 entries" specs`

Expected: no stale counts remain for the Fix SBOM rule set. Manually confirm that all cross-references and table numbers are consistent.

- [ ] **Step 7: Commit**

```bash
git add specs
git commit -m "docs: describe provided_by rule in sbom fixer specs"
```

## Self-Review

- Spec coverage: model/defaults (Task 1), matching and property rules (Task 2), pipeline/stats/issues (Task 3), catalog/translations (Task 4), editor/save/reset (Task 5), verification (Task 6), documentation (Task 7).
- Review Focus items map to tests in Tasks 2 and 3; no uncovered item remains.
- Type consistency: `add_provided_by`, `provided_by_patterns`, `field`, `pattern`, `provided_by`, `GOST:provided_by` are used with the same names in backend, API tests, frontend types, and i18n.
