# Leaf Component Removal Rules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add three opt-in static rules to «Исправить SBOM» that delete leaf components lacking `purl`, having an invalid `purl`, or lacking `version`, and expose them in the options model, API, and UI.

**Architecture:** Extend `ComponentsFixOptions` with three `False`-default flags and append three ids to `RULE_IDS` at the start of the `components` group. Before the existing component filters, `_apply_components_rules` collects the ids of leaf components once and runs one rebuild pass per enabled removal rule, so containers with a non-empty `components` array are never removed. The UI renders the new rows from `COMPONENTS_RULES`, backed by the shared options payload.

**Tech Stack:** Python 3 / FastAPI / Pydantic / pytest (`packageurl-python`), Vue 3 `<script setup>` / Pinia / vue-i18n / Vitest.

**Spec:** `docs/superpowers/specs/2026-11-02-sbom-fixer-leaf-component-removal-design.md`

## Global Constraints

- Python commands run through `.venv/bin/python`; frontend commands through `npm --prefix frontend`.
- Full backend check: `.venv/bin/python -m pytest -q`. If only e2e tests fail on external network, rerun `SKIP_E2E=1 .venv/bin/python -m pytest -q`.
- Frontend checks: `npm --prefix frontend run test` and `npm --prefix frontend run build`.
- All user-facing strings go through i18n (`ru`, `en`); API errors stay machine-readable codes.
- `fix_sbom()` must not mutate its input (it works on `copy.deepcopy`).
- New rules default to disabled; with defaults, `stats` must keep exactly the current 7 rows and their order.
- Rule ids, in `RULE_IDS` order: `components.remove_leaf_missing_purl`, `components.remove_leaf_invalid_purl`, `components.remove_leaf_missing_version`.
- Option keys: `remove_leaf_missing_purl`, `remove_leaf_invalid_purl`, `remove_leaf_missing_version`.
- Leaf = component whose `components` value is absent, `null`, not a list, or an empty list. A non-empty list makes it a container.
- Leaf status is computed once before the removal passes; a container whose children were removed is not removed in the same run.
- The invalid-PURL rule checks only non-empty string values; missing/empty/`null`/non-string `purl` belongs to the missing-PURL rule.
- All three rules walk only the root `components[]` tree; `metadata.component` is never touched.
- Each task ends with a local commit (project workflow).

## Review Focus

- Container with a non-empty `components` array must never be removed by any of the three rules — pinned in Task 2 (`test_leaf_rules_never_remove_containers`).
- A component with `components: []` is a leaf and may be removed — pinned in Task 2 (`test_remove_leaf_missing_purl_removes_empty_components_array_leaf`).
- Non-object entries in a `components` array must be preserved — pinned in Task 2 (`test_remove_leaf_missing_purl_preserves_non_objects`).
- The invalid-PURL rule must not delete a component whose `purl` is missing or empty — pinned in Task 2 (`test_remove_leaf_invalid_purl_ignores_missing_and_empty`).
- Removed components must not appear in other rules' statistics or in `issues` — pinned in Task 2 (`test_leaf_removal_runs_before_other_component_rules`, `test_removed_components_do_not_appear_in_issues`).

---

### Task 1: Backend options, rule ids, persistence, and API validation

**Files:**
- Modify: `src/purl_resolver/sbom/fixer.py:60-72` (`RULE_IDS`), `src/purl_resolver/sbom/fixer.py:75-79` (`ComponentsFixOptions`)
- Modify: `tests/test_sbom_fixer.py:15-30` (`NEW_RULE_IDS`), `:48-90` (defaults and all-enabled tests), `:1968-1976` (rule count)
- Modify: `tests/test_sbom_fix_options_store.py`
- Modify: `tests/test_sbom_fix_api.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `ComponentsFixOptions.remove_leaf_missing_purl: bool`, `.remove_leaf_invalid_purl: bool`, `.remove_leaf_missing_version: bool`, all defaults `False`; `RULE_IDS` tuple of 14 ids in the exact order below.

- [ ] **Step 1: Update the failing tests**

In `tests/test_sbom_fixer.py`, set the canonical tuple:

```python
NEW_RULE_IDS = (
    "reorder",
    "set_spec_version",
    "increment_version",
    "add_timestamp",
    "add_manufacturer",
    "components.remove_leaf_missing_purl",
    "components.remove_leaf_invalid_purl",
    "components.remove_leaf_missing_version",
    "components.filter_external_references",
    "components.filter_properties",
    "components.fill_missing_gost_properties",
    "licenses.filter_non_proprietary",
    "licenses.add_proprietary",
    "licenses.remove_proprietary_source_references",
)
```

Extend `test_defaults_expose_flat_base_options` with:

```python
    assert o.components.remove_leaf_missing_purl is False
    assert o.components.remove_leaf_invalid_purl is False
    assert o.components.remove_leaf_missing_version is False
