from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from purl_resolver.resolver.interface import Resolution
from purl_resolver.router import router
from purl_resolver.service import PurlResolutionService
from purl_resolver.settings_store import SettingsStore
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


class TestResolveBatch:
    def test_batch_successful_resolution(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/resolve/batch",
            json={"purls": ["pkg:pypi/requests@2.31.0"]},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 1
        item = data["results"][0]
        assert item["repository_url"] == "https://github.com/psf/requests"
        assert item["purl"] == "pkg:pypi/requests@2.31.0"
        assert item["error"] is None
        assert isinstance(item["warnings"], list)

    def test_batch_returns_row_per_purl_in_order(self, client: TestClient) -> None:
        client.app.state.resolvers = [FakeResolver()]
        client.app.state.resolution_service = PurlResolutionService(
            storage=client.app.state.storage,
            resolvers=client.app.state.resolvers,
            settings_store=client.app.state.settings_store,
        )
        response = client.post(
            "/api/v1/resolve/batch",
            json={"purls": [
                "pkg:pypi/requests@2.31.0",
                "pkg:pypi/this-package-does-not-exist-12345@0.0.1",
            ]},
        )
        assert response.status_code == 200
        results = response.json()["results"]
        assert len(results) == 2
        assert results[0]["purl"] == "pkg:pypi/requests@2.31.0"
        assert results[0]["repository_url"] is None
        assert results[0]["error"] is None
        assert results[1]["purl"] == "pkg:pypi/this-package-does-not-exist-12345@0.0.1"
        assert results[1]["repository_url"] is None

    def test_batch_invalid_purl_returns_error_row(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/resolve/batch",
            json={"purls": ["not-a-purl"]},
        )
        assert response.status_code == 200
        results = response.json()["results"]
        assert len(results) == 1
        assert results[0]["error"] == "invalid_purl"
        assert results[0]["repository_url"] is None

    def test_batch_mixed_valid_and_invalid(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/resolve/batch",
            json={"purls": ["not-a-purl", "pkg:pypi/requests@2.31.0"]},
        )
        assert response.status_code == 200
        results = response.json()["results"]
        assert results[0]["error"] == "invalid_purl"
        assert results[1]["repository_url"] == "https://github.com/psf/requests"
        assert results[1]["error"] is None

    def test_batch_empty_list_returns_422(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/resolve/batch",
            json={"purls": []},
        )
        assert response.status_code == 422

    def test_batch_repeat_request_returns_cached(self, client: TestClient) -> None:
        first = client.post(
            "/api/v1/resolve/batch",
            json={"purls": ["pkg:pypi/requests@2.31.0"]},
        )
        assert first.status_code == 200
        first_data = first.json()

        second = client.post(
            "/api/v1/resolve/batch",
            json={"purls": ["pkg:pypi/requests@2.31.0"]},
        )
        assert second.status_code == 200
        second_data = second.json()

        first_repo = first_data["results"][0]["repository_url"]
        second_repo = second_data["results"][0]["repository_url"]
        assert second_repo == first_repo

    def test_batch_different_versions_use_same_cache(self, client: TestClient) -> None:
        first = client.post(
            "/api/v1/resolve/batch",
            json={"purls": ["pkg:pypi/requests@2.31.0"]},
        )
        assert first.status_code == 200

        second = client.post(
            "/api/v1/resolve/batch",
            json={"purls": ["pkg:pypi/requests@3.0.0"]},
        )
        assert second.status_code == 200

        first_repo = first.json()["results"][0]["repository_url"]
        second_repo = second.json()["results"][0]["repository_url"]
        assert second_repo == first_repo

    def test_batch_response_purl_is_original_input(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/resolve/batch",
            json={"purls": ["pkg:pypi/requests@2.31.0"]},
        )
        assert response.status_code == 200
        assert response.json()["results"][0]["purl"] == "pkg:pypi/requests@2.31.0"

    def test_batch_resolve_response_includes_found_by(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/resolve/batch",
            json={"purls": ["pkg:pypi/requests@2.31.0"]},
        )
        assert response.status_code == 200
        data = response.json()["results"][0]
        assert data["found_by"] == "resolver"

    def test_batch_cached_response_includes_found_by_local_db(self, client: TestClient) -> None:
        first = client.post(
            "/api/v1/resolve/batch",
            json={"purls": ["pkg:pypi/requests@2.31.0"]},
        )
        assert first.status_code == 200
        cached_data = first.json()["results"][0]
        second = client.post(
            "/api/v1/resolve/batch",
            json={"purls": ["pkg:pypi/requests@2.31.0"]},
        )
        assert second.status_code == 200
        data = second.json()["results"][0]
        assert data["found_by"] == "local_db"
        assert data["resolver"] == cached_data["resolver"]

    def test_batch_duplicate_purls_resolved_once(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/resolve/batch",
            json={"purls": ["pkg:pypi/requests@2.31.0", "pkg:pypi/requests@2.31.0"]},
        )
        assert response.status_code == 200
        results = response.json()["results"]
        assert len(results) == 2
        assert results[0]["repository_url"] == "https://github.com/psf/requests"
        assert results[1]["repository_url"] == "https://github.com/psf/requests"
        assert client.app.state.resolvers[0].call_count == 1

    def test_batch_different_versions_resolved_once(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/resolve/batch",
            json={"purls": ["pkg:pypi/requests@2.31.0", "pkg:pypi/requests@3.0.0"]},
        )
        assert response.status_code == 200
        results = response.json()["results"]
        assert len(results) == 2
        assert results[0]["repository_url"] == "https://github.com/psf/requests"
        assert results[1]["repository_url"] == "https://github.com/psf/requests"
        assert client.app.state.resolvers[0].call_count == 1

    def test_batch_too_large_returns_400(self, client: TestClient, tmp_path: Path) -> None:
        client.app.state.settings_store = SettingsStore(path=tmp_path / "settings.json")
        client.app.state.settings_store.save(
            client.app.state.settings_store.load().model_copy(update={"batch_max_items": 2})
        )
        response = client.post(
            "/api/v1/resolve/batch",
            json={"purls": ["pkg:pypi/a@1.0.0", "pkg:pypi/b@1.0.0", "pkg:pypi/c@1.0.0"]},
        )
        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "batch_too_large"
        assert "detail" in data


class TestLibrariesIoSettings:
    def test_get_settings_includes_librariesio(self, client: TestClient) -> None:
        response = client.get("/api/v1/settings")
        assert response.status_code == 200
        data = response.json()
        assert "librariesio_enabled" in data
        assert "token_set" in data
        assert "librariesio_api_key" in data["token_set"]

    def test_get_settings_includes_batch_max_items(self, client: TestClient) -> None:
        response = client.get("/api/v1/settings")
        assert response.status_code == 200
        data = response.json()
        assert data["batch_max_items"] == 100

    def test_patch_settings_batch_max_items(self, client: TestClient, tmp_path: Path) -> None:
        client.app.state.settings_store = SettingsStore(path=tmp_path / "settings.json")
        response = client.patch("/api/v1/settings", json={
            "batch_max_items": 50,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["batch_max_items"] == 50

    def test_patch_invalid_batch_max_items(self, client: TestClient, tmp_path: Path) -> None:
        client.app.state.settings_store = SettingsStore(path=tmp_path / "settings.json")
        response = client.patch("/api/v1/settings", json={
            "batch_max_items": 0,
        })
        assert response.status_code == 422

    def test_patch_settings_enable_librariesio(self, client: TestClient, tmp_path: Path) -> None:
        client.app.state.settings_store = SettingsStore(path=tmp_path / "settings.json")
        response = client.patch("/api/v1/settings", json={
            "librariesio_enabled": True,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["librariesio_enabled"] is True

    def test_patch_settings_with_valid_librariesio_key(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        client.app.state.settings_store = SettingsStore(path=tmp_path / "settings.json")
        with patch("purl_resolver.routes.settings.validate_librariesio_key", return_value=True):
            response = client.patch("/api/v1/settings", json={
                "librariesio_api_key": "lib_test_key",
            })
        assert response.status_code == 200
        data = response.json()
        assert data["token_set"]["librariesio_api_key"] is True

    def test_patch_settings_with_invalid_librariesio_key(
        self, client: TestClient, tmp_path: Path
    ) -> None:
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


class TestResolverChainRebuild:
    def test_patch_settings_updates_resolution_service_chain(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        client.app.state.settings_store = SettingsStore(path=tmp_path / "settings.json")
        response = client.patch("/api/v1/settings", json={
            "librariesio_enabled": False,
            "ecosystems_enabled": False,
            "llm_resolver_enabled": True,
            "llm_resolver_base_url": "https://api.example.com",
            "llm_resolver_api_key": "test-key",
            "llm_resolver_model": "test-model",
        })
        assert response.status_code == 200
        names = [r.name for r in client.app.state.resolution_service._resolvers]
        assert "fake" not in names, "service must use the rebuilt chain, not the startup one"
        assert names[-1] == "llm"

    def test_patch_settings_rebuilt_chain_resolves_with_new_resolver(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        client.app.state.settings_store = SettingsStore(path=tmp_path / "settings.json")

        with (
            patch("purl_resolver.resolver.factory.Purl2RepoResolver") as purl2repo_cls,
            patch("purl_resolver.resolver.factory.DepsdevResolver") as depsdev_cls,
            patch("purl_resolver.resolver.factory.LlmResolver") as llm_cls,
        ):
            fake_purl2repo = purl2repo_cls.return_value
            fake_purl2repo.name = "purl2repo"
            fake_purl2repo.resolve = AsyncMock(
                return_value=Resolution(purl="pkg:pypi/requests@2.31.0")
            )

            fake_depsdev = depsdev_cls.return_value
            fake_depsdev.name = "depsdev"
            fake_depsdev.resolve = AsyncMock(
                return_value=Resolution(purl="pkg:pypi/requests@2.31.0")
            )

            fake_llm = llm_cls.return_value
            fake_llm.name = "llm"
            fake_llm.resolve = AsyncMock(return_value=Resolution(
                purl="pkg:pypi/requests@2.31.0",
                repository_url="https://github.com/psf/requests",
            ))

            response = client.patch("/api/v1/settings", json={
                "librariesio_enabled": False,
                "ecosystems_enabled": False,
                "llm_resolver_enabled": True,
                "llm_resolver_base_url": "https://api.example.com",
                "llm_resolver_api_key": "test-key",
                "llm_resolver_model": "test-model",
            })
            assert response.status_code == 200

            resolve_response = client.post(
                "/api/v1/resolve/batch",
                json={"purls": ["pkg:pypi/requests@2.31.0"]},
            )
        assert resolve_response.status_code == 200
        data = resolve_response.json()["results"][0]
        assert data["repository_url"] == "https://github.com/psf/requests"
        assert data["resolver"] == "llm"
        fake_llm.resolve.assert_awaited_once()
