import copy
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from purl_resolver.sbom.fixer import (
    RULE_IDS,
    FixIssue,
    LicensePatternItem,
    OptionalFieldsFixOptions,
    SbomFixOptions,
    _collect_component_issues,
    _fill_gost_properties,
    _filter_external_references,
    _filter_properties,
    _reorder,
    _walk_components,
    fix_sbom,
)
from purl_resolver.sbom.optional_fields import DEFAULT_KEEP_FIELDS

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

DEFAULT_RULE_IDS = tuple(
    rule
    for rule in NEW_RULE_IDS
    if not rule.startswith("licenses.")
    and rule != "components.fill_missing_gost_properties"
    and not rule.startswith("components.remove_leaf_")
)


def _reorder_only_options() -> SbomFixOptions:
    return SbomFixOptions(
        reorder=True,
        set_spec_version=False,
        increment_version=False,
        add_timestamp=False,
        add_manufacturer=False,
    )


def test_defaults_expose_flat_base_options():
    o = SbomFixOptions()
    assert o.reorder is True
    assert o.set_spec_version is True
    assert o.spec_version == "1.7"
    assert o.increment_version is True
    assert o.add_timestamp is True
    assert o.add_manufacturer is True
    assert o.manufacturer == "Positive Technologies"
    assert o.components.fill_missing_gost_properties is False
    assert o.components.remove_leaf_missing_purl is False
    assert o.components.remove_leaf_invalid_purl is False
    assert o.components.remove_leaf_missing_version is False
    assert o.optional_fields.keep == list(DEFAULT_KEEP_FIELDS)
    for removed in ("root", "metadata"):
        assert not hasattr(o, removed)
    for removed in ("reorder", "remove_dependencies", "remove_services"):
        assert not hasattr(o.components, removed)


def test_default_stats_contain_only_enabled_rules():
    result = fix_sbom(
        {"bomFormat": "CycloneDX", "specVersion": "1.7", "version": 1},
        SbomFixOptions(),
    )
    assert [stat.rule_id for stat in result.stats] == list(DEFAULT_RULE_IDS)


def test_all_enabled_rules_yield_fourteen_stats_in_canonical_order():
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
    result = fix_sbom(
        {"bomFormat": "CycloneDX", "specVersion": "1.7", "version": 1}, options
    )
    assert [stat.rule_id for stat in result.stats] == list(NEW_RULE_IDS)


def test_keep_list_normalizes_entries_and_rejects_non_list():
    options = OptionalFieldsFixOptions(
        keep=[" components[].scope ", "root.dependencies", "root.dependencies", "bad"]
    )
    assert options.keep == ["components[].scope", "root.dependencies"]

    with pytest.raises(ValidationError):
        OptionalFieldsFixOptions(keep="components[].scope")

    with pytest.raises(ValidationError):
        OptionalFieldsFixOptions(keep=None)


@pytest.mark.parametrize("value", ["", " ", "   ", "1", "1.7.0", "v1.7", "1,7", 1.7])
def test_invalid_spec_version_rejected(value):
    with pytest.raises(ValidationError):
        SbomFixOptions(spec_version=value)


def test_spec_version_is_trimmed_before_validation():
    options = SbomFixOptions(spec_version=" 1.7 ")
    assert options.spec_version == "1.7"


def test_rule_ids_match_canonical_order():
    assert RULE_IDS == NEW_RULE_IDS


def test_fix_sbom_copies_input_and_emits_zero_stats_for_enabled_rules():
    data = {"bomFormat": "CycloneDX", "specVersion": "1.7"}
    result = fix_sbom(data, SbomFixOptions())
    assert result.fixed_sbom == data
    assert result.fixed_sbom is not data
    assert result.changed is False
    assert len(result.stats) == 7
    assert all(stat.count == 0 for stat in result.stats)
    assert [stat.rule_id for stat in result.stats] == list(DEFAULT_RULE_IDS)


@pytest.mark.parametrize(
    "component",
    [
        {"type": "application", "name": "app", "version": "1.0"},
        {"type": "application", "name": "app", "version": "1.0", "manufacturer": None},
        {"type": "application", "name": "app", "version": "1.0", "manufacturer": {}},
        {
            "type": "application",
            "name": "app",
            "version": "1.0",
            "manufacturer": {"name": "  "},
        },
    ],
)
def test_add_manufacturer_fills_missing_or_empty(component):
    data = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.7",
        "version": 1,
        "metadata": {"component": component},
    }
    options = SbomFixOptions(manufacturer="  Acme  ")
    result = fix_sbom(data, options)
    assert data["metadata"]["component"].get("manufacturer") in (None, {}, {"name": "  "})
    assert result.fixed_sbom["metadata"]["component"]["manufacturer"] == {"name": "Acme"}
    stats = {stat.rule_id: stat.count for stat in result.stats}
    assert stats["add_manufacturer"] == 1


def test_add_manufacturer_keeps_existing_value_and_ignores_supplier():
    data = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.7",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "name": "app",
                "version": "1.0",
                "manufacturer": {"name": "Existing"},
                "supplier": {"name": "Supplier"},
            }
        },
    }
    result = fix_sbom(data, SbomFixOptions())
    assert result.fixed_sbom["metadata"]["component"]["manufacturer"] == {"name": "Existing"}
    assert result.fixed_sbom["metadata"]["component"]["supplier"] == {"name": "Supplier"}


def test_add_manufacturer_disabled_leaves_component_untouched():
    data = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.7",
        "version": 1,
        "metadata": {
            "component": {"type": "application", "name": "app", "version": "1.0"}
        },
    }
    options = SbomFixOptions(add_manufacturer=False)
    result = fix_sbom(data, options)
    assert "manufacturer" not in result.fixed_sbom["metadata"]["component"]
    assert "add_manufacturer" not in _stats(result)


@pytest.mark.parametrize("value", ["", "   "])
def test_empty_manufacturer_value_is_rejected(value):
    with pytest.raises(ValidationError):
        SbomFixOptions(manufacturer=value)


def test_remove_fields_runs_before_add_manufacturer_and_appears_in_stats():
    data = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.7",
        "version": 1,
        "metadata": {
            "component": {"type": "application", "name": "app", "version": "1.0"}
        },
        "components": [
            {
                "type": "library",
                "name": "openssl",
                "version": "3.0",
                "purl": "pkg:generic/openssl@3.0",
                "scope": "required",
            }
        ],
        "dependencies": [{"ref": "openssl"}],
    }
    result = fix_sbom(
        data,
        SbomFixOptions(),
        remove_fields=["root.dependencies", "components[].scope"],
    )
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
        "bomFormat": "CycloneDX",
        "specVersion": "1.7",
        "version": 1,
        "components": [
            {
                "type": "library",
                "name": "openssl",
                "version": "3.0",
                "purl": "pkg:generic/openssl@3.0",
                "bom-ref": "openssl",
            }
        ],
    }
    result = fix_sbom(data, SbomFixOptions(), remove_fields=["components[].bom-ref"])
    assert result.fixed_sbom["components"][0]["bom-ref"] == "openssl"
    assert not [s for s in result.stats if s.rule_id == "optional_fields.remove"]


def test_removing_keep_listed_path_is_ignored():
    data = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.7",
        "version": 1,
        "components": [
            {"type": "library", "name": "a", "version": "1.0", "description": "x"}
        ],
    }
    options = SbomFixOptions(optional_fields={"keep": ["components[].description"]})
    result = fix_sbom(data, options, remove_fields=["components[].description"])
    assert result.fixed_sbom["components"][0]["description"] == "x"
    assert not [s for s in result.stats if s.rule_id == "optional_fields.remove"]


