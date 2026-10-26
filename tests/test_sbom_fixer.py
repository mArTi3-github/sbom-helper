import copy
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from purl_resolver.sbom.fixer import (
    RULE_IDS,
    FixIssue,
    SbomFixOptions,
    _collect_component_issues,
    _fill_gost_properties,
    _filter_external_references,
    _filter_properties,
    _reorder,
    _walk_components,
    fix_sbom,
)


def test_defaults_all_on_except_two_rules():
    o = SbomFixOptions()
    assert o.root.set_spec_version is True
    assert o.root.spec_version == "1.7"
    assert o.metadata.add_timestamp is True
    assert o.metadata.component.remove_purl is False
    assert o.components.fill_missing_gost_properties is False
    assert o.components.filter_properties is True


@pytest.mark.parametrize("value", ["", "1", "1.7.0", "v1.7", "1,7", 1.7])
def test_invalid_spec_version_rejected(value):
    with pytest.raises(ValidationError):
        SbomFixOptions(root={"spec_version": value})


def test_all_enabled_rules_yield_21_stats_in_canonical_order():
    options = SbomFixOptions(
        metadata={"component": {"remove_purl": True}},
        components={"fill_missing_gost_properties": True},
    )
    result = fix_sbom(
        {"bomFormat": "CycloneDX", "specVersion": "1.7", "version": 1}, options
    )
    assert [stat.rule_id for stat in result.stats] == list(RULE_IDS)
    assert len(result.stats) == 21


def test_fix_sbom_copies_input_and_emits_zero_stats_for_enabled_rules():
    data = {"bomFormat": "CycloneDX", "specVersion": "1.7"}
    result = fix_sbom(data, SbomFixOptions())
    assert result.fixed_sbom == data
    assert result.fixed_sbom is not data
    assert result.changed is False
    assert len(result.stats) == 19
    assert all(stat.count == 0 for stat in result.stats)
    assert [stat.rule_id for stat in result.stats] == [
        "root.reorder", "root.set_spec_version", "root.remove_dependencies",
        "root.remove_services", "root.increment_version", "metadata.add_timestamp",
        "metadata.reorder", "metadata.remove_properties", "metadata.remove_tools",
        "metadata_component.reorder", "metadata_component.remove_external_references",
        "metadata_component.remove_properties", "metadata_component.remove_scope",
        "metadata_component.rename_supplier", "components.reorder",
        "components.remove_hashes", "components.remove_scope",
        "components.filter_external_references", "components.filter_properties",
    ]


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
    assert result.stats[0].count == 1


def test_root_reorder_skips_missing_keys_and_preserves_other_relative_order():
    data = {
        "$schema": "x",
        "extra_b": 2,
        "components": [],
        "extra_a": 1,
        "bomFormat": "CycloneDX",
    }
    result = fix_sbom(data, SbomFixOptions(root={"set_spec_version": False}))
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
    result = fix_sbom(data, SbomFixOptions())
    assert list(result.fixed_sbom["metadata"]) == [
        "timestamp", "component", "authors", "manufacture",
    ]
    stats = {stat.rule_id: stat.count for stat in result.stats}
    assert stats["metadata.reorder"] == 1


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
    result = fix_sbom(data, SbomFixOptions())
    assert list(result.fixed_sbom["metadata"]["component"]) == [
        "type", "name", "version", "manufacturer", "bom-ref",
    ]
    stats = {stat.rule_id: stat.count for stat in result.stats}
    assert stats["metadata_component.reorder"] == 1


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
    result = fix_sbom(data, SbomFixOptions())
    components = result.fixed_sbom["components"]
    assert list(components[0]) == ["type", "name", "version"]
    assert list(components[1]) == ["type", "name"]
    assert list(components[2]) == [
        "type", "name", "components", "z_extra", "a_extra",
    ]
    assert list(components[2]["components"][0]) == ["type", "name", "purl"]
    stats = {stat.rule_id: stat.count for stat in result.stats}
    assert stats["components.reorder"] == 2


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
    result = fix_sbom(data, SbomFixOptions())
    nested = result.fixed_sbom["metadata"]["component"]["components"][0]
    assert list(nested) == ["name", "type"]
    stats = {stat.rule_id: stat.count for stat in result.stats}
    assert stats["components.reorder"] == 0


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
        root={"reorder": False},
        metadata={"reorder": False, "component": {"reorder": False}},
        components={"reorder": False},
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
    assert "root.reorder" not in rule_ids
    assert "metadata.reorder" not in rule_ids
    assert "metadata_component.reorder" not in rule_ids
    assert "components.reorder" not in rule_ids
    assert all(stat.count == 0 for stat in result.stats)


def _stats(result):
    return {stat.rule_id: stat.count for stat in result.stats}