```

Rename `test_all_enabled_rules_yield_eleven_stats_in_canonical_order` to `test_all_enabled_rules_yield_fourteen_stats_in_canonical_order` and enable every flag:

```python
    options = SbomFixOptions(
        components={
            "remove_leaf_missing_purl": True,
            "remove_leaf_invalid_purl": True,
            "remove_leaf_missing_version": True,
            "fill_missing_gost_properties": True,
        },
        licenses={
            "filter_non_proprietary": True,
            "add_proprietary": True,
            "remove_proprietary_source_references": True,
        },
    )
```

Change `test_license_rule_ids_come_last_in_execution_order` to assert `len(RULE_IDS) == 14`; the last three ids stay unchanged.

The two default-stats tests currently build their expected list by excluding only `components.fill_missing_gost_properties` and `licenses.*`. Add a constant after `NEW_RULE_IDS` and use it in both tests so the expected default set excludes the three new opt-in rules too:

```python
DEFAULT_RULE_IDS = tuple(
    rule
    for rule in NEW_RULE_IDS
    if not rule.startswith("licenses.")
    and rule != "components.fill_missing_gost_properties"
    and not rule.startswith("components.remove_leaf_")
)
```

`test_default_stats_contain_only_enabled_rules` asserts `[stat.rule_id for stat in result.stats] == list(DEFAULT_RULE_IDS)`. `test_fix_sbom_copies_input_and_emits_zero_stats_for_enabled_rules` keeps `assert len(result.stats) == 7` and uses the same list.

In `tests/test_sbom_fix_options_store.py`, import `ComponentsFixOptions` and add:

```python
def test_save_load_roundtrip_including_leaf_removal_flags(tmp_path):
    store = SbomFixOptionsStore(tmp_path / "options.json")
    options = SbomFixOptions(
        components=ComponentsFixOptions(
            remove_leaf_missing_purl=True,
            remove_leaf_invalid_purl=True,
            remove_leaf_missing_version=True,
        )
    )
    store.save(options)
    assert store.load() == options


def test_old_file_without_leaf_flags_uses_disabled_defaults(tmp_path):
    path = tmp_path / "old.json"
    path.write_text('{"components": {"filter_properties": false}}', encoding="utf-8")
    loaded = SbomFixOptionsStore(path).load()
    assert loaded.components.filter_properties is False
    assert loaded.components.remove_leaf_missing_purl is False
    assert loaded.components.remove_leaf_invalid_purl is False
    assert loaded.components.remove_leaf_missing_version is False
```

In `tests/test_sbom_fix_api.py`, add a defaults assertion to the existing options endpoint test and a rejection test:

```python
def test_fix_options_endpoint_returns_leaf_flags_disabled(client):
    response = client.get("/api/v1/sbom/fix/options")
    assert response.status_code == 200
    components = response.json()["options"]["components"]
    assert components["remove_leaf_missing_purl"] is False
    assert components["remove_leaf_invalid_purl"] is False
    assert components["remove_leaf_missing_version"] is False


def test_fix_options_endpoint_rejects_non_boolean_leaf_flag(client):
    response = client.post(
        "/api/v1/sbom/fix/options",
        json={"options": {"components": {"remove_leaf_missing_purl": "maybe"}}},
    )
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_options"
```

Do not change the endpoint.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_sbom_fixer.py tests/test_sbom_fix_options_store.py tests/test_sbom_fix_api.py -q`

