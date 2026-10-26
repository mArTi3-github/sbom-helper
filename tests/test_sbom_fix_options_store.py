from __future__ import annotations

import json
import logging

import pytest

from purl_resolver.sbom.fixer import RootFixOptions, SbomFixOptions
from purl_resolver.sbom_fix_options_store import SbomFixOptionsStore


def test_load_missing_file_returns_defaults(tmp_path):
    store = SbomFixOptionsStore(tmp_path / "missing.json")
    assert store.load() == SbomFixOptions()


def test_save_load_roundtrip_including_spec_version(tmp_path):
    store = SbomFixOptionsStore(tmp_path / "options.json")
    options = SbomFixOptions(root={"spec_version": "1.6"})
    store.save(options)
    assert store.load() == options


def test_corrupt_json_returns_defaults(tmp_path, caplog):
    path = tmp_path / "bad.json"
    path.write_text("not json", encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        assert SbomFixOptionsStore(path).load() == SbomFixOptions()
    assert "bad.json" in caplog.text


def test_invalid_spec_version_returns_defaults(tmp_path, caplog):
    path = tmp_path / "invalid.json"
    path.write_text('{"root": {"spec_version": "9.9.9"}}', encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        assert SbomFixOptionsStore(path).load() == SbomFixOptions()
    assert "invalid.json" in caplog.text


def test_os_error_returns_defaults(tmp_path, caplog):
    with caplog.at_level(logging.WARNING):
        assert SbomFixOptionsStore(tmp_path).load() == SbomFixOptions()
    assert "Failed to load sbom fix options" in caplog.text


def test_partial_json_fills_defaults(tmp_path):
    path = tmp_path / "partial.json"
    path.write_text('{"root": {"reorder": false}}', encoding="utf-8")
    loaded = SbomFixOptionsStore(path).load()
    assert loaded.root.reorder is False
    assert loaded.root.set_spec_version is True
    assert loaded.metadata.add_timestamp is True


def test_custom_path_is_used(tmp_path):
    path = tmp_path / "nested" / "custom-options.json"
    store = SbomFixOptionsStore(path)
    store.save(SbomFixOptions())
    assert path.exists()
    assert store.load() == SbomFixOptions()


def test_save_writes_indented_utf8_json_with_trailing_newline(tmp_path):
    path = tmp_path / "options.json"
    store = SbomFixOptionsStore(path)
    options = SbomFixOptions.model_construct(
        root=RootFixOptions.model_construct(spec_version="1.7-тест")
    )

    store.save(options)

    text = path.read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert '\n  "root": {' in text
    assert "1.7-тест" in text
    assert json.loads(text) == options.model_dump()


def test_save_propagates_write_errors(tmp_path):
    parent_file = tmp_path / "not-a-dir"
    parent_file.write_text("", encoding="utf-8")
    store = SbomFixOptionsStore(parent_file / "options.json")
    with pytest.raises(OSError):
        store.save(SbomFixOptions())
