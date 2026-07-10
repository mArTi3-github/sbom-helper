from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from purl_resolver.job_repository import JobRecord
from purl_resolver.routes.jobs import router


@pytest.fixture
def mock_manager():
    mgr = MagicMock()
    mgr.create_job = AsyncMock()
    mgr.get_job = AsyncMock()
    mgr.list_jobs = AsyncMock()
    mgr.cancel_job = AsyncMock()
    mgr.delete_job = AsyncMock()
    return mgr


@pytest.fixture
def client(mock_manager):
    app = FastAPI()
    app.state.job_manager = mock_manager
    app.include_router(router)
    with TestClient(app) as c:
        yield c


class TestCreateSbomEnrichJob:
    def test_success(self, client, mock_manager):
        mock_manager.create_job.return_value = JobRecord(
            id="job-1", type="sbom_enrich", status="queued"
        )
        response = client.post(
            "/api/v1/jobs/sbom-enrich",
            files={"file": ("test.json", b'{"packages":[]}', "application/json")},
        )
        assert response.status_code == 202
        assert response.json() == {"job_id": "job-1", "status": "queued"}
        mock_manager.create_job.assert_called_once()

    def test_file_too_large(self, client, mock_manager):
        with patch("purl_resolver.routes.jobs.sbom_settings.max_file_size", 10):
            response = client.post(
                "/api/v1/jobs/sbom-enrich",
                files={"file": ("test.json", b"x" * 100, "application/json")},
            )
        assert response.status_code == 413
        data = response.json()
        assert data["detail"]["error"] == "file_too_large"

    def test_invalid_json(self, client, mock_manager):
        response = client.post(
            "/api/v1/jobs/sbom-enrich",
            files={"file": ("test.json", b"not json", "text/plain")},
        )
        assert response.status_code == 400
        assert response.json() == {"error": "invalid_json"}

    def test_with_ignore_patterns(self, client, mock_manager):
        mock_manager.create_job.return_value = JobRecord(
            id="job-2", type="sbom_enrich", status="queued"
        )
        response = client.post(
            "/api/v1/jobs/sbom-enrich",
            files={"file": ("test.json", b'{"packages":[]}', "application/json")},
            data={
                "remove_unresolved_no_subcomponents": "true",
                "ignore_patterns": json.dumps([{"field": "name", "pattern": "test"}]),
            },
        )
        assert response.status_code == 202
        args, _ = mock_manager.create_job.call_args
        params = args[2]
        assert params["remove_unresolved_no_subcomponents"] is True
        assert params["ignore_patterns"] == [{"field": "name", "pattern": "test"}]


class TestGetJob:
    def test_existing(self, client, mock_manager):
        record = JobRecord(
            id="job-1", type="sbom_enrich", status="completed",
            progress_current=5, progress_total=10,
            params_json='{"remove_unresolved_no_subcomponents": false}',
            input_filename="test.json",
            summary_json=json.dumps({"total": 1}),
            results_json=json.dumps([{"purl": "pkg:pypi/requests"}]),
            error_message=None,
            created_at="2026-01-01T00:00:00",
            started_at="2026-01-01T00:01:00",
            finished_at="2026-01-01T00:02:00",
        )
        mock_manager.get_job.return_value = record
        response = client.get("/api/v1/jobs/job-1")
        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == "job-1"
        assert data["status"] == "completed"
        assert data["summary"] == {"total": 1}
        assert data["results"] == [{"purl": "pkg:pypi/requests"}]

    def test_not_found(self, client, mock_manager):
        mock_manager.get_job.return_value = None
        response = client.get("/api/v1/jobs/nonexistent")
        assert response.status_code == 404
        assert response.json() == {"detail": {"error": "job_not_found"}}


class TestDownloadResult:
    def test_completed(self, client, mock_manager, tmp_path):
        result_file = tmp_path / "result.json"
        result_file.write_text(json.dumps({"enriched": True}))
        mock_manager.get_job.return_value = JobRecord(
            id="job-1", type="sbom_enrich", status="completed",
            result_path=str(result_file),
            input_filename="test.json",
        )
        response = client.get("/api/v1/jobs/job-1/result")
        assert response.status_code == 200
        assert response.json() == {"enriched": True}

    def test_not_completed(self, client, mock_manager):
        mock_manager.get_job.return_value = JobRecord(
            id="job-1", type="sbom_enrich", status="running",
        )
        response = client.get("/api/v1/jobs/job-1/result")
        assert response.status_code == 400
        data = response.json()
        assert data["detail"]["error"] == "result_not_ready"

    def test_job_not_found(self, client, mock_manager):
        mock_manager.get_job.return_value = None
        response = client.get("/api/v1/jobs/nonexistent/result")
        assert response.status_code == 404

    def test_result_file_missing(self, client, mock_manager):
        mock_manager.get_job.return_value = JobRecord(
            id="job-1", type="sbom_enrich", status="completed",
            result_path=None,
            input_filename="test.json",
        )
        response = client.get("/api/v1/jobs/job-1/result")
        assert response.status_code == 404
        assert response.json() == {"detail": {"error": "result_file_not_found"}}


class TestCancelJob:
    def test_success(self, client, mock_manager):
        mock_manager.cancel_job.return_value = True
        response = client.post("/api/v1/jobs/job-1/cancel")
        assert response.status_code == 200
        assert response.json() == {"job_id": "job-1", "status": "cancelled"}

    def test_terminal_status(self, client, mock_manager):
        mock_manager.cancel_job.return_value = False
        mock_manager.get_job.return_value = JobRecord(
            id="job-1", type="sbom_enrich", status="completed"
        )
        response = client.post("/api/v1/jobs/job-1/cancel")
        assert response.status_code == 409
        data = response.json()
        assert data["detail"]["error"] == "job_already_terminal"

    def test_not_found(self, client, mock_manager):
        mock_manager.cancel_job.return_value = False
        mock_manager.get_job.return_value = None
        response = client.post("/api/v1/jobs/nonexistent/cancel")
        assert response.status_code == 404


class TestDeleteJob:
    def test_success(self, client, mock_manager):
        mock_manager.delete_job.return_value = True
        response = client.delete("/api/v1/jobs/job-1")
        assert response.status_code == 200
        assert response.json() == {"job_id": "job-1", "deleted": True}

    def test_not_found(self, client, mock_manager):
        mock_manager.delete_job.return_value = False
        response = client.delete("/api/v1/jobs/nonexistent")
        assert response.status_code == 404
        assert response.json() == {"detail": {"error": "job_not_found"}}


class TestListJobs:
    def test_empty(self, client, mock_manager):
        mock_manager.list_jobs.return_value = []
        response = client.get("/api/v1/jobs")
        assert response.status_code == 200
        assert response.json() == {"jobs": []}

    def test_with_records(self, client, mock_manager):
        mock_manager.list_jobs.return_value = [
            JobRecord(
                id="job-1", type="sbom_enrich", status="completed",
                progress_current=10, progress_total=10,
                input_filename="test.json",
                summary_json=json.dumps({"total": 5}),
                error_message=None,
                created_at="2026-01-01T00:00:00",
                started_at="2026-01-01T00:01:00",
                finished_at="2026-01-01T00:02:00",
            ),
        ]
        response = client.get("/api/v1/jobs?limit=10&offset=5")
        assert response.status_code == 200
        data = response.json()
        assert len(data["jobs"]) == 1
        assert data["jobs"][0]["job_id"] == "job-1"
        mock_manager.list_jobs.assert_called_once_with(limit=10, offset=5)