Expected: failures on missing attributes, `RULE_IDS` order/count, and the new options assertions.

- [ ] **Step 3: Implement the model and catalogue changes**

In `src/purl_resolver/sbom/fixer.py`:

```python
RULE_IDS: tuple[str, ...] = (
    "reorder",
    "set_spec_version",
    "increment_version",
    "add_timestamp",
    "add_manufacturer",
    "components.remove_leaf_missing_purl",
    "components.remove_leaf_invalid_purl",
    "components.remove_leaf_missing_version",
    "components.filter_external_references",
    "components.filter_properties",
    "components.fill_missing_gost_properties",
    "licenses.filter_non_proprietary",
    "licenses.add_proprietary",
    "licenses.remove_proprietary_source_references",
)


class ComponentsFixOptions(BaseModel):
    remove_leaf_missing_purl: bool = False
    remove_leaf_invalid_purl: bool = False
    remove_leaf_missing_version: bool = False
    filter_external_references: bool = True
    filter_properties: bool = True
    fill_missing_gost_properties: bool = False
```

`_rule_enabled` already resolves the `components.` prefix; no change is needed.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_sbom_fixer.py tests/test_sbom_fix_options_store.py tests/test_sbom_fix_api.py -q`

Expected: PASS. The new rules are still inert because Task 2 has not wired them in.

- [ ] **Step 5: Commit**

```bash
git add src/purl_resolver/sbom/fixer.py tests/test_sbom_fixer.py tests/test_sbom_fix_options_store.py tests/test_sbom_fix_api.py
git commit -m "feat: add leaf component removal options to sbom fixer"
```

---

### Task 2: Leaf detection and the three removal rules

**Files:**
- Modify: `src/purl_resolver/sbom/fixer.py:1-12` (import `purl_utils`), new helpers after `_walk_components`, `_apply_components_rules` at `:613-647`
- Test: `tests/test_sbom_fixer.py` (new tests near the existing `components.*` rule tests, around `:891-1100`)

**Interfaces:**
- Consumes: the three option fields and `RULE_IDS` entries from Task 1.
- Produces (private, may be renamed only if tests stay green):
  - `_is_leaf_component(component: dict) -> bool`
  - `_collect_leaf_ids(components: list) -> set[int]`
  - `_remove_leaf_components(components: list, leaf_ids: set[int], predicate: Callable[[dict], bool]) -> tuple[list, int]`
  - `_has_missing_purl(component: dict) -> bool`, `_has_invalid_purl(component: dict) -> bool`, `_has_missing_version(component: dict) -> bool`

- [ ] **Step 1: Write the failing tests**

Add a helper next to `_stats`:

```python
def _leaf_options(**flags) -> SbomFixOptions:
    return SbomFixOptions(
        reorder=False,
        set_spec_version=False,
        increment_version=False,
        add_timestamp=False,
        add_manufacturer=False,
        components={
            "filter_external_references": False,
            "filter_properties": False,
            **flags,
        },
    )
```

Add these tests (names are the interface between plan and reviewer):

```python
@pytest.mark.parametrize("purl", [None, "", 5, ["pkg:pypi/a@1"]])
def test_remove_leaf_missing_purl_removes_null_empty_and_non_string(purl):
    data = {"components": [{"name": "a", "version": "1", "purl": purl}]}
    result = fix_sbom(data, _leaf_options(remove_leaf_missing_purl=True))
    assert result.fixed_sbom["components"] == []
    assert _stats(result)["components.remove_leaf_missing_purl"] == 1


def test_remove_leaf_missing_purl_removes_absent_purl():
    data = {"components": [{"name": "a", "version": "1"}]}
    result = fix_sbom(data, _leaf_options(remove_leaf_missing_purl=True))
    assert result.fixed_sbom["components"] == []
    assert _stats(result)["components.remove_leaf_missing_purl"] == 1


def test_remove_leaf_missing_purl_keeps_valid_purl():
    data = {"components": [{"name": "a", "version": "1", "purl": "pkg:pypi/a@1"}]}
    result = fix_sbom(data, _leaf_options(remove_leaf_missing_purl=True))
    assert result.fixed_sbom["components"][0]["purl"] == "pkg:pypi/a@1"
    assert _stats(result)["components.remove_leaf_missing_purl"] == 0


