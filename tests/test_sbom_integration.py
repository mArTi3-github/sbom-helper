from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from purl_resolver.resolver.purl2repo import Purl2RepoResolver
from purl_resolver.router import router
from purl_resolver.storage.inmemory import InMemoryCache


@pytest.fixture
def client() -> TestClient:
    test_app = FastAPI()
    test_app.state.storage = InMemoryCache()
    test_app.state.resolvers = [Purl2RepoResolver()]
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


class TestSbomValidation:
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


class TestSbomResolveE2E:
    """Tests using real Purl2RepoResolver to catch bugs that SelectiveResolver misses."""

    def test_remove_resolved_and_unresolved_children_no_crash(
        self, client: TestClient
    ) -> None:
        """Regression: removing unresolved children while resolved children exist
        must not crash with IndexError from stale component paths."""
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
                        {
                            "type": "library",
                            "name": "unknown",
                            "version": "1.0",
                            "purl": "pkg:pypi/unknown-pkg@1.0",
                        },
                        {
                            "type": "library",
                            "name": "cffi",
                            "version": "2.0.0",
                            "purl": "pkg:pypi/cffi@2.0.0",
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
        assert data["summary"]["removed"] >= 1
        enriched = data["enriched_sbom"]
        parent = enriched["components"][0]
        assert parent["name"] == "parent-pkg"
        remaining = parent.get("components", [])
        for child in remaining:
            assert child.get("externalReferences"), (
                f"resolved child {child['name']} should have externalReferences"
            )

    def test_remove_default_false_keeps_all_components(
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

    def test_enrichment_inserts_vcs_references(self, client: TestClient) -> None:
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
            ],
        }
        response = client.post(
            "/api/v1/resolve/sbom",
            files={"file": ("test.json", json.dumps(sbom), "application/json")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["summary"]["found"] >= 1
        enriched = data["enriched_sbom"]
        refs = enriched["components"][0].get("externalReferences", [])
        assert any(r["type"] == "vcs" for r in refs)

    def test_enrichment_with_real_file(self, client: TestClient) -> None:
        """End-to-end test with the real SBOM fixture that has an intentionally
        broken PURL (altgraphekekeke) to verify the full pipeline handles it."""
        with open(".misc/addictional_materials/sbom_example_missed_references_unknown_purl.json") as f:
            sbom_data = json.load(f)
        response = client.post(
            "/api/v1/resolve/sbom",
            data={"remove_unresolved_no_subcomponents": "true"},
            files={"file": ("test.json", json.dumps(sbom_data), "application/json")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["summary"]["removed"] >= 1
        enriched = data["enriched_sbom"]
        assert enriched["version"] > 1
        parent = enriched["components"][0]
        remaining = parent.get("components", [])
        for child in remaining:
            assert child.get("externalReferences"), (
                f"resolved child {child['name']} should have externalReferences"
            )