def test_set_spec_version_replaces_value_and_counts_one():
    data = {"bomFormat": "CycloneDX", "specVersion": "1.6"}
    result = fix_sbom(data, SbomFixOptions(root={"spec_version": "1.7"}))
    assert result.fixed_sbom["specVersion"] == "1.7"
    assert _stats(result)["root.set_spec_version"] == 1
    assert result.changed is True


def test_set_spec_version_adds_missing_key_and_counts_one():
    data = {"bomFormat": "CycloneDX"}
    result = fix_sbom(data, SbomFixOptions(root={"spec_version": "1.6"}))
    assert result.fixed_sbom["specVersion"] == "1.6"
    assert _stats(result)["root.set_spec_version"] == 1


def test_set_spec_version_same_value_counts_zero():
    data = {"bomFormat": "CycloneDX", "specVersion": "1.7"}
    result = fix_sbom(data, SbomFixOptions(root={"spec_version": "1.7"}))
    assert result.fixed_sbom == data
    assert _stats(result)["root.set_spec_version"] == 0


def test_set_spec_version_strips_configured_value():
    options = SbomFixOptions()
    options.root.spec_version = " 1.7 "
    data = {"bomFormat": "CycloneDX", "specVersion": "1.6"}
    result = fix_sbom(data, options)
    assert result.fixed_sbom["specVersion"] == "1.7"
    assert _stats(result)["root.set_spec_version"] == 1


@pytest.mark.parametrize(
    ("rule_id", "key"),
    [
        ("root.remove_dependencies", "dependencies"),
        ("root.remove_services", "services"),
    ],
)
def test_remove_root_key_removes_even_empty_list_and_counts_one(rule_id, key):
    data = {"bomFormat": "CycloneDX", "specVersion": "1.7", key: []}
    result = fix_sbom(data, SbomFixOptions())
    assert key not in result.fixed_sbom
    assert _stats(result)[rule_id] == 1
    assert result.changed is True


@pytest.mark.parametrize(
    ("rule_id", "key"),
    [
        ("root.remove_dependencies", "dependencies"),
        ("root.remove_services", "services"),
    ],
)
def test_remove_absent_root_key_counts_zero(rule_id, key):
    data = {"bomFormat": "CycloneDX", "specVersion": "1.7"}
    result = fix_sbom(data, SbomFixOptions())
    assert key not in result.fixed_sbom
    assert _stats(result)[rule_id] == 0
    assert result.changed is False


@pytest.mark.parametrize("value", [0, 1, -3])
def test_increment_version_increments_integers(value):
    data = {"bomFormat": "CycloneDX", "specVersion": "1.7", "version": value}
    result = fix_sbom(data, SbomFixOptions())
    assert result.fixed_sbom["version"] == value + 1
    assert _stats(result)["root.increment_version"] == 1


@pytest.mark.parametrize("value", ["1", 1.5, True, False, None])
def test_increment_version_leaves_missing_or_non_int_unchanged(value):
    data = {"bomFormat": "CycloneDX", "specVersion": "1.7", "version": value}
    result = fix_sbom(data, SbomFixOptions())
    assert result.fixed_sbom["version"] == value
    assert _stats(result)["root.increment_version"] == 0


def test_increment_version_absent_counts_zero_and_does_not_add_key():
    data = {"bomFormat": "CycloneDX", "specVersion": "1.7"}
    result = fix_sbom(data, SbomFixOptions())
    assert "version" not in result.fixed_sbom
    assert _stats(result)["root.increment_version"] == 0


def test_disabled_root_rules_leave_fields_untouched_and_are_absent_from_stats():
    data = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "dependencies": [],
        "services": [],
    }
    options = SbomFixOptions(
        root={
            "set_spec_version": False,
            "remove_dependencies": False,
            "remove_services": False,
            "increment_version": False,
        }
    )
    result = fix_sbom(data, options)
    assert result.fixed_sbom == data
    rule_ids = {stat.rule_id for stat in result.stats}
    assert "root.set_spec_version" not in rule_ids
    assert "root.remove_dependencies" not in rule_ids
    assert "root.remove_services" not in rule_ids
    assert "root.increment_version" not in rule_ids
    assert result.changed is False


def test_added_spec_version_goes_last_when_root_reorder_disabled():
    data = {"bomFormat": "CycloneDX", "version": 5}
    options = SbomFixOptions(root={"reorder": False})
    result = fix_sbom(data, options)
    assert list(result.fixed_sbom) == ["bomFormat", "version", "specVersion"]
    stats = _stats(result)
    assert stats["root.set_spec_version"] == 1
    assert stats["root.increment_version"] == 1
    assert "root.reorder" not in stats
    assert result.changed is True