def test_remove_leaf_missing_purl_works_at_all_levels_and_preserves_containers():
    data = {"components": [{
        "name": "parent",
        "purl": "pkg:pypi/parent@1",
        "version": "1",
        "components": [{
            "name": "child",
            "purl": "pkg:pypi/child@1",
            "version": "1",
            "components": [{"name": "grandchild"}],
        }],
    }]}
    result = fix_sbom(data, _leaf_options(remove_leaf_missing_purl=True))
    parent = result.fixed_sbom["components"][0]
    assert parent["name"] == "parent"
    assert parent["components"][0]["components"] == []
    assert _stats(result)["components.remove_leaf_missing_purl"] == 1


def test_remove_leaf_missing_purl_treats_empty_components_array_as_leaf():
    data = {"components": [
        {"name": "no-purl", "components": []},
        {"name": "valid", "purl": "pkg:pypi/a@1", "components": []},
    ]}
    result = fix_sbom(data, _leaf_options(remove_leaf_missing_purl=True))
    assert [c["name"] for c in result.fixed_sbom["components"]] == ["valid"]
    assert _stats(result)["components.remove_leaf_missing_purl"] == 1
```

```python
def test_remove_leaf_missing_purl_preserves_non_objects():
    data = {"components": ["not-an-object", None, {"name": "a"}]}
    result = fix_sbom(data, _leaf_options(remove_leaf_missing_purl=True))
    assert result.fixed_sbom["components"] == ["not-an-object", None]
    assert _stats(result)["components.remove_leaf_missing_purl"] == 1


def test_leaf_rules_never_remove_containers():
    container = {
        "name": "container",
        "components": [{"name": "child", "purl": "pkg:pypi/child@1", "version": "1"}],
    }
    data = {"components": [container]}
    result = fix_sbom(
        data,
        _leaf_options(
            remove_leaf_missing_purl=True,
            remove_leaf_missing_version=True,
        ),
    )
    assert result.fixed_sbom["components"][0]["name"] == "container"
    assert _stats(result)["components.remove_leaf_missing_purl"] == 0
    assert _stats(result)["components.remove_leaf_missing_version"] == 0


def test_container_is_not_rechecked_after_children_removed():
    data = {"components": [{
        "name": "container",
        "components": [{"name": "child"}],
    }]}
    result = fix_sbom(
        data,
        _leaf_options(remove_leaf_missing_purl=True),
    )
    parent = result.fixed_sbom["components"][0]
    assert parent["name"] == "container"
    assert parent["components"] == []


def test_remove_leaf_invalid_purl_removes_invalid_keeps_valid():
    data = {"components": [
        {"name": "bad", "purl": "not-a-purl", "version": "1"},
        {"name": "good", "purl": "pkg:pypi/a@1", "version": "1"},
    ]}
    result = fix_sbom(data, _leaf_options(remove_leaf_invalid_purl=True))
    assert [c["name"] for c in result.fixed_sbom["components"]] == ["good"]
    assert _stats(result)["components.remove_leaf_invalid_purl"] == 1


@pytest.mark.parametrize("purl", [None, "", 5])
def test_remove_leaf_invalid_purl_ignores_missing_and_empty(purl):
    data = {"components": [{"name": "a", "version": "1", "purl": purl}]}
    result = fix_sbom(data, _leaf_options(remove_leaf_invalid_purl=True))
    assert result.fixed_sbom["components"] == data["components"]
    assert _stats(result)["components.remove_leaf_invalid_purl"] == 0


def test_remove_leaf_invalid_purl_ignores_absent_purl():
    data = {"components": [{"name": "a", "version": "1"}]}
    result = fix_sbom(data, _leaf_options(remove_leaf_invalid_purl=True))
    assert result.fixed_sbom["components"] == data["components"]
    assert _stats(result)["components.remove_leaf_invalid_purl"] == 0


