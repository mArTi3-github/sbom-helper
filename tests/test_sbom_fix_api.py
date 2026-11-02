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


def upload_analyze(client, sbom):
    files = {"file": ("bom.json", json.dumps(sbom).encode("utf-8"), "application/json")}
    return client.post("/api/v1/sbom/fix/analyze", files=files)


def upload_fix(client, sbom, remove_fields=None, options=None):
    files = {"file": ("bom.json", json.dumps(sbom).encode("utf-8"), "application/json")}
    data = {}
    if options is not None:
        data["options"] = json.dumps(options)
    if remove_fields is not None:
        data["remove_fields"] = json.dumps(remove_fields)
    return client.post("/api/v1/sbom/fix", files=files, data=data)


@pytest.fixture
def client(tmp_path):
    test_app = FastAPI()
    test_app.state.sbom_fix_options_store = SbomFixOptionsStore(tmp_path / "options.json")
    test_app.include_router(router)
    with TestClient(test_app) as c:
        yield c


def test_field_catalog_returns_fstec_fields_and_default_keep(client):
    response = client.get("/api/v1/sbom/fix/field-catalog")
    assert response.status_code == 200
    body = response.json()
    assert len(body["fstec_fields"]) == 29
    assert len(body["default_keep"]) == 10
    assert {"path": "root.bomFormat", "status": "mandatory"} in body["fstec_fields"]
    assert {
        "path": "components[].externalReferences[].hashes",
        "status": "optional",
        "condition_key": "sourceDistributionHashes",
    } in body["fstec_fields"]


def test_analyze_returns_compact_inventory(client):
    response = upload_analyze(client, make_sbom())
    assert response.status_code == 200
    fields = {item["path"]: item for item in response.json()["fields"]}
    assert fields["root.dependencies"]["status"] == "additional"
    assert fields["root.dependencies"]["count"] == 1
    assert fields["root.version"]["status"] == "mandatory"
    assert fields["components[].hashes"]["count"] == 1


def test_analyze_rejects_invalid_input(client):
    files = {"file": ("bom.json", b"not json", "application/json")}
    assert client.post("/api/v1/sbom/fix/analyze", files=files).status_code == 400
    files = {"file": ("bom.json", json.dumps({"bomFormat": "Other"}).encode(), "application/json")}
    assert client.post("/api/v1/sbom/fix/analyze", files=files).status_code == 400


def test_fix_removes_selected_fields_and_reports_them(client):
    response = upload_fix(
        client, make_sbom(),
        remove_fields=["root.dependencies", "root.services", "components[].hashes"],
    )
    assert response.status_code == 200
    body = response.json()
    assert "dependencies" not in body["fixed_sbom"]
    assert "services" not in body["fixed_sbom"]
    assert "hashes" not in body["fixed_sbom"]["components"][0]
    removal = [s for s in body["stats"] if s["rule_id"] == "optional_fields.remove"]
    assert {(s["field"], s["count"]) for s in removal} == {
        ("root.dependencies", 1), ("root.services", 1), ("components[].hashes", 1)
    }