def test_any_root_rule_with_positive_count_sets_changed():
    options = SbomFixOptions(
        root={
            "set_spec_version": False,
            "remove_dependencies": False,
            "remove_services": False,
        }
    )
    data = {"bomFormat": "CycloneDX", "specVersion": "1.7", "version": 1}
    result = fix_sbom(data, options)
    assert _stats(result)["root.increment_version"] == 1
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
    assert _stats(result)["metadata.add_timestamp"] == 1
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
    assert _stats(result)["metadata.add_timestamp"] == 0


def test_add_timestamp_does_nothing_without_metadata():
    data = {"bomFormat": "CycloneDX", "specVersion": "1.7"}
    result = fix_sbom(data, SbomFixOptions(), now=NOW)
    assert "metadata" not in result.fixed_sbom
    assert _stats(result)["metadata.add_timestamp"] == 0
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
    assert _stats(second)["metadata.add_timestamp"] == 0
    assert second.changed is False


@pytest.mark.parametrize("tools", [[], {"components": []}], ids=["array", "object"])
def test_metadata_remove_properties_and_tools(tools):
    data = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.7",
        "metadata": {"timestamp": NOW_TEXT, "properties": [{"name": "x"}], "tools": tools},
    }
    result = fix_sbom(data, SbomFixOptions(), now=NOW)
    metadata = result.fixed_sbom["metadata"]
    assert "properties" not in metadata
    assert "tools" not in metadata
    stats = _stats(result)
    assert stats["metadata.remove_properties"] == 1
    assert stats["metadata.remove_tools"] == 1


def test_metadata_remove_absent_properties_and_tools_counts_zero():
    data = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.7",
        "metadata": {"timestamp": NOW_TEXT},
    }
    result = fix_sbom(data, SbomFixOptions(), now=NOW)
    stats = _stats(result)
    assert stats["metadata.remove_properties"] == 0
    assert stats["metadata.remove_tools"] == 0


def test_metadata_component_removes_fields_but_keeps_purl_and_group_by_default():
    data = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.7",
        "metadata": {
            "timestamp": NOW_TEXT,
            "component": {
                "type": "application",
                "name": "root",
                "group": "g",
                "purl": "pkg:x/y@1",
                "scope": "required",
                "properties": [{"name": "x"}],
                "externalReferences": [{"type": "vcs"}],
            },
        },
    }
    result = fix_sbom(data, SbomFixOptions(), now=NOW)
    component = result.fixed_sbom["metadata"]["component"]
    assert component["purl"] == "pkg:x/y@1"
    assert component["group"] == "g"
    assert "scope" not in component
    assert "properties" not in component
    assert "externalReferences" not in component
    stats = _stats(result)
    assert stats["metadata_component.remove_external_references"] == 1
    assert stats["metadata_component.remove_properties"] == 1
    assert "metadata_component.remove_purl" not in stats
    assert stats["metadata_component.remove_scope"] == 1


def test_metadata_component_remove_purl_when_enabled():
    data = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.7",
        "metadata": {
            "timestamp": NOW_TEXT,
            "component": {"type": "application", "name": "root", "purl": "pkg:x/y@1"},
        },
    }
    options = SbomFixOptions(metadata={"component": {"remove_purl": True}})
    result = fix_sbom(data, options, now=NOW)
    assert "purl" not in result.fixed_sbom["metadata"]["component"]
    assert _stats(result)["metadata_component.remove_purl"] == 1


def test_rename_supplier_transfers_when_manufacturer_missing():
    data = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.7",
        "metadata": {
            "timestamp": NOW_TEXT,
            "component": {
                "type": "application",
                "name": "root",
                "supplier": {"name": "Vendor"},
            },
        },
    }
    result = fix_sbom(data, SbomFixOptions(), now=NOW)
    component = result.fixed_sbom["metadata"]["component"]
    assert component["manufacturer"] == {"name": "Vendor"}
    assert "supplier" not in component
    assert _stats(result)["metadata_component.rename_supplier"] == 1


def test_rename_supplier_transfers_when_manufacturer_is_null():
    data = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.7",
        "metadata": {
            "timestamp": NOW_TEXT,
            "component": {
                "type": "application",
                "name": "root",
                "manufacturer": None,
                "supplier": {"name": "Vendor"},
            },
        },
    }
    result = fix_sbom(data, SbomFixOptions(), now=NOW)
    component = result.fixed_sbom["metadata"]["component"]
    assert component["manufacturer"] == {"name": "Vendor"}
    assert "supplier" not in component
    assert _stats(result)["metadata_component.rename_supplier"] == 1


