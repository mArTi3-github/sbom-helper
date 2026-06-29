from __future__ import annotations

import json
from pathlib import Path

import pytest

from purl_resolver.settings_store import AppSettings, ServiceTokens, SettingsStore


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


class TestLibrariesIoSettings:
    def test_default_librariesio_disabled(self, tmp_path: Path) -> None:
        store = SettingsStore(path=tmp_path / "settings.json")
        settings = store.load()
        assert settings.librariesio_enabled is False
        assert settings.librariesio_api_key is None

    def test_save_and_load_librariesio_settings(self, tmp_path: Path) -> None:
        store = SettingsStore(path=tmp_path / "settings.json")
        settings = store.load()
        updated = settings.model_copy(update={
            "librariesio_enabled": True,
            "librariesio_api_key": "test_key_123",
        })
        store.save(updated)

        loaded = store.load()
        assert loaded.librariesio_enabled is True
        assert loaded.librariesio_api_key == "test_key_123"

    def test_clear_librariesio_key(self, tmp_path: Path) -> None:
        store = SettingsStore(path=tmp_path / "settings.json")
        settings = store.load()
        with_key = settings.model_copy(update={"librariesio_api_key": "key"})
        store.save(with_key)

        loaded = store.load()
        cleared = loaded.model_copy(update={"librariesio_api_key": None})
        store.save(cleared)

        final = store.load()
        assert final.librariesio_api_key is None


class TestEcosystemsSettings:
    def test_default_ecosystems_max_requests_per_second(self) -> None:
        s = AppSettings()
        assert s.ecosystems_max_requests_per_second == 2.0

    def test_save_and_load_ecosystems_rate(self, tmp_path: Path) -> None:
        store = SettingsStore(path=tmp_path / "settings.json")
        settings = store.load()
        updated = settings.model_copy(update={"ecosystems_max_requests_per_second": 5.0})
        store.save(updated)

        loaded = store.load()
        assert loaded.ecosystems_max_requests_per_second == 5.0


class TestSettingsStoreCache:

    def test_load_returns_cached_value_after_first_read(self, store: SettingsStore, tmp_settings_file: Path):
        import json
        tmp_settings_file.write_text(json.dumps({"validate_db_urls": True}))
        first = store.load()
        assert first.validate_db_urls is True

        tmp_settings_file.write_text(json.dumps({"validate_db_urls": False}))
        second = store.load()
        assert second.validate_db_urls is True, "Should return cached value, not re-read file"

    def test_save_invalidates_cache(self, store: SettingsStore, tmp_settings_file: Path):
        import json
        tmp_settings_file.write_text(json.dumps({"validate_db_urls": True}))
        first = store.load()
        assert first.validate_db_urls is True

        store.save(AppSettings(validate_db_urls=False))
        second = store.load()
        assert second.validate_db_urls is False, "Should re-read file after save"