def test_removal_stats_include_zero_counts_and_canonical_order():
    data = {"bomFormat": "CycloneDX", "specVersion": "1.7"}
    result = fix_sbom(
        data,
        SbomFixOptions(),
        remove_fields=["components[].scope", "root.dependencies", "components[].hashes"],
    )
    removal_stats = [s for s in result.stats if s.rule_id == "optional_fields.remove"]
    assert [(s.field, s.count) for s in removal_stats] == [
        ("root.dependencies", 0),
        ("components[].hashes", 0),
        ("components[].scope", 0),
    ]
    assert result.changed is False


def test_removing_licenses_can_surface_missing_source_reference():
    data = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.7",
        "version": 1,
        "components": [
            {
                "type": "library",
                "name": "proprietary",
                "version": "1.0",
                "purl": "pkg:generic/proprietary@1.0",
                "licenses": [{"license": {"name": "Proprietary"}}],
            }
        ],
    }
    options = SbomFixOptions(
        optional_fields={
            "keep": [p for p in DEFAULT_KEEP_FIELDS if p != "components[].licenses"]
        }
    )
    result = fix_sbom(data, options, remove_fields=["components[].licenses"])
    codes = [issue.code for issue in result.issues]
    assert "component.missing_source_reference" in codes


def test_ignored_remove_fields_are_absent_from_stats():
    data = {"bomFormat": "CycloneDX", "specVersion": "1.7", "version": 1}
    result = fix_sbom(
        data,
        SbomFixOptions(),
        remove_fields=["bad", "root.specVersion", "", "bad"],
    )
    assert not [s for s in result.stats if s.rule_id == "optional_fields.remove"]


def test_reorder_returns_new_dict_and_changed_flag():
    data = {"b": 1, "a": 2}
    ordered, changed = _reorder(data, ("a",))
    assert list(ordered) == ["a", "b"]
    assert changed is True
    assert list(data) == ["b", "a"]

    unchanged, flag = _reorder({"a": 1, "b": 2}, ("a",))
    assert list(unchanged) == ["a", "b"]
    assert flag is False


def test_root_reorder_puts_schema_last():
    data = {
        "$schema": "x", "components": [], "version": 1,
        "serialNumber": "urn:uuid:1", "specVersion": "1.7",
        "bomFormat": "CycloneDX", "annotations": [],
    }
    result = fix_sbom(data, SbomFixOptions())
    assert list(result.fixed_sbom) == [
        "bomFormat", "specVersion", "serialNumber", "version",
        "components", "annotations", "$schema",
    ]
    assert _stats(result)["reorder"] == 1


def test_root_reorder_skips_missing_keys_and_preserves_other_relative_order():
    data = {
        "$schema": "x",
        "extra_b": 2,
        "components": [],
        "extra_a": 1,
        "bomFormat": "CycloneDX",
    }
    result = fix_sbom(data, SbomFixOptions(set_spec_version=False))
    assert list(result.fixed_sbom) == [
        "bomFormat", "components", "$schema", "extra_b", "extra_a",
    ]
    assert result.stats[0].count == 1


def test_metadata_reorder_puts_timestamp_and_component_first():
    data = {
        "bomFormat": "CycloneDX",
        "metadata": {
            "authors": [],
            "component": {"name": "x"},
            "manufacture": {},
            "timestamp": "2020-01-01T00:00:00Z",
        },
    }
    result = fix_sbom(data, _reorder_only_options())
    assert list(result.fixed_sbom["metadata"]) == [
        "timestamp", "component", "authors", "manufacture",
    ]
    stats = {stat.rule_id: stat.count for stat in result.stats}
    assert stats["reorder"] == 1


def test_metadata_component_reorder_puts_canonical_fields_first():
    data = {
        "bomFormat": "CycloneDX",
        "metadata": {
            "timestamp": "2020-01-01T00:00:00Z",
            "component": {
                "bom-ref": "pkg:x",
                "manufacturer": {"name": "m"},
                "version": "1.0",
                "name": "x",
                "type": "library",
            },
        },
    }
    result = fix_sbom(data, _reorder_only_options())
    assert list(result.fixed_sbom["metadata"]["component"]) == [
        "type", "name", "version", "manufacturer", "bom-ref",
    ]
    stats = {stat.rule_id: stat.count for stat in result.stats}
    assert stats["reorder"] == 1


def test_components_reorder_is_recursive_and_counts_each_changed_component():
    data = {
        "components": [
            {"version": "1.0", "name": "a", "type": "library"},
            {"type": "library", "name": "b"},
            {
                "type": "library",
                "name": "c",
                "components": [
                    {"purl": "pkg:x/y@1", "name": "d", "type": "library"},
                ],
                "z_extra": 1,
                "a_extra": 2,
            },
        ]
    }
    result = fix_sbom(data, _reorder_only_options())
    components = result.fixed_sbom["components"]
    assert list(components[0]) == ["type", "name", "version"]
    assert list(components[1]) == ["type", "name"]
    assert list(components[2]) == [
        "type", "name", "components", "z_extra", "a_extra",
    ]
    assert list(components[2]["components"][0]) == ["type", "name", "purl"]
    stats = {stat.rule_id: stat.count for stat in result.stats}
    assert stats["reorder"] == 2


def test_components_reorder_does_not_enter_metadata_component_components():
    data = {
        "metadata": {
            "component": {
                "type": "library",
                "name": "root",
                "components": [{"name": "nested", "type": "library"}],
            }
        },
        "components": [{"type": "library", "name": "a"}],
    }
    result = fix_sbom(data, _reorder_only_options())
    nested = result.fixed_sbom["metadata"]["component"]["components"][0]
    assert list(nested) == ["name", "type"]
    stats = {stat.rule_id: stat.count for stat in result.stats}
    assert stats["reorder"] == 0


def test_merged_reorder_counts_only_changed_objects():
    data = {
        "components": [{"version": "1", "name": "a", "type": "library"}],
        "metadata": {
            "component": {"name": "root", "type": "application"},
            "timestamp": "2020-01-01T00:00:00Z",
        },
        "specVersion": "1.7",
        "bomFormat": "CycloneDX",
    }
    options = SbomFixOptions(
        reorder=True,
        set_spec_version=False,
        increment_version=False,
        add_timestamp=False,
        add_manufacturer=False,
    )
    result = fix_sbom(data, options)
    assert list(result.fixed_sbom) == ["bomFormat", "specVersion", "metadata", "components"]
    assert list(result.fixed_sbom["metadata"]) == ["timestamp", "component"]
    assert list(result.fixed_sbom["metadata"]["component"]) == ["type", "name"]
    assert list(result.fixed_sbom["components"][0]) == ["type", "name", "version"]
    assert _stats(result)["reorder"] == 4


def test_disabled_reorder_changes_nothing_and_is_absent_from_stats():
    data = {
        "$schema": "x",
        "bomFormat": "CycloneDX",
        "specVersion": "1.7",
        "metadata": {
            "timestamp": "2020-01-01T00:00:00Z",
            "component": {"name": "m", "type": "library"},
        },
        "components": [{"version": "1", "name": "a", "type": "library"}],
    }
    options = SbomFixOptions(
        reorder=False,
        set_spec_version=False,
        increment_version=False,
        add_timestamp=False,
        add_manufacturer=False,
    )
    result = fix_sbom(data, options)
    assert list(result.fixed_sbom) == [
        "$schema", "bomFormat", "specVersion", "metadata", "components",
    ]
    assert list(result.fixed_sbom["metadata"]) == ["timestamp", "component"]
    assert list(result.fixed_sbom["metadata"]["component"]) == ["name", "type"]
    assert list(result.fixed_sbom["components"][0]) == [
        "version", "name", "type",
    ]
    rule_ids = {stat.rule_id for stat in result.stats}
    assert "reorder" not in rule_ids
    assert all(stat.count == 0 for stat in result.stats)


