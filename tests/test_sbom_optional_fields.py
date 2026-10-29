import copy

from purl_resolver.sbom.optional_fields import (
    DEFAULT_KEEP_FIELDS,
    FSTEC_FIELDS,
    analyze_fields,
    canonical_sort_key,
    invalid_keep_entries,
    normalize_keep,
    remove_optional_fields,
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


def test_normalize_keep_skips_non_string_entries():
    assert normalize_keep(["components[].group", 123, None]) == [
        "components[].group"
    ]


def test_invalid_keep_entries_stringifies_non_string_entries():
    assert invalid_keep_entries(["components[].group", 123]) == ["123"]


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
