from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from purl_resolver.resolver.interface import Resolution, Resolver
from purl_resolver.router import router
from purl_resolver.storage.inmemory import InMemoryCache


class SelectiveResolver(Resolver):
    def __init__(self, purl: str, resolution: Resolution) -> None:
        self._purl = purl
        self._resolution = resolution
        self.call_count = 0

    def resolve(self, purl: str) -> Resolution:
        self.call_count += 1
        if purl == self._purl:
            return self._resolution
        return Resolution(purl=purl)


@pytest.fixture
def client() -> TestClient:
    test_app = FastAPI()
    test_app.state.storage = InMemoryCache()
    test_app.state.resolvers = [
        SelectiveResolver(
            purl="pkg:pypi/certifi@2026.1.4",
            resolution=Resolution(
                purl="pkg:pypi/certifi@2026.1.4",
                repository_url="https://github.com/certifi/python-certifi",
                repository_type="github",
                repository_kind="source_code",
                confidence="high",
                evidence=["verified"],
            ),
        ),
        SelectiveResolver(
            purl="pkg:pypi/black@25.12.0",
            resolution=Resolution(
                purl="pkg:pypi/black@25.12.0",
                repository_url="https://github.com/psf/black",
                repository_type="github",
                repository_kind="source_code",
                confidence="high",
                evidence=["verified"],
            ),
        ),
        SelectiveResolver(
            purl="pkg:pypi/cffi@2.0.0",
            resolution=Resolution(
                purl="pkg:pypi/cffi@2.0.0",
                repository_url="https://github.com/python-cffi/cffi",
                repository_type="github",
                repository_kind="source_code",
                confidence="high",
                evidence=["verified"],
            ),
        ),
    ]
    test_app.include_router(router)
    with TestClient(test_app) as c:
        yield c


class TestSbomUpdaterPage:
    def test_returns_html(self, client: TestClient) -> None:
        response = client.get("/sbom-updater")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")

    def test_contains_upload_text(self, client: TestClient) -> None:
        response = client.get("/sbom-updater")
        assert "CycloneDX".encode() in response.content


