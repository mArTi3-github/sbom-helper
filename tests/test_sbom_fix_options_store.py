from __future__ import annotations

import json
import logging

import pytest

from purl_resolver.sbom.fixer import (
    LicensePatternItem,
    LicensesFixOptions,
    SbomFixOptions,
)
from purl_resolver.sbom.optional_fields import DEFAULT_KEEP_FIELDS
from purl_resolver.sbom_fix_options_store import SbomFixOptionsStore


def test_load_missing_file_returns_defaults(tmp_path):
    store = SbomFixOptionsStore(tmp_path / "missing.json")
    assert store.load() == SbomFixOptions()


def test_save_load_roundtrip_including_spec_version(tmp_path):
    store = SbomFixOptionsStore(tmp_path / "options.json")
    options = SbomFixOptions(spec_version="1.6")
    store.save(options)
    assert store.load() == options


def test_corrupt_json_returns_defaults(tmp_path, caplog):
    path = tmp_path / "bad.json"
    path.write_text("not json", encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        assert SbomFixOptionsStore(path).load() == SbomFixOptions()
    assert "bad.json" in caplog.text


def test_corrupt_non_utf8_file_returns_defaults(tmp_path, caplog):
    path = tmp_path / "bad-encoding.json"
    path.write_bytes(b'{"reorder": false}\xff')
    with caplog.at_level(logging.WARNING):
        assert SbomFixOptionsStore(path).load() == SbomFixOptions()
    assert "bad-encoding.json" in caplog.text


def test_invalid_spec_version_returns_defaults(tmp_path, caplog):
    path = tmp_path / "invalid.json"
    path.write_text('{"spec_version": "9.9.9"}', encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        assert SbomFixOptionsStore(path).load() == SbomFixOptions()
    assert "invalid.json" in caplog.text


def test_os_error_returns_defaults(tmp_path, caplog):
    with caplog.at_level(logging.WARNING):
        assert SbomFixOptionsStore(tmp_path).load() == SbomFixOptions()
    assert "Failed to load sbom fix options" in caplog.text


def test_partial_json_fills_defaults(tmp_path):
    path = tmp_path / "partial.json"
    path.write_text('{"reorder": false}', encoding="utf-8")
    loaded = SbomFixOptionsStore(path).load()
    assert loaded.reorder is False
    assert loaded.set_spec_version is True
    assert loaded.add_timestamp is True


def test_custom_path_is_used(tmp_path):
    path = tmp_path / "nested" / "custom-options.json"
    store = SbomFixOptionsStore(path)
    store.save(SbomFixOptions())
    assert path.exists()
    assert store.load() == SbomFixOptions()


def test_save_writes_indented_utf8_json_with_trailing_newline(tmp_path):
    path = tmp_path / "options.json"
    store = SbomFixOptionsStore(path)
    options = SbomFixOptions.model_construct(spec_version="1.7-тест")

    store.save(options)

    text = path.read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert '\n  "spec_version": "1.7-тест"' in text
    assert json.loads(text) == options.model_dump()


def test_save_propagates_write_errors(tmp_path):
    parent_file = tmp_path / "not-a-dir"
    parent_file.write_text("", encoding="utf-8")
    store = SbomFixOptionsStore(parent_file / "options.json")
    with pytest.raises(OSError):
        store.save(SbomFixOptions())


def test_load_ignores_legacy_nested_options(tmp_path):
    path = tmp_path / "legacy.json"
    path.write_text(
        json.dumps({
            "root": {"reorder": False, "remove_dependencies": True},
            "metadata": {"component": {"rename_supplier": True}},
            "components": {"remove_hashes": True},
        }),
        encoding="utf-8",
    )
    options = SbomFixOptionsStore(path).load()
    assert options == SbomFixOptions()
    assert not hasattr(options, "root")
    assert options.optional_fields.keep == list(DEFAULT_KEEP_FIELDS)


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
