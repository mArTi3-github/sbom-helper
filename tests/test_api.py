from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from purl_resolver.resolver.interface import Resolution
from purl_resolver.router import router
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
                repository_type="github",
                repository_kind="source_code",
                confidence="high",
                evidence=["verified"],
            ),
        ),
    ]
    test_app.state.settings_store = SettingsStore()
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
        assert data["confidence"] == "high"
        assert isinstance(data["evidence"], list)
        assert isinstance(data["warnings"], list)

    def test_invalid_purl_returns_400(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/resolve",
            json={"purl": "not-a-purl"},
        )
        assert response.status_code == 400
        data = response.json()
        assert "error" in data
        assert "message" in data

    def test_unresolved_purl_returns_200_with_null(
        self, client: TestClient
    ) -> None:
        client.app.state.resolvers = [FakeResolver()]
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