class TestSbomResolve:
    def test_successful_enrichment(self, client: TestClient) -> None:
        sbom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "metadata": {
                "timestamp": "2024-01-01T00:00:00",
                "component": {"type": "application", "name": "app", "version": "1.0"},
            },
            "components": [
                {
                    "type": "library",
                    "name": "certifi",
                    "version": "2026.1.4",
                    "purl": "pkg:pypi/certifi@2026.1.4",
                },
                {
                    "type": "library",
                    "name": "black",
                    "version": "25.12.0",
                    "purl": "pkg:pypi/black@25.12.0",
                },
                {
                    "type": "library",
                    "name": "unknown",
                    "version": "1.0",
                    "purl": "pkg:pypi/unknown@1.0",
                },
            ],
        }
        response = client.post(
            "/api/v1/resolve/sbom",
            files={"file": ("test.json", json.dumps(sbom), "application/json")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["summary"]["found"] == 2
        assert data["summary"]["not_found"] == 1
        assert data["summary"]["skipped"] == 0
        assert len(data["results"]) == 3

        enriched = data["enriched_sbom"]
        assert enriched["version"] == 2
        assert enriched["components"][0].get("externalReferences") == [
            {"type": "vcs", "url": "https://github.com/certifi/python-certifi"}
        ]

    def test_enriches_multiple_versions_of_same_package(
        self, client: TestClient
    ) -> None:
        sbom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "metadata": {
                "timestamp": "2024-01-01T00:00:00",
                "component": {"type": "application", "name": "app", "version": "1.0"},
            },
            "components": [
                {
                    "type": "library",
                    "name": "cffi",
                    "version": "2.0.0",
                    "purl": "pkg:pypi/cffi@2.0.0",
                },
                {
                    "type": "library",
                    "name": "cffi",
                    "version": "1.15.0",
                    "purl": "pkg:pypi/cffi@1.15.0",
                },
            ],
        }
        response = client.post(
            "/api/v1/resolve/sbom",
            files={"file": ("test.json", json.dumps(sbom), "application/json")},
        )
        assert response.status_code == 200
        data = response.json()
        # Both components match normalized "pkg:pypi/cffi" → 1 unique PURL found
        assert data["summary"]["found"] == 1
        enriched = data["enriched_sbom"]
        expected_url = "https://github.com/python-cffi/cffi"
        assert enriched["components"][0].get("externalReferences") == [
            {"type": "vcs", "url": expected_url}
        ]
        assert enriched["components"][1].get("externalReferences") == [
            {"type": "vcs", "url": expected_url}
        ]

    def test_invalid_json_returns_400(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/resolve/sbom",
            files={"file": ("bad.json", b"this is not json", "application/json")},
        )
        assert response.status_code == 400

    def test_missing_file_returns_422(self, client: TestClient) -> None:
        response = client.post("/api/v1/resolve/sbom")
        assert response.status_code == 422

    def test_invalid_bom_format_returns_400(self, client: TestClient) -> None:
        sbom = {"bomFormat": "SPDX", "specVersion": "1.6"}
        response = client.post(
            "/api/v1/resolve/sbom",
            files={"file": ("bad.json", json.dumps(sbom), "application/json")},
        )
        assert response.status_code == 400

    def test_skipped_components_counted(self, client: TestClient) -> None:
        sbom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "metadata": {
                "timestamp": "2024-01-01T00:00:00",
                "component": {"type": "application", "name": "app", "version": "1.0"},
            },
            "components": [
                {
                    "type": "library",
                    "name": "totally-invalid-purl!!!",
                    "version": "1.0",
                    "purl": "not-even-close-to-a-purl",
                },
            ],
        }
        response = client.post(
            "/api/v1/resolve/sbom",
            files={"file": ("test.json", json.dumps(sbom), "application/json")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["summary"]["skipped"] == 1

    def test_remove_unresolved_no_subcomponents_removes_components(
        self, client: TestClient
    ) -> None:
        sbom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "metadata": {
                "timestamp": "2024-01-01T00:00:00",
                "component": {"type": "application", "name": "app", "version": "1.0"},
            },
            "components": [
                {
                    "type": "library",
                    "name": "certifi",
                    "version": "2026.1.4",
                    "purl": "pkg:pypi/certifi@2026.1.4",
                },
                {
                    "type": "library",
                    "name": "unknown",
                    "version": "1.0",
                    "purl": "pkg:pypi/unknown-pkg@1.0",
                },
            ],
        }
        response = client.post(
            "/api/v1/resolve/sbom",
            data={"remove_unresolved_no_subcomponents": "true"},
            files={"file": ("test.json", json.dumps(sbom), "application/json")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["summary"]["removed"] == 1
        removed_results = [r for r in data["results"] if r["status"] == "removed"]
        assert len(removed_results) == 1
        assert removed_results[0]["purl"] == "pkg:pypi/unknown-pkg@1.0"
        enriched = data["enriched_sbom"]
        assert len(enriched["components"]) == 1
        assert enriched["components"][0]["name"] == "certifi"

    def test_remove_unresolved_keeps_parent_with_subcomponents(
        self, client: TestClient
    ) -> None:
        sbom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "metadata": {
                "timestamp": "2024-01-01T00:00:00",
                "component": {"type": "application", "name": "app", "version": "1.0"},
            },
            "components": [
                {
                    "type": "application",
                    "name": "parent-pkg",
                    "version": "1.0",
                    "purl": "pkg:generic/parent-pkg@1.0",
                    "components": [
                        {
                            "type": "library",
                            "name": "certifi",
                            "version": "2026.1.4",
                            "purl": "pkg:pypi/certifi@2026.1.4",
                        },
                    ],
                },
            ],
        }
        response = client.post(
            "/api/v1/resolve/sbom",
            data={"remove_unresolved_no_subcomponents": "true"},
            files={"file": ("test.json", json.dumps(sbom), "application/json")},
        )
        assert response.status_code == 200
        data = response.json()
        enriched = data["enriched_sbom"]
        assert len(enriched["components"]) == 1
        assert enriched["components"][0]["name"] == "parent-pkg"

    def test_default_false_preserves_current_behavior(
        self, client: TestClient
    ) -> None:
        sbom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "metadata": {
                "timestamp": "2024-01-01T00:00:00",
                "component": {"type": "application", "name": "app", "version": "1.0"},
            },
            "components": [
                {
                    "type": "library",
                    "name": "unknown",
                    "version": "1.0",
                    "purl": "pkg:pypi/unknown-pkg@1.0",
                },
            ],
        }
        response = client.post(
            "/api/v1/resolve/sbom",
            files={"file": ("test.json", json.dumps(sbom), "application/json")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["summary"]["removed"] == 0
        assert data["summary"]["not_found"] == 1
        enriched = data["enriched_sbom"]
        assert len(enriched["components"]) == 1