def _stats(result):
    return {stat.rule_id: stat.count for stat in result.stats}


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


def test_set_spec_version_replaces_value_and_counts_one():
    data = {"bomFormat": "CycloneDX", "specVersion": "1.6"}
    result = fix_sbom(data, SbomFixOptions(spec_version="1.7"))
    assert result.fixed_sbom["specVersion"] == "1.7"
    assert _stats(result)["set_spec_version"] == 1
    assert result.changed is True


def test_set_spec_version_adds_missing_key_and_counts_one():
    data = {"bomFormat": "CycloneDX"}
    result = fix_sbom(data, SbomFixOptions(spec_version="1.6"))
    assert result.fixed_sbom["specVersion"] == "1.6"
    assert _stats(result)["set_spec_version"] == 1


def test_set_spec_version_same_value_counts_zero():
    data = {"bomFormat": "CycloneDX", "specVersion": "1.7"}
    result = fix_sbom(data, SbomFixOptions(spec_version="1.7"))
    assert result.fixed_sbom == data
    assert _stats(result)["set_spec_version"] == 0


def test_set_spec_version_strips_configured_value():
    options = SbomFixOptions()
    options.spec_version = " 1.7 "
    data = {"bomFormat": "CycloneDX", "specVersion": "1.6"}
    result = fix_sbom(data, options)
    assert result.fixed_sbom["specVersion"] == "1.7"
    assert _stats(result)["set_spec_version"] == 1


@pytest.mark.parametrize("value", [0, 1, -3])
def test_increment_version_increments_integers(value):
    data = {"bomFormat": "CycloneDX", "specVersion": "1.7", "version": value}
    result = fix_sbom(data, SbomFixOptions())
    assert result.fixed_sbom["version"] == value + 1
    assert _stats(result)["increment_version"] == 1


@pytest.mark.parametrize("value", ["1", 1.5, True, False, None])
def test_increment_version_leaves_missing_or_non_int_unchanged(value):
    data = {"bomFormat": "CycloneDX", "specVersion": "1.7", "version": value}
    result = fix_sbom(data, SbomFixOptions())
    assert result.fixed_sbom["version"] == value
    assert _stats(result)["increment_version"] == 0


def test_increment_version_absent_counts_zero_and_does_not_add_key():
    data = {"bomFormat": "CycloneDX", "specVersion": "1.7"}
    result = fix_sbom(data, SbomFixOptions())
    assert "version" not in result.fixed_sbom
    assert _stats(result)["increment_version"] == 0


def test_disabled_root_rules_leave_fields_untouched_and_are_absent_from_stats():
    data = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "dependencies": [],
        "services": [],
    }
    options = SbomFixOptions(
        set_spec_version=False,
        increment_version=False,
    )
    result = fix_sbom(data, options)
    assert result.fixed_sbom == data
    rule_ids = {stat.rule_id for stat in result.stats}
    assert "set_spec_version" not in rule_ids
    assert "increment_version" not in rule_ids
    assert result.changed is False


def test_added_spec_version_goes_last_when_root_reorder_disabled():
    data = {"bomFormat": "CycloneDX", "version": 5}
    options = SbomFixOptions(reorder=False)
    result = fix_sbom(data, options)
    assert list(result.fixed_sbom) == ["bomFormat", "version", "specVersion"]
    stats = _stats(result)
    assert stats["set_spec_version"] == 1
    assert stats["increment_version"] == 1
    assert "reorder" not in stats
    assert result.changed is True


def test_any_root_rule_with_positive_count_sets_changed():
    options = SbomFixOptions(
        set_spec_version=False,
    )
    data = {"bomFormat": "CycloneDX", "specVersion": "1.7", "version": 1}
    result = fix_sbom(data, options)
    assert _stats(result)["increment_version"] == 1
    assert result.changed is True


NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
NOW_TEXT = "2026-01-02T03:04:05Z"


@pytest.mark.parametrize(
    "metadata",
    [{}, {"timestamp": None}, {"timestamp": ""}],
    ids=["missing", "null", "empty-string"],
)
def test_add_timestamp_sets_now_when_absent_null_or_empty(metadata):
    data = {"bomFormat": "CycloneDX", "specVersion": "1.7", "metadata": metadata}
    result = fix_sbom(data, SbomFixOptions(), now=NOW)
    assert result.fixed_sbom["metadata"]["timestamp"] == NOW_TEXT
    assert _stats(result)["add_timestamp"] == 1
    assert result.changed is True


@pytest.mark.parametrize(
    "value",
    ["2020-01-01T00:00:00Z", "not-a-date", 5, 0, False, {}, []],
    ids=["valid", "invalid-format", "int", "zero", "bool", "dict", "list"],
)
def test_add_timestamp_never_overwrites_existing_non_empty_value(value):
    data = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.7",
        "metadata": {"timestamp": value},
    }
    result = fix_sbom(data, SbomFixOptions(), now=NOW)
    assert result.fixed_sbom["metadata"]["timestamp"] == value
    assert _stats(result)["add_timestamp"] == 0


def test_add_timestamp_does_nothing_without_metadata():
    data = {"bomFormat": "CycloneDX", "specVersion": "1.7"}
    result = fix_sbom(data, SbomFixOptions(), now=NOW)
    assert "metadata" not in result.fixed_sbom
    assert _stats(result)["add_timestamp"] == 0
    assert result.changed is False


def test_add_timestamp_treats_naive_now_as_utc():
    data = {"bomFormat": "CycloneDX", "specVersion": "1.7", "metadata": {}}
    result = fix_sbom(
        data, SbomFixOptions(), now=datetime(2026, 1, 2, 3, 4, 5)
    )
    assert result.fixed_sbom["metadata"]["timestamp"] == NOW_TEXT


def test_add_timestamp_converts_aware_now_to_utc():
    data = {"bomFormat": "CycloneDX", "specVersion": "1.7", "metadata": {}}
    result = fix_sbom(
        data,
        SbomFixOptions(),
        now=datetime(2026, 1, 2, 6, 4, 5, tzinfo=timezone(timedelta(hours=3))),
    )
    assert result.fixed_sbom["metadata"]["timestamp"] == NOW_TEXT


def test_add_timestamp_is_idempotent_with_same_now():
    data = {"bomFormat": "CycloneDX", "specVersion": "1.7", "metadata": {}}
    first = fix_sbom(data, SbomFixOptions(), now=NOW)
    second = fix_sbom(first.fixed_sbom, SbomFixOptions(), now=NOW)
    assert second.fixed_sbom["metadata"]["timestamp"] == NOW_TEXT
    assert _stats(second)["add_timestamp"] == 0
    assert second.changed is False


@pytest.mark.parametrize(
    ("path", "key"),
    [
        ("metadata.properties", "properties"),
        ("metadata.tools", "tools"),
        ("metadata.component.externalReferences", "externalReferences"),
    ],
)
def test_metadata_removal_via_remove_fields_counts_one(path, key):
    data = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.7",
        "metadata": {
            "timestamp": NOW_TEXT,
            "properties": [{"name": "x"}],
            "tools": [],
            "component": {
                "type": "application",
                "name": "root",
                "externalReferences": [{"type": "vcs"}],
            },
        },
    }
    options = SbomFixOptions(optional_fields={"keep": []})
    result = fix_sbom(data, options, now=NOW, remove_fields=[path])
    target = result.fixed_sbom["metadata"]
    if path.startswith("metadata.component."):
        target = target["component"]
    assert key not in target
    removal_stats = [s for s in result.stats if s.rule_id == "optional_fields.remove"]
    assert [(s.field, s.count) for s in removal_stats] == [(path, 1)]
    assert result.changed is True


