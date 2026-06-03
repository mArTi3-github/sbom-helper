from __future__ import annotations

import json
import pytest
from pathlib import Path

from purl_resolver.settings_store import SettingsStore, AppSettings


@pytest.fixture
def tmp_settings_file(tmp_path: Path) -> Path:
    return tmp_path / "settings.json"


@pytest.fixture
def store(tmp_settings_file: Path) -> SettingsStore:
    return SettingsStore(path=tmp_settings_file)


class TestAppSettingsDefaults:
    def test_defaults(self):
        s = AppSettings()
        assert s.validate_db_urls is False
        assert s.url_validation_timeout == 5


class TestSettingsStoreLoad:
    def test_file_missing_creates_with_defaults(self, store: SettingsStore, tmp_settings_file: Path):
        result = store.load()
        assert result.validate_db_urls is False
        assert result.url_validation_timeout == 5
        assert tmp_settings_file.exists()

    def test_file_valid_json(self, store: SettingsStore, tmp_settings_file: Path):
        tmp_settings_file.write_text(json.dumps({
            "validate_db_urls": True,
            "url_validation_timeout": 10,
        }))
        result = store.load()
        assert result.validate_db_urls is True
        assert result.url_validation_timeout == 10

    def test_file_corrupt_json(self, store: SettingsStore, tmp_settings_file: Path):
        tmp_settings_file.write_text("not json {{{")
        result = store.load()
        assert result.validate_db_urls is False
        assert result.url_validation_timeout == 5


class TestSettingsStoreSave:
    def test_save_and_load_roundtrip(self, store: SettingsStore):
        original = AppSettings(validate_db_urls=True, url_validation_timeout=15)
        store.save(original)
        loaded = store.load()
        assert loaded.validate_db_urls is True
        assert loaded.url_validation_timeout == 15

    def test_save_creates_parent_dirs(self, tmp_path: Path):
        nested = tmp_path / "sub" / "dir" / "settings.json"
        store = SettingsStore(path=nested)
        store.save(AppSettings())
        assert nested.exists()
