import pytest
from pydantic import ValidationError

from purl_resolver.sbom.fixer import (
    RULE_IDS,
    SbomFixOptions,
    _reorder,
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