@pytest.mark.parametrize(
    "metadata",
    [{}, {"timestamp": NOW_TEXT}, {"timestamp": NOW_TEXT, "component": None}],
    ids=["no-component", "no-component-key", "null-component"],
)
def test_metadata_component_add_manufacturer_skips_when_component_missing_or_null(
    metadata,
):
    data = {"bomFormat": "CycloneDX", "specVersion": "1.7", "metadata": metadata}
    options = SbomFixOptions(add_timestamp=False)
    result = fix_sbom(data, options, now=NOW)
    assert result.fixed_sbom["metadata"] == metadata
    assert _stats(result)["add_manufacturer"] == 0


@pytest.mark.parametrize("metadata", [None, [], "text"], ids=["null", "list", "string"])
def test_metadata_rules_skip_when_metadata_is_not_object(metadata):
    data = {"bomFormat": "CycloneDX", "specVersion": "1.7", "metadata": metadata}
    result = fix_sbom(data, SbomFixOptions(), now=NOW)
    assert result.fixed_sbom["metadata"] == metadata
    stats = _stats(result)
    assert stats["add_timestamp"] == 0
    assert stats["add_manufacturer"] == 0


def test_disabled_metadata_rules_leave_fields_untouched_and_are_absent_from_stats():
    data = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.7",
        "metadata": {
            "properties": [{"name": "x"}],
            "tools": [],
            "component": {
                "type": "application",
                "name": "root",
                "purl": "pkg:x/y@1",
                "scope": "required",
                "supplier": {"name": "Vendor"},
            },
        },
    }
    options = SbomFixOptions(
        reorder=False,
        add_timestamp=False,
        add_manufacturer=False,
    )
    result = fix_sbom(data, options, now=NOW)
    assert result.fixed_sbom == data
    rule_ids = {stat.rule_id for stat in result.stats}
    assert "reorder" not in rule_ids
    assert "add_timestamp" not in rule_ids
    assert "add_manufacturer" not in rule_ids
    assert result.changed is False


def test_timestamp_and_manufacturer_are_first_and_fourth_after_all_rules():
    data = {
        "bomFormat": "CycloneDX", "specVersion": "1.6", "version": 1,
        "metadata": {
            "supplier": {"name": "Vendor"},
            "component": {"supplier": {"name": "Vendor"}, "version": "1",
                          "name": "root", "type": "application", "group": "g"},
        },
    }
    result = fix_sbom(
        data,
        SbomFixOptions(),
        now=datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
    )
    assert list(result.fixed_sbom["metadata"])[:2] == ["timestamp", "component"]
    assert list(result.fixed_sbom["metadata"]["component"])[:4] == [
        "type", "name", "version", "manufacturer",
    ]
    assert result.fixed_sbom["metadata"]["component"]["group"] == "g"


def test_walk_components_visits_pre_order_and_skips_metadata_and_non_objects():
    visited = []
    root = {
        "components": [
            {
                "name": "a",
                "components": [
                    {"name": "b", "components": [{"name": "c"}]},
                ],
            },
            {"name": "d"},
            "not-an-object",
            {"name": "e", "components": "not-a-list"},
        ],
        "metadata": {
            "component": {
                "name": "root",
                "components": [{"name": "hidden"}],
            }
        },
    }
    _walk_components(root, lambda component: visited.append(component["name"]))
    assert visited == ["a", "b", "c", "d", "e"]


def test_walk_components_without_components_array_does_nothing():
    visited = []
    _walk_components({}, lambda component: visited.append(component))
    _walk_components({"components": None}, lambda component: visited.append(component))
    _walk_components({"components": {}}, lambda component: visited.append(component))
    assert visited == []


def test_remove_fields_removes_direct_key_only_and_keeps_nested_containers():
    data = {
        "components": [
            {
                "type": "library",
                "name": "a",
                "hashes": [{"alg": "SHA-256", "content": "x"}],
                "externalReferences": [
                    {
                        "type": "vcs",
                        "url": "https://example.com/repo",
                        "hashes": [{"alg": "SHA-1", "content": "keep"}],
                    }
                ],
                "components": [{"name": "b", "hashes": "unexpected-type"}],
            }
        ]
    }
    result = fix_sbom(
        data,
        SbomFixOptions(optional_fields={"keep": []}),
        remove_fields=["components[].hashes"],
    )
    component = result.fixed_sbom["components"][0]
    assert "hashes" not in component
    assert component["externalReferences"][0]["hashes"] == [
        {"alg": "SHA-1", "content": "keep"}
    ]
    assert "hashes" not in component["components"][0]
    removal_stats = [s for s in result.stats if s.rule_id == "optional_fields.remove"]
    assert [(s.field, s.count) for s in removal_stats] == [
        ("components[].hashes", 2)
    ]


def test_remove_fields_removes_key_on_all_component_levels():
    data = {
        "components": [
            {
                "name": "a",
                "scope": "required",
                "components": [
                    {
                        "name": "b",
                        "scope": "optional",
                        "components": [{"name": "c", "scope": "excluded"}],
                    }
                ],
            }
        ]
    }
    result = fix_sbom(
        data,
        SbomFixOptions(optional_fields={"keep": []}),
        remove_fields=["components[].scope"],
    )
    component = result.fixed_sbom["components"][0]
    assert "scope" not in component
    assert "scope" not in component["components"][0]
    assert "scope" not in component["components"][0]["components"][0]
    removal_stats = [s for s in result.stats if s.rule_id == "optional_fields.remove"]
    assert [(s.field, s.count) for s in removal_stats] == [
        ("components[].scope", 3)
    ]


def test_filter_external_references_keeps_only_allowed_types():
    refs = [
        {"type": "vcs", "url": "https://a"},
        {"type": "source-distribution", "url": "https://b"},
        {"type": "website", "url": "https://c"},
        {"url": "https://no-type"},
        "not-an-object",
        None,
        {"type": "VCS", "url": "https://upper"},
    ]
    kept, removed = _filter_external_references(refs)
    assert kept == [
        {"type": "vcs", "url": "https://a"},
        {"type": "source-distribution", "url": "https://b"},
    ]
    assert removed == 5


def test_filter_external_references_preserves_empty_list():
    kept, removed = _filter_external_references([])
    assert kept == []
    assert removed == 0


def test_filter_external_references_keeps_empty_array_in_component():
    data = {"components": [{"name": "a", "externalReferences": []}]}
    result = fix_sbom(data, SbomFixOptions())
    assert result.fixed_sbom["components"][0]["externalReferences"] == []
    assert _stats(result)["components.filter_external_references"] == 0


def test_filter_external_references_counts_removed_elements_across_tree():
    data = {
        "components": [
            {
                "name": "a",
                "externalReferences": [
                    {"type": "vcs"},
                    {"type": "website"},
                ],
            },
            {
                "name": "b",
                "externalReferences": [
                    {"type": "source-distribution"},
                    {"type": "other"},
                    {"type": "docs"},
                ],
            },
        ]
    }
    result = fix_sbom(data, SbomFixOptions())
    assert _stats(result)["components.filter_external_references"] == 3
    assert result.fixed_sbom["components"][0]["externalReferences"] == [
        {"type": "vcs"}
    ]
    assert result.fixed_sbom["components"][1]["externalReferences"] == [
        {"type": "source-distribution"}
    ]


def test_filter_properties_keeps_only_gost_named_properties():
    props = [
        {"name": "GOST:attack_surface", "value": "no"},
        {"name": "GOST:", "value": "x"},
        {"name": "gost:attack_surface", "value": "no"},
        {"name": "", "value": "empty"},
        {"value": "no-name"},
        {"name": 5, "value": "non-string"},
        "not-an-object",
    ]
    kept, removed = _filter_properties(props)
    assert kept == [
        {"name": "GOST:attack_surface", "value": "no"},
        {"name": "GOST:", "value": "x"},
    ]
    assert removed == 5


