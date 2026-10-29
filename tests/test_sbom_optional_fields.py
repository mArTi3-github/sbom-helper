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