@pytest.mark.parametrize("version", [None, "", 5, ["1"]])
def test_remove_leaf_missing_version_removes_null_empty_and_non_string(version):
    data = {"components": [{"name": "a", "purl": "pkg:pypi/a@1", "version": version}]}
    result = fix_sbom(data, _leaf_options(remove_leaf_missing_version=True))
    assert result.fixed_sbom["components"] == []
    assert _stats(result)["components.remove_leaf_missing_version"] == 1


def test_remove_leaf_missing_version_removes_absent_version():
    data = {"components": [{"name": "a", "purl": "pkg:pypi/a@1"}]}
    result = fix_sbom(data, _leaf_options(remove_leaf_missing_version=True))
    assert result.fixed_sbom["components"] == []
    assert _stats(result)["components.remove_leaf_missing_version"] == 1


def test_remove_leaf_missing_version_keeps_non_empty():
    data = {"components": [{"name": "a", "purl": "pkg:pypi/a@1", "version": "1.0"}]}
    result = fix_sbom(data, _leaf_options(remove_leaf_missing_version=True))
    assert result.fixed_sbom["components"][0]["version"] == "1.0"
    assert _stats(result)["components.remove_leaf_missing_version"] == 0


def test_leaf_rules_first_match_wins():
    data = {"components": [{"name": "a"}]}
    result = fix_sbom(
        data,
        _leaf_options(
            remove_leaf_missing_purl=True,
            remove_leaf_missing_version=True,
        ),
    )
    assert result.fixed_sbom["components"] == []
    assert _stats(result)["components.remove_leaf_missing_purl"] == 1
    assert _stats(result)["components.remove_leaf_missing_version"] == 0


def test_leaf_removal_runs_before_other_component_rules():
    data = {"components": [{
        "name": "a",
        "externalReferences": [{"type": "website", "url": "https://example.com"}],
    }]}
    result = fix_sbom(
        data,
        SbomFixOptions(
            reorder=False,
            set_spec_version=False,
            increment_version=False,
            add_timestamp=False,
            add_manufacturer=False,
            components={
                "remove_leaf_missing_purl": True,
                "filter_external_references": True,
            },
        ),
    )
    assert result.fixed_sbom["components"] == []
    assert _stats(result)["components.filter_external_references"] == 0


def test_removed_components_do_not_appear_in_issues():
    data = {"bomFormat": "CycloneDX", "components": [{"name": "a"}]}
    result = fix_sbom(data, _leaf_options(remove_leaf_missing_purl=True))
    assert result.fixed_sbom["components"] == []
    assert not [i for i in result.issues if i.path == "$.components[0]"]


def test_leaf_rules_do_not_touch_metadata_component():
    data = {
        "metadata": {"component": {"name": "app"}},
        "components": [{"name": "a", "purl": "pkg:pypi/a@1", "version": "1"}],
    }
    result = fix_sbom(
        data,
        _leaf_options(
            remove_leaf_missing_purl=True,
            remove_leaf_missing_version=True,
        ),
    )
    assert result.fixed_sbom["metadata"]["component"] == {"name": "app"}
    assert len(result.fixed_sbom["components"]) == 1


def test_leaf_rules_do_not_mutate_input():
    data = {"components": [{"name": "a"}]}
    before = copy.deepcopy(data)
    fix_sbom(data, _leaf_options(remove_leaf_missing_purl=True))
    assert data == before
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_sbom_fixer.py -q -k "leaf"`

Expected: FAIL — the rules are enabled in options but not applied, so components remain.

- [ ] **Step 3: Implement the helpers and wire them in**

At the top of `src/purl_resolver/sbom/fixer.py`:

```python
from ..purl_utils import PurlValidationError, validate
```

Add after `_walk_components`:

```python
def _is_leaf_component(component: dict) -> bool:
    nested = component.get("components")
    return not (isinstance(nested, list) and nested)


def _collect_leaf_ids(components: list) -> set[int]:
    leaf_ids: set[int] = set()
    for component in components:
        if not isinstance(component, dict):
            continue
        if _is_leaf_component(component):
            leaf_ids.add(id(component))
        else:
            leaf_ids |= _collect_leaf_ids(component["components"])
    return leaf_ids