def test_filter_properties_preserves_empty_list():
    kept, removed = _filter_properties([])
    assert kept == []
    assert removed == 0


def test_filter_properties_keeps_empty_array_in_component():
    data = {"components": [{"name": "a", "properties": []}]}
    result = fix_sbom(data, SbomFixOptions())
    assert result.fixed_sbom["components"][0]["properties"] == []
    assert _stats(result)["components.filter_properties"] == 0


def test_filter_properties_counts_removed_elements_across_tree():
    data = {
        "components": [
            {
                "name": "a",
                "properties": [
                    {"name": "GOST:attack_surface", "value": "no"},
                    {"name": "custom", "value": "1"},
                ],
            },
            {
                "name": "b",
                "properties": [
                    {"name": "GOST:security_function", "value": "no"},
                    {"value": "no-name"},
                ],
                "components": [
                    {"name": "c", "properties": [{"name": "other"}]},
                ],
            },
        ]
    }
    result = fix_sbom(data, SbomFixOptions())
    assert _stats(result)["components.filter_properties"] == 3


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


def test_fill_gost_properties_creates_list_when_absent():
    component = {"name": "a"}
    assert _fill_gost_properties(component) == 2
    assert component["properties"] == [
        {"name": "GOST:attack_surface", "value": "no"},
        {"name": "GOST:security_function", "value": "no"},
    ]


def test_fill_gost_properties_creates_list_when_null():
    component = {"name": "a", "properties": None}
    assert _fill_gost_properties(component) == 2
    assert component["properties"] == [
        {"name": "GOST:attack_surface", "value": "no"},
        {"name": "GOST:security_function", "value": "no"},
    ]


def test_fill_gost_properties_adds_only_missing_and_preserves_values():
    component = {
        "properties": [{"name": "GOST:attack_surface", "value": "custom"}]
    }
    assert _fill_gost_properties(component) == 1
    assert component["properties"] == [
        {"name": "GOST:attack_surface", "value": "custom"},
        {"name": "GOST:security_function", "value": "no"},
    ]


def test_fill_gost_properties_adds_nothing_when_both_present():
    component = {
        "properties": [
            {"name": "GOST:attack_surface", "value": "external"},
            {"name": "GOST:security_function", "value": "internal"},
        ]
    }
    assert _fill_gost_properties(component) == 0
    assert component["properties"] == [
        {"name": "GOST:attack_surface", "value": "external"},
        {"name": "GOST:security_function", "value": "internal"},
    ]


def test_fill_gost_properties_skips_non_list():
    component = {"properties": {"name": "GOST:attack_surface", "value": "no"}}
    assert _fill_gost_properties(component) == 0
    assert component["properties"] == {
        "name": "GOST:attack_surface",
        "value": "no",
    }


def test_fill_gost_properties_ignores_non_object_entries():
    component = {"properties": ["not-an-object", {"name": "GOST:attack_surface"}]}
    assert _fill_gost_properties(component) == 1
    assert component["properties"] == [
        "not-an-object",
        {"name": "GOST:attack_surface"},
        {"name": "GOST:security_function", "value": "no"},
    ]


def test_filter_properties_runs_before_fill_gost_properties():
    data = {
        "components": [
            {
                "name": "a",
                "properties": [
                    {"name": "custom", "value": "1"},
                    {"name": "GOST:attack_surface", "value": "custom"},
                ],
            }
        ]
    }
    options = SbomFixOptions(components={"fill_missing_gost_properties": True})
    result = fix_sbom(data, options)
    assert result.fixed_sbom["components"][0]["properties"] == [
        {"name": "GOST:attack_surface", "value": "custom"},
        {"name": "GOST:security_function", "value": "no"},
    ]
    stats = _stats(result)
    assert stats["components.filter_properties"] == 1
    assert stats["components.fill_missing_gost_properties"] == 1


def test_fill_gost_properties_does_not_apply_to_metadata_component():
    data = {
        "metadata": {"component": {"type": "application", "name": "root"}},
        "components": [{"name": "a"}],
    }
    options = SbomFixOptions(components={"fill_missing_gost_properties": True})
    result = fix_sbom(data, options)
    assert "properties" not in result.fixed_sbom["metadata"]["component"]
    assert result.fixed_sbom["components"][0]["properties"] == [
        {"name": "GOST:attack_surface", "value": "no"},
        {"name": "GOST:security_function", "value": "no"},
    ]
    assert _stats(result)["components.fill_missing_gost_properties"] == 2


def test_unexpected_types_do_not_raise_and_non_objects_are_preserved():
    data = {
        "components": [
            {
                "name": "a",
                "properties": "not-a-list",
                "externalReferences": {},
                "components": "not-a-list",
            },
            "not-an-object",
            {
                "name": "b",
                "properties": [{"name": None}, "not-an-object"],
                "externalReferences": ["not-an-object", {"type": "website"}],
            },
        ]
    }
    options = SbomFixOptions(components={"fill_missing_gost_properties": True})
    result = fix_sbom(data, options)
    first = result.fixed_sbom["components"][0]
    assert first["properties"] == "not-a-list"
    assert first["externalReferences"] == {}
    assert first["components"] == "not-a-list"
    assert result.fixed_sbom["components"][1] == "not-an-object"
    second = result.fixed_sbom["components"][2]
    assert second["externalReferences"] == []
    assert second["properties"] == [
        {"name": "GOST:attack_surface", "value": "no"},
        {"name": "GOST:security_function", "value": "no"},
    ]


def test_fix_sbom_does_not_mutate_input_including_external_reference_hashes():
    data = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "name": "root",
                "properties": [{"name": "x"}],
            }
        },
        "components": [
            {
                "type": "library",
                "name": "a",
                "scope": "required",
                "hashes": [{"alg": "SHA-256", "content": "h"}],
                "properties": [{"name": "custom", "value": "1"}],
                "externalReferences": [
                    {
                        "type": "vcs",
                        "url": "https://example.com/repo",
                        "hashes": [{"alg": "SHA-1", "content": "keep"}],
                    },
                    {"type": "website", "url": "https://example.com"},
                ],
                "components": [
                    {
                        "name": "b",
                        "hashes": {"unexpected": True},
                        "scope": "optional",
                    }
                ],
            }
        ],
    }
    snapshot = copy.deepcopy(data)
    options = SbomFixOptions(components={"fill_missing_gost_properties": True})
    fix_sbom(data, options, now=NOW)
    assert data == snapshot
    assert data["components"][0]["externalReferences"][0]["hashes"] == [
        {"alg": "SHA-1", "content": "keep"}
    ]


def test_disabled_components_rules_leave_fields_untouched():
    data = {
        "components": [
            {
                "name": "a",
                "scope": "required",
                "hashes": [{"alg": "SHA-256", "content": "h"}],
                "properties": [{"name": "custom", "value": "1"}],
                "externalReferences": [{"type": "website"}],
            }
        ]
    }
    options = SbomFixOptions(
        reorder=False,
        set_spec_version=False,
        add_timestamp=False,
        add_manufacturer=False,
        components={
            "filter_external_references": False,
            "filter_properties": False,
            "fill_missing_gost_properties": False,
        },
    )
    result = fix_sbom(data, options)
    assert result.fixed_sbom == data
    assert result.changed is False
    assert all(stat.count == 0 for stat in result.stats)


_ABSENT = object()