@pytest.mark.parametrize(
    "manufacturer",
    [{"name": "Existing"}, {}, {"name": ""}],
    ids=["object", "empty-object", "empty-name"],
)
def test_rename_supplier_keeps_existing_manufacturer_and_deletes_supplier(manufacturer):
    data = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.7",
        "metadata": {
            "timestamp": NOW_TEXT,
            "component": {
                "type": "application",
                "name": "root",
                "manufacturer": manufacturer,
                "supplier": {"name": "Vendor"},
            },
        },
    }
    result = fix_sbom(data, SbomFixOptions(), now=NOW)
    component = result.fixed_sbom["metadata"]["component"]
    assert component["manufacturer"] == manufacturer
    assert "supplier" not in component
    assert _stats(result)["metadata_component.rename_supplier"] == 1


def test_rename_supplier_null_is_deleted_without_creating_manufacturer():
    data = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.7",
        "metadata": {
            "timestamp": NOW_TEXT,
            "component": {
                "type": "application",
                "name": "root",
                "supplier": None,
            },
        },
    }
    result = fix_sbom(data, SbomFixOptions(), now=NOW)
    component = result.fixed_sbom["metadata"]["component"]
    assert "manufacturer" not in component
    assert "supplier" not in component
    assert _stats(result)["metadata_component.rename_supplier"] == 1


def test_rename_supplier_absent_counts_zero_and_does_not_add_manufacturer():
    data = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.7",
        "metadata": {
            "timestamp": NOW_TEXT,
            "component": {"type": "application", "name": "root"},
        },
    }
    result = fix_sbom(data, SbomFixOptions(), now=NOW)
    component = result.fixed_sbom["metadata"]["component"]
    assert "manufacturer" not in component
    assert _stats(result)["metadata_component.rename_supplier"] == 0


@pytest.mark.parametrize(
    "metadata",
    [{}, {"timestamp": NOW_TEXT}, {"timestamp": NOW_TEXT, "component": None}],
    ids=["no-component", "no-component-key", "null-component"],
)
def test_metadata_component_rules_skip_when_component_missing_or_null(metadata):
    data = {"bomFormat": "CycloneDX", "specVersion": "1.7", "metadata": metadata}
    result = fix_sbom(data, SbomFixOptions(), now=NOW)
    stats = _stats(result)
    assert stats["metadata_component.remove_external_references"] == 0
    assert stats["metadata_component.remove_properties"] == 0
    assert stats["metadata_component.remove_scope"] == 0
    assert stats["metadata_component.rename_supplier"] == 0


@pytest.mark.parametrize("metadata", [None, [], "text"], ids=["null", "list", "string"])
def test_metadata_rules_skip_when_metadata_is_not_object(metadata):
    data = {"bomFormat": "CycloneDX", "specVersion": "1.7", "metadata": metadata}
    result = fix_sbom(data, SbomFixOptions(), now=NOW)
    assert result.fixed_sbom["metadata"] == metadata
    stats = _stats(result)
    assert stats["metadata.add_timestamp"] == 0
    assert stats["metadata.remove_properties"] == 0
    assert stats["metadata.remove_tools"] == 0


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
        root={"reorder": False},
        metadata={
            "add_timestamp": False,
            "reorder": False,
            "remove_properties": False,
            "remove_tools": False,
            "component": {
                "reorder": False,
                "remove_external_references": False,
                "remove_properties": False,
                "remove_purl": False,
                "remove_scope": False,
                "rename_supplier": False,
            },
        },
    )
    result = fix_sbom(data, options, now=NOW)
    assert result.fixed_sbom == data
    rule_ids = {stat.rule_id for stat in result.stats}
    assert "metadata.add_timestamp" not in rule_ids
    assert "metadata.remove_properties" not in rule_ids
    assert "metadata.remove_tools" not in rule_ids
    assert "metadata_component.rename_supplier" not in rule_ids
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


def test_remove_hashes_removes_direct_key_only_and_keeps_external_reference_hashes():
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
    result = fix_sbom(data, SbomFixOptions())
    component = result.fixed_sbom["components"][0]
    assert "hashes" not in component
    assert component["externalReferences"][0]["hashes"] == [
        {"alg": "SHA-1", "content": "keep"}
    ]
    assert "hashes" not in component["components"][0]
    assert _stats(result)["components.remove_hashes"] == 2


def test_remove_scope_on_all_levels():
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
    result = fix_sbom(data, SbomFixOptions())
    component = result.fixed_sbom["components"][0]
    assert "scope" not in component
    assert "scope" not in component["components"][0]
    assert "scope" not in component["components"][0]["components"][0]
    assert _stats(result)["components.remove_scope"] == 3


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
        root={"reorder": False, "set_spec_version": False},
        metadata={
            "add_timestamp": False,
            "reorder": False,
            "component": {"reorder": False},
        },
        components={
            "reorder": False,
            "remove_hashes": False,
            "remove_scope": False,
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
