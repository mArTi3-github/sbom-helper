from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from purl_resolver.resolver.interface import Resolution
from purl_resolver.router import router
from purl_resolver.service import PurlResolutionService
from purl_resolver.settings_store import AppSettings, SettingsStore
from purl_resolver.storage.inmemory import InMemoryCache
from tests.helpers import FakeResolver


@pytest.fixture
def client() -> TestClient:
    test_app = FastAPI()
    test_app.state.storage = InMemoryCache()
    test_app.state.resolvers = [
        FakeResolver(
            resolution=Resolution(
                purl="pkg:pypi/requests@2.31.0",
                repository_url="https://github.com/psf/requests",
            ),
        ),
    ]
    test_app.state.settings_store = SettingsStore()
    test_app.state.resolution_service = PurlResolutionService(
        storage=test_app.state.storage,
        resolvers=test_app.state.resolvers,
        settings_store=test_app.state.settings_store,
    )
    test_app.include_router(router)
    with TestClient(test_app) as c:
        yield c


class TestHealth:
    def test_health_returns_ok(self, client: TestClient) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestResolve:
    def test_successful_resolution(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/resolve",
            json={"purl": "pkg:pypi/requests@2.31.0"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["repository_url"] == "https://github.com/psf/requests"
        assert data["purl"] == "pkg:pypi/requests"
        assert isinstance(data["warnings"], list)

    def test_invalid_purl_returns_400(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/resolve",
            json={"purl": "not-a-purl"},
        )
        assert response.status_code == 400
        data = response.json()
        assert "error" in data
        assert "detail" in data

    def test_unresolved_purl_returns_200_with_null(
        self, client: TestClient
    ) -> None:
        client.app.state.resolvers = [FakeResolver()]
        client.app.state.resolution_service = PurlResolutionService(
            storage=client.app.state.storage,
            resolvers=client.app.state.resolvers,
            settings_store=client.app.state.settings_store,
        )
        response = client.post(
            "/api/v1/resolve",
            json={"purl": "pkg:pypi/this-package-does-not-exist-12345@0.0.1"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["repository_url"] is None
        assert isinstance(data["warnings"], list)

    def test_empty_purl_returns_422(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/resolve",
            json={"purl": ""},
        )
        assert response.status_code == 422

    def test_repeat_request_returns_cached(self, client: TestClient) -> None:
        first = client.post(
            "/api/v1/resolve",
            json={"purl": "pkg:pypi/requests@2.31.0"},
        )
        assert first.status_code == 200
        first_data = first.json()

        second = client.post(
            "/api/v1/resolve",
            json={"purl": "pkg:pypi/requests@2.31.0"},
        )
        assert second.status_code == 200
        second_data = second.json()

        assert second_data["repository_url"] == first_data["repository_url"]
        assert second_data["purl"] == "pkg:pypi/requests"

    def test_different_versions_use_same_cache(self, client: TestClient) -> None:
        first = client.post(
            "/api/v1/resolve",
            json={"purl": "pkg:pypi/requests@2.31.0"},
        )
        assert first.status_code == 200
        first_data = first.json()

        second = client.post(
            "/api/v1/resolve",
            json={"purl": "pkg:pypi/requests@3.0.0"},
        )
        assert second.status_code == 200
        second_data = second.json()

        assert second_data["repository_url"] == first_data["repository_url"]
        assert second_data["purl"] == "pkg:pypi/requests"

    def test_purl_response_is_normalized(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/resolve",
            json={"purl": "pkg:pypi/requests@2.31.0"},
        )
        assert response.status_code == 200
        assert response.json()["purl"] == "pkg:pypi/requests"

    def test_invalid_purl_without_resolver_call(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/resolve",
            json={"purl": "not-a-purl"},
        )
        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "invalid_purl"

    def test_resolve_response_includes_found_by(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/resolve",
            json={"purl": "pkg:pypi/requests@2.31.0"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "found_by" in data
        assert data["found_by"] == "resolver"

    def test_cached_response_includes_found_by_local_db(self, client: TestClient) -> None:
        first = client.post(
            "/api/v1/resolve",
            json={"purl": "pkg:pypi/requests@2.31.0"},
        )
        assert first.status_code == 200
        cached_data = first.json()
        second = client.post(
            "/api/v1/resolve",
            json={"purl": "pkg:pypi/requests@2.31.0"},
        )
        assert second.status_code == 200
        data = second.json()
        assert data["found_by"] == "local_db"
        assert data["resolver"] == cached_data["resolver"]


class TestLibrariesIoSettings:
    def test_get_settings_includes_librariesio(self, client: TestClient) -> None:
        response = client.get("/api/v1/settings")
        assert response.status_code == 200
        data = response.json()
        assert "librariesio_enabled" in data
        assert "token_set" in data
        assert "librariesio_api_key" in data["token_set"]

    def test_patch_settings_enable_librariesio(self, client: TestClient, tmp_path: Path) -> None:
        client.app.state.settings_store = SettingsStore(path=tmp_path / "settings.json")
        response = client.patch("/api/v1/settings", json={
            "librariesio_enabled": True,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["librariesio_enabled"] is True

    def test_patch_settings_with_valid_librariesio_key(self, client: TestClient, tmp_path: Path) -> None:
        client.app.state.settings_store = SettingsStore(path=tmp_path / "settings.json")
        with patch("purl_resolver.routes.settings.validate_librariesio_key", return_value=True):
            response = client.patch("/api/v1/settings", json={
                "librariesio_api_key": "lib_test_key",
            })
        assert response.status_code == 200
        data = response.json()
        assert data["token_set"]["librariesio_api_key"] is True

    def test_patch_settings_with_invalid_librariesio_key(self, client: TestClient, tmp_path: Path) -> None:
        client.app.state.settings_store = SettingsStore(path=tmp_path / "settings.json")
        with patch("purl_resolver.routes.settings.validate_librariesio_key", return_value=False):
            response = client.patch("/api/v1/settings", json={
                "librariesio_api_key": "invalid_key",
            })
        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "invalid_token"

    def test_patch_settings_clear_librariesio_key(self, client: TestClient, tmp_path: Path) -> None:
        client.app.state.settings_store = SettingsStore(path=tmp_path / "settings.json")
        client.app.state.settings_store.save(
            client.app.state.settings_store.load().model_copy(update={"librariesio_api_key": "key"})
        )
        response = client.patch("/api/v1/settings", json={
            "librariesio_api_key": None,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["token_set"]["librariesio_api_key"] is False