def _valid_component(**overrides):
    component = {
        "type": "library",
        "name": "pkg",
        "version": "1.0.0",
        "purl": "pkg:generic/pkg@1.0.0",
        "properties": [
            {"name": "GOST:attack_surface", "value": "no"},
            {"name": "GOST:security_function", "value": "no"},
        ],
        "externalReferences": [{"type": "vcs", "url": "https://example.com/repo"}],
    }
    component.update(overrides)
    return component


def _issue_codes(issues):
    return [(issue.code, issue.path, issue.component) for issue in issues]


def test_collect_component_issues_reports_missing_fields():
    issues: list[FixIssue] = []
    _collect_component_issues([{"type": "library"}], "$.components", issues)
    assert [(i.code, i.path, i.component) for i in issues] == [
        ("component.missing_name", "$.components[0]", None),
        ("component.missing_version", "$.components[0]", None),
        ("component.missing_purl", "$.components[0]", None),
        ("component.missing_gost_properties", "$.components[0]", None),
        ("component.missing_source_reference", "$.components[0]", None),
    ]


def test_collect_component_issues_valid_component_has_no_issues():
    issues = []
    _collect_component_issues([_valid_component()], "$.components", issues)
    assert issues == []


def test_collect_component_issues_invalid_entry_is_reported_and_others_processed():
    issues = []
    _collect_component_issues(
        [None, _valid_component(), "not-an-object"], "$.components", issues
    )
    assert _issue_codes(issues) == [
        ("component.invalid_entry", "$.components[0]", None),
        ("component.invalid_entry", "$.components[2]", None),
    ]


@pytest.mark.parametrize(
    ("field", "code"),
    [
        ("type", "component.missing_type"),
        ("name", "component.missing_name"),
        ("version", "component.missing_version"),
        ("purl", "component.missing_purl"),
    ],
)
@pytest.mark.parametrize(
    "value",
    [
        pytest.param(_ABSENT, id="absent"),
        pytest.param(None, id="null"),
        pytest.param("", id="empty"),
        pytest.param(0, id="int"),
        pytest.param([], id="list"),
        pytest.param({}, id="dict"),
    ],
)
def test_collect_component_issues_missing_required_field(field, code, value):
    component = _valid_component()
    if value is _ABSENT:
        del component[field]
    else:
        component[field] = value
    name = component.get("name")
    expected_component = name if isinstance(name, str) and name else None
    issues = []
    _collect_component_issues([component], "$.components", issues)
    assert _issue_codes(issues) == [(code, "$.components[0]", expected_component)]


@pytest.mark.parametrize("value", [{}, "not-a-list", 42, True])
def test_collect_component_issues_invalid_properties_does_not_duplicate_gost(value):
    issues = []
    _collect_component_issues(
        [_valid_component(properties=value)], "$.components", issues
    )
    assert _issue_codes(issues) == [
        ("component.invalid_properties", "$.components[0]", "pkg")
    ]


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(_ABSENT, id="absent"),
        pytest.param(None, id="null"),
        pytest.param([], id="empty"),
    ],
)
def test_collect_component_issues_missing_gost_properties(value):
    component = _valid_component()
    if value is _ABSENT:
        del component["properties"]
    else:
        component["properties"] = value
    issues = []
    _collect_component_issues([component], "$.components", issues)
    assert _issue_codes(issues) == [
        ("component.missing_gost_properties", "$.components[0]", "pkg")
    ]
    assert issues[0].details == {
        "missing": ["GOST:attack_surface", "GOST:security_function"]
    }


@pytest.mark.parametrize(
    ("properties", "missing"),
    [
        (
            [{"name": "GOST:attack_surface", "value": "no"}],
            ["GOST:security_function"],
        ),
        (
            [{"name": "GOST:security_function", "value": "no"}],
            ["GOST:attack_surface"],
        ),
        (
            [{"name": "custom"}, "not-an-object", {"name": 5}],
            ["GOST:attack_surface", "GOST:security_function"],
        ),
    ],
)
def test_collect_component_issues_reports_missing_gost_names(properties, missing):
    issues = []
    _collect_component_issues(
        [_valid_component(properties=properties)], "$.components", issues
    )
    assert _issue_codes(issues) == [
        ("component.missing_gost_properties", "$.components[0]", "pkg")
    ]
    assert issues[0].details == {"missing": missing}


def test_collect_component_issues_no_gost_issue_when_both_names_present():
    component = _valid_component(
        properties=[
            {"name": "GOST:security_function"},
            {"name": "GOST:attack_surface"},
        ]
    )
    issues = []
    _collect_component_issues([component], "$.components", issues)
    assert issues == []


@pytest.mark.parametrize("value", [{}, "not-a-list", 42, True])
def test_collect_component_issues_invalid_external_references_not_duplicated(value):
    issues = []
    _collect_component_issues(
        [_valid_component(externalReferences=value)], "$.components", issues
    )
    assert _issue_codes(issues) == [
        ("component.invalid_external_references", "$.components[0]", "pkg")
    ]


def test_collect_component_issues_invalid_fields_do_not_emit_missing_counterparts():
    component = _valid_component(properties={}, externalReferences="not-a-list")
    issues = []
    _collect_component_issues([component], "$.components", issues)
    assert _issue_codes(issues) == [
        ("component.invalid_properties", "$.components[0]", "pkg"),
        ("component.invalid_external_references", "$.components[0]", "pkg"),
    ]


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(_ABSENT, id="absent"),
        pytest.param(None, id="null"),
        pytest.param([], id="empty"),
        pytest.param([{"type": "website"}], id="wrong-type"),
        pytest.param([None, "not-an-object", {"type": 5}], id="invalid-entries"),
    ],
)
def test_collect_component_issues_missing_source_reference(value):
    component = _valid_component()
    if value is _ABSENT:
        del component["externalReferences"]
    else:
        component["externalReferences"] = value
    issues = []
    _collect_component_issues([component], "$.components", issues)
    assert _issue_codes(issues) == [
        ("component.missing_source_reference", "$.components[0]", "pkg")
    ]


@pytest.mark.parametrize(
    "references",
    [
        [{"type": "vcs"}],
        [{"type": "source-distribution"}],
        [{"type": "website"}, {"type": "vcs", "url": "https://example.com"}],
    ],
)
def test_collect_component_issues_source_reference_present(references):
    issues = []
    _collect_component_issues(
        [_valid_component(externalReferences=references)], "$.components", issues
    )
    assert issues == []


def test_collect_component_issues_non_empty_components_exempts_source_reference():
    parent = _valid_component(
        name="parent", components=[_valid_component(name="child")]
    )
    del parent["externalReferences"]
    issues = []
    _collect_component_issues([parent], "$.components", issues)
    assert issues == []


def test_collect_component_issues_empty_components_does_not_exempt_source_reference():
    component = _valid_component(components=[])
    del component["externalReferences"]
    issues = []
    _collect_component_issues([component], "$.components", issues)
    assert _issue_codes(issues) == [
        ("component.missing_source_reference", "$.components[0]", "pkg")
    ]


@pytest.mark.parametrize(
    ("value", "exempt"),
    [
        pytest.param(_ABSENT, False, id="absent"),
        ("certified", True),
        ("", False),
        (None, False),
        (5, False),
        (["certified"], False),
    ],
)
def test_collect_component_issues_provided_by_exception(value, exempt):
    properties = [{"name": "GOST:attack_surface"}, {"name": "GOST:security_function"}]
    if value is _ABSENT:
        properties.append({"name": "GOST:provided_by"})
    else:
        properties.append({"name": "GOST:provided_by", "value": value})
    component = _valid_component(properties=properties)
    del component["externalReferences"]
    issues = []
    _collect_component_issues([component], "$.components", issues)
    expected = (
        []
        if exempt
        else [("component.missing_source_reference", "$.components[0]", "pkg")]
    )
    assert _issue_codes(issues) == expected


