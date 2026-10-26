from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from purl_resolver.router import router
from purl_resolver.sbom.fixer import SbomFixOptions
from purl_resolver.sbom_fix_options_store import SbomFixOptionsStore


def make_sbom() -> dict[str, Any]:
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "name": "тест",
                "version": "1.0",
                "supplier": {"name": "Example"},
            },
        },
        "components": [
            {
                "type": "library",
                "name": "Компонент",
                "version": "1.0",
                "purl": "pkg:pypi/example@1.0",
                "scope": "required",
                "hashes": [{"alg": "SHA-256", "content": "abc"}],
            },
        ],
        "dependencies": [{"ref": "pkg:pypi/example@1.0"}],
        "services": [{"name": "svc"}],
    }


def upload(
    client: TestClient,
    sbom: Any,
    options: str | None = None,
):
    files = {"file": ("bom.json", json.dumps(sbom).encode("utf-8"), "application/json")}
    data = {"options": options} if options is not None else None
    return client.post("/api/v1/sbom/fix", files=files, data=data)


@pytest.fixture
def client(tmp_path):
    test_app = FastAPI()
    test_app.state.sbom_fix_options_store = SbomFixOptionsStore(tmp_path / "options.json")
    test_app.include_router(router)
    with TestClient(test_app) as c:
        yield c


class TestFixSbom:
    def test_fix_returns_expected_shape(self, client: TestClient) -> None:
        response = upload(
            client,
            make_sbom(),
            json.dumps({"metadata": {"component": {"remove_purl": True}}}),
        )
        assert response.status_code == 200
        assert set(response.json()) == {"changed", "fixed_sbom", "stats", "issues"}
        assert response.json()["changed"] is True

    def test_fix_with_options_honors_them(self, client: TestClient) -> None:
        options = {"metadata": {"component": {"remove_purl": True}}}
        response = upload(client, make_sbom(), json.dumps(options))
        assert response.status_code == 200
        data = response.json()
        stats = {item["rule_id"]: item["count"] for item in data["stats"]}
        assert "metadata_component.remove_purl" in stats
        assert len(data["stats"]) == 20
        assert all(set(item) == {"rule_id", "count"} for item in data["stats"])
        assert all(
            set(item) >= {"code", "path", "component", "details"}
            for item in data["issues"]
        )

    def test_non_ascii_is_not_escaped(self, client: TestClient) -> None:
        response = upload(client, make_sbom())
        assert response.status_code == 200
        assert "Компонент" in response.text
        assert "\\u" not in response.text
        names = [c["name"] for c in response.json()["fixed_sbom"]["components"]]
        assert names == ["Компонент"]

    def test_missing_options_uses_defaults(self, client: TestClient) -> None:
        response = upload(client, make_sbom())
        assert response.status_code == 200
        data = response.json()
        assert len(data["stats"]) == 19
        assert data["changed"] is True
        assert data["fixed_sbom"]["specVersion"] == "1.7"
        assert data["fixed_sbom"]["version"] == 2
        assert "dependencies" not in data["fixed_sbom"]
        assert "services" not in data["fixed_sbom"]

    def test_invalid_json_returns_error(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/sbom/fix",
            files={"file": ("bom.json", b"not json", "application/json")},
        )
        assert response.status_code == 400
        assert response.json() == {"error": "invalid_json"}

    def test_invalid_utf8_file_returns_invalid_json(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/sbom/fix",
            files={"file": ("bom.json", b"\xff\xfe\x00", "application/json")},
        )
        assert response.status_code == 400
        assert response.json() == {"error": "invalid_json"}

    def test_invalid_sbom_returns_error_with_detail(self, client: TestClient) -> None:
        response = upload(client, {"bomFormat": "SPDX"})
        assert response.status_code == 400
        body = response.json()
        assert body["error"] == "invalid_sbom"
        assert body["detail"]

    def test_invalid_options_json_returns_error(self, client: TestClient) -> None:
        response = upload(client, make_sbom(), "not json")
        assert response.status_code == 400
        body = response.json()
        assert body["error"] == "invalid_options"
        assert body["detail"]

    def test_invalid_spec_version_returns_error(self, client: TestClient) -> None:
        response = upload(
            client,
            make_sbom(),
            json.dumps({"root": {"spec_version": "9.9.9"}}),
        )
        assert response.status_code == 400
        body = response.json()
        assert body["error"] == "invalid_options"
        assert body["detail"]

    def test_file_too_large(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "purl_resolver.routes.sbom_fix.sbom_settings.max_file_size", 10
        )
        response = upload(client, make_sbom())
        assert response.status_code == 413
        body = response.json()
        assert body["error"] == "file_too_large"
        assert "max_size_mb" in body

    def test_missing_file_returns_422(self, client: TestClient) -> None:
        response = client.post("/api/v1/sbom/fix")
        assert response.status_code == 422


class TestSbomFixOptions:
    def test_get_returns_defaults(self, client: TestClient) -> None:
        response = client.get("/api/v1/sbom/fix/options")
        assert response.status_code == 200
        assert response.json() == {"options": SbomFixOptions().model_dump()}

    def test_post_saves_and_get_returns_saved(self, client: TestClient) -> None:
        options = SbomFixOptions(
            metadata={"component": {"remove_purl": True}},
            components={"fill_missing_gost_properties": True},
        ).model_dump()
        response = client.post("/api/v1/sbom/fix/options", json={"options": options})
        assert response.status_code == 200
        assert response.json() == {"status": "saved"}

        response = client.get("/api/v1/sbom/fix/options")
        assert response.status_code == 200
        assert response.json() == {"options": options}

    def test_post_invalid_options_returns_400(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/sbom/fix/options",
            json={"options": {"root": {"spec_version": "bad"}}},
        )
        assert response.status_code == 400
        body = response.json()
        assert body["error"] == "invalid_options"
        assert body["detail"]

    def test_post_non_json_body_returns_400(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/sbom/fix/options",
            content=b"not json",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400
        assert response.json()["error"] == "invalid_options"

    def test_post_body_without_options_returns_400(self, client: TestClient) -> None:
        response = client.post("/api/v1/sbom/fix/options", json={"foo": 1})
        assert response.status_code == 400
        assert response.json()["error"] == "invalid_options"

    def test_save_failure_returns_500(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def raise_oserror(self, options):
            raise OSError("disk full")

        monkeypatch.setattr(SbomFixOptionsStore, "save", raise_oserror)
        response = client.post(
            "/api/v1/sbom/fix/options",
            json={"options": SbomFixOptions().model_dump()},
        )
        assert response.status_code == 500
        assert response.json() == {"error": "options_save_failed"}