def _remove_leaf_components(
    components: list,
    leaf_ids: set[int],
    predicate: Callable[[dict], bool],
) -> tuple[list, int]:
    kept: list = []
    removed = 0
    for component in components:
        if isinstance(component, dict):
            nested = component.get("components")
            if isinstance(nested, list) and nested:
                new_nested, nested_removed = _remove_leaf_components(
                    nested, leaf_ids, predicate
                )
                component["components"] = new_nested
                removed += nested_removed
            if id(component) in leaf_ids and predicate(component):
                removed += 1
                continue
        kept.append(component)
    return kept, removed


def _has_missing_purl(component: dict) -> bool:
    return not _is_non_empty_string(component.get("purl"))


def _has_invalid_purl(component: dict) -> bool:
    purl = component.get("purl")
    if not _is_non_empty_string(purl):
        return False
    try:
        validate(purl)
    except PurlValidationError:
        return True
    return False


def _has_missing_version(component: dict) -> bool:
    return not _is_non_empty_string(component.get("version"))


def _apply_leaf_removals(
    data: dict,
    options: SbomFixOptions,
    counts: dict[str, int],
) -> None:
    components = data.get("components")
    if not isinstance(components, list):
        return
    leaf_ids = _collect_leaf_ids(components)
    for rule_id, predicate in (
        ("components.remove_leaf_missing_purl", _has_missing_purl),
        ("components.remove_leaf_invalid_purl", _has_invalid_purl),
        ("components.remove_leaf_missing_version", _has_missing_version),
    ):
        if not _rule_enabled(rule_id, options):
            continue
        components, removed = _remove_leaf_components(
            components, leaf_ids, predicate
        )
        counts[rule_id] = counts.get(rule_id, 0) + removed
    data["components"] = components
```

In `_apply_components_rules`, make the first line:

```python
    _apply_leaf_removals(data, options, counts)
```

The existing `filter_external_references`, `filter_properties`, and `fill_gost` logic stays unchanged and runs against the pruned tree.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_sbom_fixer.py -q`

Expected: PASS, including the pre-existing `components.*` tests.

- [ ] **Step 5: Commit**

```bash
git add src/purl_resolver/sbom/fixer.py tests/test_sbom_fixer.py
git commit -m "feat: remove leaf components without valid purl or version"
```

---

### Task 3: Frontend types, rule catalogue, i18n, and page defaults

**Files:**
- Modify: `frontend/src/types/api.ts:202-206` (`ComponentsFixOptions`)
- Modify: `frontend/src/views/sbomFixerRules.ts:121-217` (`COMPONENTS_RULES`)
- Modify: `frontend/src/views/SbomFixer.vue:406-417` (`defaultFixOptions`)
- Modify: `frontend/src/i18n/locales/ru.json`, `frontend/src/i18n/locales/en.json`
- Test: `frontend/src/views/sbomFixerRules.test.ts`, `frontend/src/views/SbomFixer.test.ts`

**Interfaces:**
- Consumes: rule ids and option keys from Tasks 1–2.
- Produces: `ComponentsFixOptions` with three new boolean fields; `COMPONENTS_RULES` of length 6 with the three new entries first.

- [ ] **Step 1: Update the failing frontend tests**

In `frontend/src/views/sbomFixerRules.test.ts`:

- `GROUPS` components entry becomes `size: 6`.
- Rename `covers all 11 rules...` to `covers all 14 rules...` and assert `toHaveLength(14)` twice.
- In the group test, replace the first-id assertion:

```ts
expect(COMPONENTS_RULES.map((rule) => rule.id)).toEqual([
  'components.remove_leaf_missing_purl',
  'components.remove_leaf_invalid_purl',
  'components.remove_leaf_missing_version',
  'components.filter_external_references',
  'components.filter_properties',
  'components.fill_missing_gost_properties',
])
```

In `frontend/src/views/SbomFixer.test.ts`, update the `defaultOptions` fixture's `components` block with `remove_leaf_missing_purl: false`, `remove_leaf_invalid_purl: false`, `remove_leaf_missing_version: false`.

Update the help-count assertion from 11 to 14. Extend the component master test list:

```ts
    for (const id of [
      'components.remove_leaf_missing_purl',
      'components.remove_leaf_invalid_purl',
      'components.remove_leaf_missing_version',
      'components.filter_external_references',
      'components.filter_properties',
      'components.fill_missing_gost_properties',
    ]) {
```

Add tests:

```ts
  it('renders six component rule rows with help', async () => {
    const wrapper = await mountFixer()
    const card = wrapper.find('.group-card[data-group="components"]')
    expect(card.findAll('[data-rule-row]')).toHaveLength(6)
    expect(card.findAll('.rule-help-button')).toHaveLength(6)
  })

  it('saves the three leaf removal flags as disabled by default', async () => {
    const wrapper = await mountFixer()
    await wrapper.find('.save-settings').trigger('click')
    await flushPromises()
    const saved = saveFixOptionsMock.mock.calls[0][0] as SbomFixOptions
    expect(saved.components.remove_leaf_missing_purl).toBe(false)
    expect(saved.components.remove_leaf_invalid_purl).toBe(false)
    expect(saved.components.remove_leaf_missing_version).toBe(false)
  })

  it('resets leaf removal flags to false', async () => {
    const wrapper = await mountFixer()
    await wrapper.find(rule('components.remove_leaf_missing_purl')).setValue(true)
    await wrapper.find(rule('components.remove_leaf_missing_version')).setValue(true)
    await wrapper.find('.reset-defaults').trigger('click')
    expect((wrapper.find(rule('components.remove_leaf_missing_purl')).element as HTMLInputElement).checked).toBe(false)
    expect((wrapper.find(rule('components.remove_leaf_missing_version')).element as HTMLInputElement).checked).toBe(false)
  })
```

Use the actual reset-button selector from the existing tests (`reset-defaults` or its equivalent), and the existing `rule()` helper.

- [ ] **Step 2: Run the frontend tests to verify they fail**

Run: `npm --prefix frontend run test -- src/views/sbomFixerRules.test.ts src/views/SbomFixer.test.ts`

Expected: FAIL on catalogue length, missing rule ids, missing i18n keys, and missing option fields.

- [ ] **Step 3: Implement types, catalogue, defaults, and locale entries**

`frontend/src/types/api.ts`:

```ts
export interface ComponentsFixOptions {
  remove_leaf_missing_purl: boolean
  remove_leaf_invalid_purl: boolean
  remove_leaf_missing_version: boolean
  filter_external_references: boolean
  filter_properties: boolean
  fill_missing_gost_properties: boolean
}
```

`frontend/src/views/sbomFixerRules.ts` — prepend entries to `COMPONENTS_RULES`:

```ts
  {
    id: 'components.remove_leaf_missing_purl',
    key: 'remove_leaf_missing_purl',
    example: {
      before: `{
  "components": [
    {
      "type": "library",
      "name": "vendor-tool",
      "version": "1.0.0"
    }
  ]
}`,
      after: `{
  "components": []
}`,
    },
  },
  {
    id: 'components.remove_leaf_invalid_purl',
    key: 'remove_leaf_invalid_purl',
    example: {
      before: `{
  "components": [
    {
      "type": "library",
      "name": "broken",
      "version": "1.0.0",
      "purl": "not-a-purl"
    }
  ]
}`,
      after: `{
  "components": []
}`,
    },
  },
  {
    id: 'components.remove_leaf_missing_version',
    key: 'remove_leaf_missing_version',
    example: {
      before: `{
  "components": [
    {
      "type": "library",
      "name": "left-pad",
      "purl": "pkg:npm/left-pad@1.3.0"
    }
  ]
}`,
      after: `{
  "components": []
}`,
    },
  },
```

`frontend/src/views/SbomFixer.vue`, `defaultFixOptions()`:

```ts
    components: {
      remove_leaf_missing_purl: false,
      remove_leaf_invalid_purl: false,
      remove_leaf_missing_version: false,
      filter_external_references: true,
      filter_properties: true,
      fill_missing_gost_properties: false,
    },
```

Locale keys — `sbomFixer.rules.components.*` (exact ru labels; en may be worded equivalently):

