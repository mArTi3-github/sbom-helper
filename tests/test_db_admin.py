from __future__ import annotations

import csv
import io

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from purl_resolver.db_admin_service import DbAdminService
from purl_resolver.resolver.interface import Resolution
from purl_resolver.router import router
from purl_resolver.schemas import ResolveResponse
from purl_resolver.storage.inmemory import InMemoryCache


@pytest.fixture
def storage():
    return InMemoryCache()


@pytest.fixture
def populated_storage(storage):
    entries = [
        ResolveResponse(
            purl="pkg:pypi/requests",
            repository_url="https://github.com/psf/requests",
            repository_type="github",
            repository_kind="source_code",
            confidence="high",
            evidence=["homepage from PyPI"],
            warnings=[],
        ),
        ResolveResponse(
            purl="pkg:npm/express",
            repository_url="https://github.com/expressjs/express",
            repository_type="github",
            repository_kind="source_code",
            confidence="low",
            evidence=[],
            warnings=["registry mismatch"],
        ),
        ResolveResponse(
            purl="pkg:pypi/flask",
            repository_url="https://github.com/pallets/flask",
            repository_type="github",
            repository_kind="source_code",
            confidence="high",
            evidence=["homepage from PyPI"],
            warnings=[],
        ),
    ]
    for e in entries:
        storage._store[e.purl] = e
    return storage


@pytest.fixture
def admin_client(storage):
    test_app = FastAPI()
    test_app.state.storage = storage
    test_app.state.db_admin_service = DbAdminService(storage)
    test_app.include_router(router)
    return TestClient(test_app)


class TestAdminListPurls:
    def test_list_all(self, admin_client):
        response = admin_client.get("/api/v1/db/purls")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["rows"] == []
        assert data["page"] == 1

    def test_list_with_data(self, populated_storage, admin_client):
        response = admin_client.get("/api/v1/db/purls")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        assert len(data["rows"]) == 3

    def test_list_pagination(self, admin_client):
        response = admin_client.get("/api/v1/db/purls?page_size=2&page=1")
        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 1
        assert data["page_size"] == 2

    def test_list_search(self, populated_storage, admin_client):
        response = admin_client.get("/api/v1/db/purls?search=requests")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["rows"][0]["purl"] == "pkg:pypi/requests"

    def test_list_confidence_filter(self, populated_storage, admin_client):
        response = admin_client.get("/api/v1/db/purls?confidence=high")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2

    def test_list_exports_all_columns(self, populated_storage, admin_client):
        response = admin_client.get("/api/v1/db/purls")
        row = response.json()["rows"][0]
        for col in ("purl", "repository_url", "repository_type", "repository_kind",
                     "confidence", "evidence", "warnings", "version_reference", "resolver"):
            assert col in row


class TestAdminUpdatePurl:
    def test_update_repository_url(self, populated_storage, admin_client):
        response = admin_client.patch(
            "/api/v1/db/purls/pkg:pypi/requests",
            json={"repository_url": "https://github.com/psf/requests-v3"},
        )
        assert response.status_code == 200
        assert response.json() == {"ok": True}
        cached = populated_storage._store.get("pkg:pypi/requests")
        assert cached.repository_url == "https://github.com/psf/requests-v3"

    def test_update_rekey_purl(self, populated_storage, admin_client):
        response = admin_client.patch(
            "/api/v1/db/purls/pkg:pypi/requests",
            json={"purl": "pkg:pypi/requests3", "repository_url": "https://github.com/psf/requests3"},
        )
        assert response.status_code == 200
        assert response.json() == {"ok": True}
        assert "pkg:pypi/requests" not in populated_storage._store
        assert "pkg:pypi/requests3" in populated_storage._store

    def test_update_not_found(self, populated_storage, admin_client):
        response = admin_client.patch(
            "/api/v1/db/purls/pkg:pypi/nonexistent",
            json={"repository_url": "https://example.com"},
        )
        assert response.status_code == 404

    def test_update_no_changes(self, populated_storage, admin_client):
        response = admin_client.patch(
            "/api/v1/db/purls/pkg:pypi/requests",
            json={},
        )
        assert response.status_code == 200


