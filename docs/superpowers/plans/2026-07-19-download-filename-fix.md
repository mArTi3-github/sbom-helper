# Download filename fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the `GET /api/v1/jobs/{job_id}/result` endpoint so the browser always receives a proper filename in `Content-Disposition` and never shows `result` as the save-dialog filename on error responses.

**Architecture:** Replace `JSONResponse` error branches with `PlainTextResponse` to avoid triggering the browser's file-download flow; add a null-guard for `input_filename`; replace fragile `str.replace(".json", "")` with `os.path.splitext`.

**Tech Stack:** Python 3.12+, FastAPI, Starlette, pytest, httpx (TestClient)

---

## Global Constraints

- All imports follow existing project conventions (`import os`, `from fastapi.responses import PlainTextResponse`).
- Logging pattern: `logger = logging.getLogger(__name__)`.
- Error responses from `download_job_result` must be `PlainTextResponse`, not `JSONResponse`.
- Test assertions verify `Content-Disposition` header and `response.text`, not `response.json()` on error paths.

---

### Task 1: Fix `routes/jobs.py` — download_job_result

**Files:**
- Modify: `src/purl_resolver/routes/jobs.py:1-119`

**Interfaces:**
- Produces: `download_job_result()` now returns `PlainTextResponse` on errors, computes filename via `os.path.splitext`, and guards against `input_filename=None`.

- [ ] **Step 1: Add imports**

Add `import os` and `import logging` after `from __future__ import annotations`. Add `PlainTextResponse` to the FastAPI responses import. Add `logger = logging.getLogger(__name__)` at module level.

Change the import block (lines 3-8):
```python
import json
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter, File, Form, Request, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
```

Add after line 14 (after `from ..job_manager import JobManager`):
```python
logger = logging.getLogger(__name__)
```

- [ ] **Step 2: Replace error responses in `download_job_result` with `PlainTextResponse`**

Current code (lines 99-119):
```python
@router.get("/api/v1/jobs/{job_id}/result")
async def download_job_result(request: Request, job_id: str) -> FileResponse:
    manager = _get_manager(request)
    if manager is None:
        return _UNAVAILABLE
    record = await manager.get_job(job_id)
    if not record:
        return JSONResponse(status_code=404, content={"error": "job_not_found"})
    if record.status != "completed":
        return JSONResponse(
            status_code=400,
            content={"error": "result_not_ready", "status": record.status},
        )
    path = Path(record.result_path) if record.result_path else None
    if not path or not path.exists():
        return JSONResponse(status_code=404, content={"error": "result_file_not_found"})
    return FileResponse(
        path=path,
        filename=record.input_filename.replace(".json", "") + "_enriched.json",
        media_type="application/json",
    )
```

Replace the entire function body with:
```python
@router.get("/api/v1/jobs/{job_id}/result")
async def download_job_result(request: Request, job_id: str) -> FileResponse:
    manager = _get_manager(request)
    if manager is None:
        return PlainTextResponse("job_queue_unavailable", status_code=503)
    record = await manager.get_job(job_id)
    if not record:
        return PlainTextResponse("job_not_found", status_code=404)
    if record.status != "completed":
        return PlainTextResponse(
            f"result_not_ready: {record.status}", status_code=400,
        )
    path = Path(record.result_path) if record.result_path else None
    if not path or not path.exists():
        return PlainTextResponse("result_file_not_found", status_code=404)
    filename = record.input_filename
    if not filename:
        logger.warning("Job %s has no input_filename, using fallback", job_id)
        filename = "unknown"
    filename = os.path.splitext(filename)[0] + "_enriched.json"
    return FileResponse(
        path=path,
        filename=filename,
        media_type="application/json",
    )
```

- [ ] **Step 3: Run existing tests to verify no regression**

```bash
.venv/bin/python -m pytest tests/test_routes_jobs.py::TestDownloadResult -v
```

Expected: all tests pass (tests will be updated in Task 2).

---

### Task 2: Update existing tests and add new tests for download endpoint

**Files:**
- Modify: `tests/test_routes_jobs.py:114-149`

**Interfaces:**
- Consumes: `download_job_result()` now returns `PlainTextResponse` on errors and uses `os.path.splitext`.
- Produces: New tests verifying `Content-Disposition` header, `input_filename=None` fallback, and 404 plain text response.

- [ ] **Step 1: Update `test_not_completed` for PlainTextResponse**

Replace lines 127-134:
```python
    def test_not_completed(self, client, mock_manager):
        mock_manager.get_job.return_value = JobRecord(
            id="job-1", type="sbom_enrich", status="running",
        )
        response = client.get("/api/v1/jobs/job-1/result")
        assert response.status_code == 400
        assert response.text == "result_not_ready: running"
```

- [ ] **Step 2: Update `test_result_file_missing` for PlainTextResponse**

Replace lines 141-149:
```python
    def test_result_file_missing(self, client, mock_manager):
        mock_manager.get_job.return_value = JobRecord(
            id="job-1", type="sbom_enrich", status="completed",
            result_path=None,
            input_filename="test.json",
        )
        response = client.get("/api/v1/jobs/job-1/result")
        assert response.status_code == 404
        assert response.text == "result_file_not_found"
```

- [ ] **Step 3: Add `test_download_content_disposition`**

Add after `test_completed` in class `TestDownloadResult`:
```python
    def test_download_content_disposition(self, client, mock_manager, tmp_path):
        result_file = tmp_path / "result.json"
        result_file.write_text(json.dumps({"enriched": True}))
        mock_manager.get_job.return_value = JobRecord(
            id="job-1", type="sbom_enrich", status="completed",
            result_path=str(result_file),
            input_filename="my-sbom.json",
        )
        response = client.get("/api/v1/jobs/job-1/result")
        assert response.status_code == 200
        cd = response.headers.get("content-disposition")
        assert cd is not None
        assert "my-sbom_enriched.json" in cd
```

- [ ] **Step 4: Add `test_download_input_filename_none`**

Add after the new content-disposition test:
```python
    def test_download_input_filename_none(self, client, mock_manager, tmp_path):
        result_file = tmp_path / "result.json"
        result_file.write_text(json.dumps({"enriched": True}))
        mock_manager.get_job.return_value = JobRecord(
            id="job-1", type="sbom_enrich", status="completed",
            result_path=str(result_file),
            input_filename=None,
        )
        response = client.get("/api/v1/jobs/job-1/result")
        assert response.status_code == 200
        cd = response.headers.get("content-disposition")
        assert cd is not None
        assert "unknown_enriched.json" in cd
```

- [ ] **Step 5: Add `test_download_result_file_not_found`**

Add after the None test:
```python
    def test_download_result_file_not_found(self, client, mock_manager):
        mock_manager.get_job.return_value = JobRecord(
            id="job-1", type="sbom_enrich", status="completed",
            result_path="/nonexistent/path/result.json",
            input_filename="test.json",
        )
        response = client.get("/api/v1/jobs/job-1/result")
        assert response.status_code == 404
        assert response.text == "result_file_not_found"
```

- [ ] **Step 6: Run all tests to verify**

```bash
.venv/bin/python -m pytest tests/test_routes_jobs.py -v
```

Expected: all tests pass (including `TestDownloadResult` with the updated and new tests).
