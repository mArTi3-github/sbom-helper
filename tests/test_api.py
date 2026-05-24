import pytest
from fastapi.testclient import TestClient

from purl_resolver.main import app

client = TestClient(app)


class TestHealth:
    def test_health_returns_ok(self) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestResolve:
    def test_successful_resolution(self) -> None:
        response = client.post(
            "/api/v1/resolve",
            json={"purl": "pkg:pypi/requests@2.31.0"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "github.com/psf/requests" in data["repository_url"]
        assert isinstance(data["confidence"], str) and data["confidence"] != ""
        assert isinstance(data["evidence"], list)
        assert isinstance(data["warnings"], list)

    def test_invalid_purl_returns_400(self) -> None:
        response = client.post(
            "/api/v1/resolve",
            json={"purl": "not-a-purl"},
        )
        assert response.status_code == 400
        data = response.json()
        assert "error" in data
        assert "message" in data

    def test_unresolved_purl_returns_200_with_null(self) -> None:
        response = client.post(
            "/api/v1/resolve",
            json={"purl": "pkg:pypi/this-package-does-not-exist-12345@0.0.1"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["repository_url"] is None
        assert isinstance(data["warnings"], list)

    def test_empty_purl_returns_422(self) -> None:
        response = client.post(
            "/api/v1/resolve",
            json={"purl": ""},
        )
        assert response.status_code == 422