@pytest.mark.parametrize(
    ("licenses", "exempt"),
    [
        pytest.param(_ABSENT, False, id="absent"),
        ([{"license": {"name": "Proprietary"}}], True),
        ([{"license": {"name": "MIT"}}], False),
        ([{"license": {"name": "proprietary"}}], False),
        ([{"name": "Proprietary"}], False),
        ([{"license": "Proprietary"}], False),
        ([{"license": None}], False),
        ("Proprietary", False),
        (None, False),
        ([], False),
    ],
)
def test_collect_component_issues_proprietary_license_exception(licenses, exempt):
    component = _valid_component()
    if licenses is not _ABSENT:
        component["licenses"] = licenses
    del component["externalReferences"]
    issues = []
    _collect_component_issues([component], "$.components", issues)
    expected = (
        []
        if exempt
        else [("component.missing_source_reference", "$.components[0]", "pkg")]
    )
    assert _issue_codes(issues) == expected


@pytest.mark.parametrize(
    "value",
    [
        "not-a-list",
        {"components": [_valid_component(name="hidden")]},
        42,
        True,
    ],
)
def test_collect_component_issues_invalid_subcomponents_does_not_recurse(value):
    issues = []
    _collect_component_issues(
        [_valid_component(components=value)], "$.components", issues
    )
    assert _issue_codes(issues) == [
        ("component.invalid_subcomponents", "$.components[0]", "pkg")
    ]


@pytest.mark.parametrize("value", [None, []])
def test_collect_component_issues_null_or_empty_subcomponents_not_reported(value):
    issues = []
    _collect_component_issues(
        [_valid_component(components=value)], "$.components", issues
    )
    assert issues == []


def test_collect_component_issues_code_order_within_component():
    component = {
        "properties": "not-a-list",
        "externalReferences": {},
        "components": "not-a-list",
    }
    issues = []
    _collect_component_issues([component], "$.components", issues)
    assert _issue_codes(issues) == [
        ("component.missing_type", "$.components[0]", None),
        ("component.missing_name", "$.components[0]", None),
        ("component.missing_version", "$.components[0]", None),
        ("component.missing_purl", "$.components[0]", None),
        ("component.invalid_properties", "$.components[0]", None),
        ("component.invalid_external_references", "$.components[0]", None),
        ("component.invalid_subcomponents", "$.components[0]", None),
    ]
    assert all(issue.details == {} for issue in issues)


def test_collect_component_issues_pre_order_and_nested_paths():
    a = _valid_component(name="a")
    del a["version"]
    b = _valid_component(name="b")
    del b["purl"]
    c = _valid_component(name="c")
    del c["type"]
    b["components"] = [c]
    a["components"] = [b]
    d = _valid_component(name="d")
    del d["name"]
    issues = []
    _collect_component_issues([a, d], "$.components", issues)
    assert _issue_codes(issues) == [
        ("component.missing_version", "$.components[0]", "a"),
        ("component.missing_purl", "$.components[0].components[0]", "b"),
        (
            "component.missing_type",
            "$.components[0].components[0].components[0]",
            "c",
        ),
        ("component.missing_name", "$.components[1]", None),
    ]


def test_collect_component_issues_unexpected_types_do_not_raise():
    entries = [
        None,
        42,
        "not-an-object",
        [],
        {},
        {
            "type": 5,
            "name": ["x"],
            "version": {},
            "purl": 1,
            "properties": 5,
            "externalReferences": 5,
            "components": 5,
            "licenses": 5,
        },
        {
            "type": "library",
            "name": "weird",
            "version": "1",
            "purl": "pkg:generic/weird@1",
            "properties": [
                None,
                1,
                "not-an-object",
                {"name": 5},
                {"name": "GOST:provided_by", "value": 5},
            ],
            "externalReferences": [None, 1, {"type": 5}],
            "licenses": 5,
        },
    ]
    issues: list[FixIssue] = []
    _collect_component_issues(entries, "$.components", issues)
    assert [issue.code for issue in issues[:4]] == ["component.invalid_entry"] * 4
    assert [issue.path for issue in issues[:4]] == [
        "$.components[0]",
        "$.components[1]",
        "$.components[2]",
        "$.components[3]",
    ]
    assert all(issue.component is None for issue in issues[:4])


def test_collect_component_issues_ignores_non_list_input():
    issues: list[FixIssue] = []
    _collect_component_issues({}, "$.components", issues)
    _collect_component_issues(None, "$.components", issues)
    _collect_component_issues("not-a-list", "$.components", issues)
    assert issues == []


def _all_disabled_options():
    return SbomFixOptions(
        reorder=False,
        set_spec_version=False,
        increment_version=False,
        add_timestamp=False,
        add_manufacturer=False,
        components={
            "filter_external_references": False,
            "filter_properties": False,
            "fill_missing_gost_properties": False,
        },
    )


def _valid_metadata_component():
    return {
        "type": "application",
        "name": "app",
        "version": "1.0.0",
        "manufacturer": {"name": "Acme"},
    }


def _valid_metadata():
    return {
        "timestamp": "2026-01-01T00:00:00Z",
        "component": _valid_metadata_component(),
    }


def _valid_sbom():
    return {
        "specVersion": "1.7",
        "version": 1,
        "metadata": _valid_metadata(),
    }


def _fix_sbom_issues(data):
    return fix_sbom(data, _all_disabled_options()).issues


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        pytest.param(_ABSENT, "root.missing_spec_version", id="absent"),
        pytest.param(None, "root.missing_spec_version", id="null"),
        pytest.param("", "root.missing_spec_version", id="empty"),
        pytest.param(1.7, "root.invalid_spec_version", id="float"),
        pytest.param(0, "root.invalid_spec_version", id="int"),
        pytest.param(True, "root.invalid_spec_version", id="bool"),
        pytest.param([], "root.invalid_spec_version", id="list"),
        pytest.param({}, "root.invalid_spec_version", id="dict"),
        pytest.param("1.5", "root.spec_version_not_allowed", id="not-allowed"),
        pytest.param("2.0", "root.spec_version_not_allowed", id="unknown"),
        pytest.param("1.7.0", "root.spec_version_not_allowed", id="patch"),
    ],
)
def test_issue_root_spec_version_is_one_mutually_exclusive_code(value, expected):
    data = _valid_sbom()
    if value is _ABSENT:
        del data["specVersion"]
    else:
        data["specVersion"] = value
    assert _issue_codes(_fix_sbom_issues(data)) == [(expected, "$", None)]


@pytest.mark.parametrize("value", ["1.6", "1.7"])
def test_issue_root_allowed_spec_version_has_no_issue(value):
    data = _valid_sbom()
    data["specVersion"] = value
    assert _fix_sbom_issues(data) == []


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        pytest.param(_ABSENT, "root.missing_version", id="absent"),
        pytest.param(None, "root.missing_version", id="null"),
        pytest.param("1", "root.invalid_version", id="string"),
        pytest.param("", "root.invalid_version", id="empty"),
        pytest.param(True, "root.invalid_version", id="bool-true"),
        pytest.param(False, "root.invalid_version", id="bool-false"),
        pytest.param(1.5, "root.invalid_version", id="float"),
        pytest.param([], "root.invalid_version", id="list"),
        pytest.param({}, "root.invalid_version", id="dict"),
    ],
)
def test_issue_root_version(value, expected):
    data = _valid_sbom()
    if value is _ABSENT:
        del data["version"]
    else:
        data["version"] = value
    assert _issue_codes(_fix_sbom_issues(data)) == [(expected, "$", None)]