- `remove_leaf_missing_purl`: «Удалить компоненты-листья без PURL» / "Remove leaf components without PURL"
- `remove_leaf_invalid_purl`: «Удалить компоненты-листья с некорректным PURL» / "Remove leaf components with invalid PURL"
- `remove_leaf_missing_version`: «Удалить компоненты-листья без version» / "Remove leaf components without version"

Add `sbomFixer.help.components.remove_leaf_missing_purl`, `...remove_leaf_invalid_purl`, `...remove_leaf_missing_version` (each > 20 characters) stating: only leaf components are removed; a non-empty `components` array is preserved; missing means absent/`null`/empty/non-string; invalid PURL means a non-empty string rejected by the Package URL specification and missing/empty is not checked; an emptied array stays `[]`; `metadata.component` is untouched.

- [ ] **Step 4: Run the frontend tests and build**

Run: `npm --prefix frontend run test -- src/views/sbomFixerRules.test.ts src/views/SbomFixer.test.ts`

Expected: PASS.

Run: `npm --prefix frontend run build`

Expected: PASS with no TypeScript errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/api.ts frontend/src/views/sbomFixerRules.ts frontend/src/views/SbomFixer.vue frontend/src/i18n/locales/ru.json frontend/src/i18n/locales/en.json frontend/src/views/sbomFixerRules.test.ts frontend/src/views/SbomFixer.test.ts
git commit -m "feat: expose leaf component removal rules in the sbom fixer ui"
```

---

### Task 4: Project specs update and full verification

**Files:**
- Modify: `specs/domains/sbom-fixing.md`
- Modify: `specs/contracts/api-contract.md`
- Modify: `specs/domains/web-ui.md`

**Interfaces:**
- Consumes: all code from Tasks 1–3.
- Produces: specs matching the shipped behavior.

- [ ] **Step 1: Run the full backend and frontend suites**

Run: `.venv/bin/python -m pytest -q`

Expected: PASS. If only `tests/e2e/` fails on network timeouts, run `SKIP_E2E=1 .venv/bin/python -m pytest -q` and record that in the commit message body.

Run: `npm --prefix frontend run test && npm --prefix frontend run build`

Expected: PASS.

- [ ] **Step 2: Update the domain spec**

Use the `vibespec-update` skill. In `specs/domains/sbom-fixing.md`:

- Change the rule count in the Description and Core Types from 11 to 14 and `RULE_IDS` to the tuple from Task 1.
- In Key Files, change «the 11 static rules» to 14 and `COMPONENTS_RULES` from 3 entries to 6.
- Add the three fields to the `ComponentsFixOptions` snippet with defaults `False`.
- Update the default-set sentence: the three `components.remove_leaf_*` flags join the opt-in rules; default static rows stay 7 (14 rules minus 4 existing opt-in rules and 3 new opt-in rules).
- Update the Statistics note «With defaults there are 7 static rows (the 11 rules minus the four opt-in rules…)» to the 14-rule arithmetic above.
- Insert three rows into the rules table before `components.filter_external_references`, with `count` = removed leaf components, leaf definition, and the rule-specific predicate from the design §6.
- Update the flow line for step 5: leaf removals run first, then the existing filters and GOST fill.
- Add invariants: leaf-only removal; leaf set computed once; invalid-PURL rule skips missing/empty; removed components absent from later stats and `issues`; `metadata.component` untouched; emptied array stays `[]`.

- [ ] **Step 3: Update the API contract**

In `specs/contracts/api-contract.md`, add the three keys to the `components` options example (both occurrences), state that they default to `false`, and note that an old options file without them loads with `false`.

- [ ] **Step 4: Update the web UI spec**

In `specs/domains/web-ui.md`, change the `components[]` card description from three rules to six, list the three new rows first, and state that the master checkbox, «Выбрать всё» / «Снять всё», help panels, save payload, and reset cover all six flags.

- [ ] **Step 5: Re-run the frontend tests that read the locale files**

Run: `npm --prefix frontend run test -- src/views/sbomFixerRules.test.ts src/views/SbomFixer.test.ts`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add specs/domains/sbom-fixing.md specs/contracts/api-contract.md specs/domains/web-ui.md
git commit -m "docs: describe leaf component removal rules in sbom fixer specs"
```