def test_fix_ignores_protected_and_malformed_paths(client):
    response = upload_fix(
        client, make_sbom(),
        remove_fields=["root.version", "components[].purl", "bad path"],
        options={"optional_fields": {"keep": []}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["fixed_sbom"]["version"] == 2
    assert "purl" in body["fixed_sbom"]["components"][0]
    assert not [s for s in body["stats"] if s["rule_id"] == "optional_fields.remove"]


def test_fix_ignores_invalid_keep_lines_in_options(client):
    response = upload_fix(
        client, make_sbom(),
        remove_fields=["components[].hashes"],
        options={"optional_fields": {"keep": ["bad path", "root.version"]}},
    )
    assert response.status_code == 200
    assert "hashes" not in response.json()["fixed_sbom"]["components"][0]


def test_fix_rejects_malformed_remove_fields(client):
    response = upload_fix(client, make_sbom(), remove_fields="not-a-list")
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_remove_fields"


def test_fix_rejects_unparseable_or_non_string_remove_fields(client):
    files = {"file": ("bom.json", json.dumps(make_sbom()).encode(), "application/json")}
    for raw in ["not json", json.dumps(["root.dependencies", 1])]:
        response = client.post(
            "/api/v1/sbom/fix", files=files, data={"remove_fields": raw}
        )
        assert response.status_code == 400
        assert response.json()["error"] == "invalid_remove_fields"


def test_save_options_rejects_invalid_keep(client):
    response = client.post(
        "/api/v1/sbom/fix/options",
        json={"options": {"optional_fields": {"keep": ["components[].group", "bad path"]}}},
    )
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_options"
    assert "bad path" in response.json()["detail"]


def test_save_and_load_options_keep_list(client):
    keep = ["components[].group", "components[].licenses"]
    assert client.post("/api/v1/sbom/fix/options",
                       json={"options": {"optional_fields": {"keep": keep}}}).status_code == 200
    body = client.get("/api/v1/sbom/fix/options").json()
    assert body["options"]["optional_fields"]["keep"] == keep


class TestFixSbom:
    def test_fix_returns_expected_shape(self, client: TestClient) -> None:
        response = upload(client, make_sbom())
        assert response.status_code == 200
        assert set(response.json()) == {"changed", "fixed_sbom", "stats", "issues"}
        assert response.json()["changed"] is True

    def test_fix_with_options_honors_them(self, client: TestClient) -> None:
        options = {"manufacturer": "Acme"}
        response = upload(client, make_sbom(), json.dumps(options))
        assert response.status_code == 200
        data = response.json()
        stats = {item["rule_id"]: item["count"] for item in data["stats"]}
        assert "add_manufacturer" in stats
        assert data["fixed_sbom"]["metadata"]["component"]["manufacturer"] == {
            "name": "Acme"
        }
        assert len(data["stats"]) == 8
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
        assert len(data["stats"]) == 8
        assert data["changed"] is True
        assert data["fixed_sbom"]["specVersion"] == "1.7"
        assert data["fixed_sbom"]["version"] == 2
        assert data["fixed_sbom"]["dependencies"] == [{"ref": "pkg:pypi/example@1.0"}]
        assert data["fixed_sbom"]["services"] == [{"name": "svc"}]

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
            json.dumps({"spec_version": "9.9.9"}),
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

    def test_get_with_non_utf8_file_returns_defaults(self, client: TestClient) -> None:
        store = client.app.state.sbom_fix_options_store
        store._path.write_bytes(b'{"reorder": false}\xff')
        response = client.get("/api/v1/sbom/fix/options")
        assert response.status_code == 200
        assert response.json() == {"options": SbomFixOptions().model_dump()}

    def test_post_trims_surrounding_spaces_in_spec_version(
        self, client: TestClient
    ) -> None:
        response = client.post(
            "/api/v1/sbom/fix/options",
            json={"options": {"spec_version": " 1.7 "}},
        )
        assert response.status_code == 200

        response = client.get("/api/v1/sbom/fix/options")
        assert response.status_code == 200
        assert response.json()["options"]["spec_version"] == "1.7"

    def test_post_saves_and_get_returns_saved(self, client: TestClient) -> None:
        options = SbomFixOptions(
            manufacturer="Acme",
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
            json={"options": {"spec_version": "bad"}},
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


def test_save_options_roundtrips_licenses_block(client):
    payload = {
        "options": {
            "licenses": {
                "add_proprietary": True,
                "add_patterns": [{"field": "name", "pattern": "vendor"}],
            }
        }
    }
    response = client.post("/api/v1/sbom/fix/options", json=payload)
    assert response.status_code == 200
    options = client.get("/api/v1/sbom/fix/options").json()["options"]
    assert options["licenses"]["add_proprietary"] is True
    assert options["licenses"]["add_patterns"] == [{"field": "name", "pattern": "vendor"}]


def test_save_options_rejects_non_list_patterns(client):
    response = client.post(
        "/api/v1/sbom/fix/options",
        json={"options": {"licenses": {"add_patterns": "name"}}},
    )
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_options"


def test_fix_options_endpoint_returns_leaf_flags_disabled(client):
    response = client.get("/api/v1/sbom/fix/options")
    assert response.status_code == 200
    components = response.json()["options"]["components"]
    assert components["remove_leaf_missing_purl"] is False
    assert components["remove_leaf_invalid_purl"] is False
    assert components["remove_leaf_missing_version"] is False


def test_fix_options_endpoint_returns_provided_by_defaults(client):
    response = client.get("/api/v1/sbom/fix/options")
    assert response.status_code == 200
    components = response.json()["options"]["components"]
    assert components["add_provided_by"] is True
    assert components["provided_by_patterns"] == [
        {
            "field": "purl",
            "pattern": "pkg:deb/astra",
            "provided_by": (
                'Операционная система специального назначения "Astra Linux Special Edition"'
            ),
        }
    ]


def test_save_options_roundtrips_provided_by_patterns(client):
    payload = {
        "options": {
            "components": {
                "add_provided_by": False,
                "provided_by_patterns": [
                    {
                        "field": "name",
                        "pattern": "vendor",
                        "provided_by": "Vendor SZI",
                    }
                ],
            }
        }
    }
    response = client.post("/api/v1/sbom/fix/options", json=payload)
    assert response.status_code == 200
    components = client.get("/api/v1/sbom/fix/options").json()["options"]["components"]
    assert components["add_provided_by"] is False
    assert components["provided_by_patterns"] == [
        {"field": "name", "pattern": "vendor", "provided_by": "Vendor SZI"}
    ]


def test_save_options_rejects_non_list_provided_by_patterns(client):
    response = client.post(
        "/api/v1/sbom/fix/options",
        json={"options": {"components": {"provided_by_patterns": "purl"}}},
    )
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_options"


def test_fix_options_endpoint_rejects_non_boolean_leaf_flag(client):
    response = client.post(
        "/api/v1/sbom/fix/options",
        json={"options": {"components": {"remove_leaf_missing_purl": "maybe"}}},
    )
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_options"


def test_fix_endpoint_applies_license_options(client):
    sbom = make_sbom()
    sbom["components"][0]["name"] = "vendor-lib"
    options = {
        "licenses": {
            "add_proprietary": True,
            "add_patterns": [{"field": "name", "pattern": "vendor"}],
        }
    }
    response = upload_fix(client, sbom, options=options)
    assert response.status_code == 200
    body = response.json()
    assert body["fixed_sbom"]["components"][0]["licenses"] == [
        {"license": {"name": "Proprietary"}}
    ]
    stat = next(
        stat for stat in body["stats"] if stat["rule_id"] == "licenses.add_proprietary"
    )
    assert stat["count"] == 1


def test_fix_endpoint_applies_provided_by_options(client):
    sbom = make_sbom()
    sbom["components"][0]["purl"] = "pkg:deb/astra/astra-utils@1.0"
    options = {
        "components": {
            "provided_by_patterns": [
                {
                    "field": "purl",
                    "pattern": "pkg:deb/astra",
                    "provided_by": "Astra Linux SE",
                }
            ]
        }
    }
    response = upload_fix(client, sbom, options=options)
    assert response.status_code == 200
    body = response.json()
    assert body["fixed_sbom"]["components"][0]["properties"] == [
        {"name": "GOST:provided_by", "value": "Astra Linux SE"}
    ]
    stat = next(
        stat
        for stat in body["stats"]
        if stat["rule_id"] == "components.add_provided_by"
    )
    assert stat["count"] == 1