@pytest.mark.parametrize("value", [0, 1, -5])
def test_issue_root_integer_version_has_no_issue(value):
    data = _valid_sbom()
    data["version"] = value
    assert _fix_sbom_issues(data) == []


@pytest.mark.parametrize("value", [_ABSENT, None])
def test_issue_root_missing_metadata_suppresses_metadata_checks(value):
    data = _valid_sbom()
    if value is _ABSENT:
        del data["metadata"]
    else:
        data["metadata"] = value
    assert _issue_codes(_fix_sbom_issues(data)) == [("root.missing_metadata", "$", None)]


@pytest.mark.parametrize("value", [[], "metadata", 5, True])
def test_issue_root_invalid_metadata_suppresses_metadata_checks(value):
    data = _valid_sbom()
    data["metadata"] = value
    assert _issue_codes(_fix_sbom_issues(data)) == [("root.invalid_metadata", "$", None)]


@pytest.mark.parametrize("value", [_ABSENT, None, []])
def test_issue_root_absent_null_or_empty_components_has_no_issue(value):
    data = _valid_sbom()
    if value is not _ABSENT:
        data["components"] = value
    assert _fix_sbom_issues(data) == []


@pytest.mark.parametrize("value", [{}, "components", 5, True])
def test_issue_root_invalid_components(value):
    data = _valid_sbom()
    data["components"] = value
    assert _issue_codes(_fix_sbom_issues(data)) == [
        ("root.invalid_components", "$", None)
    ]


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(_ABSENT, id="absent"),
        pytest.param(None, id="null"),
        pytest.param("", id="empty"),
        pytest.param(5, id="int"),
        pytest.param([], id="list"),
        pytest.param({}, id="dict"),
        pytest.param(True, id="bool"),
    ],
)
def test_issue_metadata_missing_timestamp(value):
    data = _valid_sbom()
    if value is _ABSENT:
        del data["metadata"]["timestamp"]
    else:
        data["metadata"]["timestamp"] = value
    assert _issue_codes(_fix_sbom_issues(data)) == [
        ("metadata.missing_timestamp", "$.metadata", None)
    ]


@pytest.mark.parametrize("value", ["not-a-date", "2020-01-01", "2026-01-01T00:00:00Z"])
def test_issue_metadata_existing_timestamp_string_is_not_reported(value):
    data = _valid_sbom()
    data["metadata"]["timestamp"] = value
    assert _fix_sbom_issues(data) == []


@pytest.mark.parametrize("value", [_ABSENT, None])
def test_issue_metadata_missing_component_suppresses_nested_checks(value):
    data = _valid_sbom()
    if value is _ABSENT:
        del data["metadata"]["component"]
    else:
        data["metadata"]["component"] = value
    assert _issue_codes(_fix_sbom_issues(data)) == [
        ("metadata.missing_component", "$.metadata", None)
    ]


@pytest.mark.parametrize("value", [[], "component", 5, True])
def test_issue_metadata_invalid_component_suppresses_nested_checks(value):
    data = _valid_sbom()
    data["metadata"]["component"] = value
    assert _issue_codes(_fix_sbom_issues(data)) == [
        ("metadata.invalid_component", "$.metadata", None)
    ]


@pytest.mark.parametrize(
    ("field", "code"),
    [
        ("type", "metadata_component.missing_type"),
        ("name", "metadata_component.missing_name"),
        ("version", "metadata_component.missing_version"),
    ],
)
@pytest.mark.parametrize(
    "value",
    [
        pytest.param(_ABSENT, id="absent"),
        pytest.param(None, id="null"),
        pytest.param("", id="empty"),
        pytest.param(5, id="int"),
        pytest.param([], id="list"),
        pytest.param({}, id="dict"),
    ],
)
def test_issue_metadata_component_missing_field(field, code, value):
    data = _valid_sbom()
    component = data["metadata"]["component"]
    if value is _ABSENT:
        del component[field]
    else:
        component[field] = value
    name = component.get("name")
    expected_component = name if isinstance(name, str) and name else None
    assert _issue_codes(_fix_sbom_issues(data)) == [
        (code, "$.metadata.component", expected_component)
    ]


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(_ABSENT, id="absent"),
        pytest.param(None, id="null"),
        pytest.param("Acme", id="string"),
        pytest.param(5, id="int"),
        pytest.param([], id="list"),
        pytest.param({}, id="empty-object"),
        pytest.param({"name": ""}, id="empty-name"),
        pytest.param({"name": "  "}, id="whitespace-name"),
        pytest.param({"name": None}, id="null-name"),
        pytest.param({"name": 5}, id="non-string-name"),
    ],
)
def test_issue_metadata_component_missing_manufacturer(value):
    data = _valid_sbom()
    component = data["metadata"]["component"]
    if value is _ABSENT:
        del component["manufacturer"]
    else:
        component["manufacturer"] = value
    assert _issue_codes(_fix_sbom_issues(data)) == [
        ("metadata_component.missing_manufacturer", "$.metadata.component", "app")
    ]


def test_issue_metadata_component_optional_fields_are_not_checked():
    data = _valid_sbom()
    data["metadata"]["component"] = {
        "type": "application",
        "name": "app",
        "version": "1.0.0",
        "manufacturer": {"name": "Acme"},
        "purl": 5,
        "externalReferences": 5,
        "properties": 5,
        "scope": 5,
    }
    assert _fix_sbom_issues(data) == []


@pytest.mark.parametrize("serial_number", [_ABSENT, None, "urn:uuid:123"])
def test_issue_never_reported_for_bom_format_or_serial_number(serial_number):
    data = _valid_sbom()
    data["bomFormat"] = "CycloneDX"
    if serial_number is not _ABSENT:
        data["serialNumber"] = serial_number
    assert _fix_sbom_issues(data) == []


def test_issue_valid_component_has_no_issues():
    data = _valid_sbom()
    data["components"] = [_valid_component()]
    assert _fix_sbom_issues(data) == []


def test_issue_integration_order_root_metadata_component_then_components():
    data = _valid_sbom()
    data["specVersion"] = "1.5"
    del data["metadata"]["timestamp"]
    del data["metadata"]["component"]["type"]
    component = _valid_component(name="a")
    del component["properties"]
    data["components"] = [component]
    issues = _fix_sbom_issues(data)
    assert _issue_codes(issues) == [
        ("root.spec_version_not_allowed", "$", None),
        ("metadata.missing_timestamp", "$.metadata", None),
        ("metadata_component.missing_type", "$.metadata.component", "app"),
        ("component.missing_gost_properties", "$.components[0]", "a"),
    ]
    assert issues[3].details == {
        "missing": ["GOST:attack_surface", "GOST:security_function"]
    }


def test_issue_metadata_invalid_component_is_not_duplicated_by_other_checks():
    data = _valid_sbom()
    data["metadata"] = {
        "timestamp": "2026-01-01T00:00:00Z",
        "component": "bad",
    }
    assert _issue_codes(_fix_sbom_issues(data)) == [
        ("metadata.invalid_component", "$.metadata", None)
    ]


def test_issue_collected_from_final_document_after_rules():
    data = _valid_sbom()
    del data["specVersion"]
    del data["metadata"]["timestamp"]
    result = fix_sbom(data, SbomFixOptions())
    assert result.issues == []
    assert result.fixed_sbom["specVersion"] == "1.7"
    assert result.fixed_sbom["metadata"]["timestamp"]


def test_licenses_options_default_to_disabled():
    options = SbomFixOptions()
    assert options.licenses.filter_non_proprietary is False
    assert options.licenses.add_proprietary is False
    assert options.licenses.remove_proprietary_source_references is False
    assert options.licenses.add_patterns == []


def test_license_rule_ids_come_last_in_execution_order():
    assert len(RULE_IDS) == 14
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