class TestAdminDeletePurls:
    def test_delete_single(self, populated_storage, admin_client):
        response = admin_client.request(
            "DELETE", "/api/v1/db/purls",
            json={"purls": ["pkg:pypi/requests"]},
        )
        assert response.status_code == 200
        assert response.json() == {"deleted": 1}
        assert "pkg:pypi/requests" not in populated_storage._store

    def test_delete_multiple(self, populated_storage, admin_client):
        response = admin_client.request(
            "DELETE", "/api/v1/db/purls",
            json={"purls": ["pkg:pypi/requests", "pkg:npm/express"]},
        )
        assert response.status_code == 200
        assert response.json() == {"deleted": 2}

    def test_delete_nonexistent(self, populated_storage, admin_client):
        response = admin_client.request(
            "DELETE", "/api/v1/db/purls",
            json={"purls": ["pkg:pypi/nonexistent"]},
        )
        assert response.status_code == 200
        assert response.json() == {"deleted": 0}

    def test_delete_empty_list(self, admin_client):
        response = admin_client.request(
            "DELETE", "/api/v1/db/purls",
            json={"purls": []},
        )
        assert response.status_code == 200
        assert response.json() == {"deleted": 0}


class TestAdminImport:
    def test_import_upsert_new_rows(self, storage, admin_client):
        csv_content = "purl,repository_url\npkg:pypi/newpkg,https://github.com/new/pkg\n"
        response = admin_client.post(
            "/api/v1/db/import",
            files={"file": ("test.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")},
            data={"strategy": "upsert"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["imported"] == 1
        assert data["skipped"] == 0
        assert data["errors"] == []
        assert "pkg:pypi/newpkg" in storage._store

    def test_import_upsert_overwrite_existing(self, populated_storage, admin_client):
        csv_content = "purl,repository_url\npkg:pypi/requests,https://github.com/psf/requests-v4\n"
        response = admin_client.post(
            "/api/v1/db/import",
            files={"file": ("test.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")},
            data={"strategy": "upsert"},
        )
        assert response.status_code == 200
        assert response.json()["imported"] == 1
        assert populated_storage._store["pkg:pypi/requests"].repository_url == "https://github.com/psf/requests-v4"

    def test_import_skip_existing(self, populated_storage, admin_client):
        csv_content = (
            "purl,repository_url\n"
            "pkg:pypi/requests,https://github.com/NEW/requests\n"
            "pkg:pypi/totallynew,https://github.com/new/totallynew\n"
        )
        response = admin_client.post(
            "/api/v1/db/import",
            files={"file": ("test.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")},
            data={"strategy": "skip_existing"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["imported"] == 1
        assert data["skipped"] == 1
        assert populated_storage._store["pkg:pypi/requests"].repository_url == "https://github.com/psf/requests"

    def test_import_missing_columns(self, admin_client):
        csv_content = "purl\npkg:pypi/requests\n"
        response = admin_client.post(
            "/api/v1/db/import",
            files={"file": ("test.csv", io.BytesIO(csv_content.encode("utf-8-sig")), "text/csv")},
            data={"strategy": "upsert"},
        )
        assert response.status_code == 400
        assert response.json()["error"] == "invalid_csv"

    def test_import_empty_purl_errors(self, storage, admin_client):
        csv_content = "purl,repository_url\n,https://example.com\npkg:pypi/valid,https://example.com\n"
        response = admin_client.post(
            "/api/v1/db/import",
            files={"file": ("test.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")},
            data={"strategy": "upsert"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["imported"] == 1
        assert len(data["errors"]) == 1

    def test_import_optional_columns(self, storage, admin_client):
        csv_content = (
            "purl,repository_url,confidence,resolver\n"
            "pkg:pypi/pkg1,https://github.com/owner/pkg1,high,custom-resolver\n"
        )
        response = admin_client.post(
            "/api/v1/db/import",
            files={"file": ("test.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")},
            data={"strategy": "upsert"},
        )
        assert response.status_code == 200
        assert response.json()["imported"] == 1
        assert "pkg:pypi/pkg1" in storage._store


class TestAdminExport:
    def test_export_selected_csv(self, populated_storage, admin_client):
        response = admin_client.post(
            "/api/v1/db/export",
            json={"purls": ["pkg:pypi/requests", "pkg:npm/express"]},
        )
        assert response.status_code == 200
        assert "attachment" in response.headers.get("content-disposition", "")
        content = response.content.decode("utf-8")
        reader = csv.DictReader(io.StringIO(content), delimiter=",")
        rows = list(reader)
        assert len(rows) == 2
        assert rows[0]["purl"] == "pkg:pypi/requests"
        assert rows[1]["purl"] == "pkg:npm/express"

    def test_export_selected_empty_list(self, admin_client):
        response = admin_client.post(
            "/api/v1/db/export",
            json={"purls": []},
        )
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        reader = csv.DictReader(io.StringIO(content), delimiter=",")
        rows = list(reader)
        assert len(rows) == 0

    def test_export_selected_partial(self, populated_storage, admin_client):
        response = admin_client.post(
            "/api/v1/db/export",
            json={"purls": ["pkg:pypi/requests", "pkg:pypi/nonexistent"]},
        )
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        reader = csv.DictReader(io.StringIO(content), delimiter=",")
        rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["purl"] == "pkg:pypi/requests"

    def test_export_selected_all_existing(self, populated_storage, admin_client):
        response = admin_client.post(
            "/api/v1/db/export",
            json={"purls": ["pkg:pypi/requests", "pkg:npm/express", "pkg:pypi/flask"]},
        )
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        reader = csv.DictReader(io.StringIO(content), delimiter=",")
        rows = list(reader)
        assert len(rows) == 3

    def test_export_uses_comma_delimiter(self, populated_storage, admin_client):
        response = admin_client.post(
            "/api/v1/db/export",
            json={"purls": ["pkg:pypi/requests"]},
        )
        content = response.content.decode("utf-8")
        first_line = content.split("\n")[0]
        assert "," in first_line
        assert ";" not in first_line


class TestAdminImportBom:
    def test_import_with_bom(self, storage, admin_client):
        csv_content = "\ufeffpurl,repository_url\npkg:pypi/bomtest,https://github.com/bom/test\n"
        response = admin_client.post(
            "/api/v1/db/import",
            files={"file": ("test.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")},
            data={"strategy": "upsert"},
        )
        assert response.status_code == 200
        assert response.json()["imported"] == 1
        assert "pkg:pypi/bomtest" in storage._store

    def test_import_with_trailing_newline(self, storage, admin_client):
        csv_content = "purl,repository_url\npkg:pypi/trailing,https://github.com/trailing/test\n\n\n"
        response = admin_client.post(
            "/api/v1/db/import",
            files={"file": ("test.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")},
            data={"strategy": "upsert"},
        )
        assert response.status_code == 200
        assert response.json()["imported"] == 1
        assert "pkg:pypi/trailing" in storage._store

    def test_import_commas_in_values(self, storage, admin_client):
        csv_content = 'purl,repository_url,evidence,warnings\npkg:pypi/semi,https://github.com/semi/test,"[""value,with,commas""]","[""warn,1""]"\n'
        response = admin_client.post(
            "/api/v1/db/import",
            files={"file": ("test.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")},
            data={"strategy": "upsert"},
        )
        assert response.status_code == 200
        assert response.json()["imported"] == 1


class TestSbomStoresPreExistingRefs:
    async def test_sbom_stores_components_with_existing_references(self):
        storage = InMemoryCache()

        sbom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "components": [
                {
                    "name": "requests",
                    "purl": "pkg:pypi/requests",
                    "externalReferences": [
                        {"type": "vcs", "url": "https://github.com/psf/requests"}
                    ],
                },
                {
                    "name": "express",
                    "purl": "pkg:npm/express",
                },
            ],
        }

        from purl_resolver.sbom.collector import collect_components
        from purl_resolver.service import PurlResolutionService
        from tests.helpers import FakeResolver

        components = collect_components(sbom)
        purls_to_resolve = [c.purl for c in components if c.needs_enrichment]

        resolver = FakeResolver(
            resolution=Resolution(
                purl="pkg:npm/express@4.17.1",
                repository_url="https://github.com/expressjs/express",
            )
        )

        svc = PurlResolutionService(storage, [resolver])

        await svc.resolve_batch(purls_to_resolve)
        await svc.store_preexisting_references(components)

        assert "pkg:npm/express" in storage._store
        assert "pkg:pypi/requests" in storage._store
        req = storage._store["pkg:pypi/requests"]
        assert req.repository_url == "https://github.com/psf/requests"
