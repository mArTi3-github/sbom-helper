from __future__ import annotations

import json
import pytest
from pathlib import Path

from purl_resolver.settings_store import SettingsStore, AppSettings, ServiceTokens


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


class TestServiceTokens:
    def test_default_has_no_github_token(self):
        t = ServiceTokens()
        assert t.github_token is None

    def test_with_github_token(self):
        t = ServiceTokens(github_token="ghp_abc123")
        assert t.github_token == "ghp_abc123"


class TestAppSettingsServiceTokens:
    def test_service_tokens_extracts_github_token(self):
        s = AppSettings(github_token="ghp_xyz")
        tokens = s.service_tokens()
        assert isinstance(tokens, ServiceTokens)
        assert tokens.github_token == "ghp_xyz"

    def test_service_tokens_default_is_none(self):
        s = AppSettings()
        tokens = s.service_tokens()
        assert tokens.github_token is None

    def test_github_token_defaults_to_none(self):
        s = AppSettings()
        assert s.github_token is None

    def test_github_token_roundtrip(self, store: SettingsStore):
        original = AppSettings(github_token="ghp_test123")
        store.save(original)
        loaded = store.load()
        assert loaded.github_token == "ghp_test123"
