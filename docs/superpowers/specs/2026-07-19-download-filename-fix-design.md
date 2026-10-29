# Download filename fix

- **Status:** approved
- **Created:** 2026-07-19
- **Related specs:** 2026-07-10-sbom-enrichment-job-queue-design.md

## Problem

When downloading an enriched SBOM via the `GET /api/v1/jobs/{job_id}/result` endpoint, under certain conditions the browser shows `result` as the filename in the save dialog instead of the expected `<input_filename>_enriched.json`.

## Root cause

The browser derives the filename from the `Content-Disposition` header. If the server returns anything other than a successful `FileResponse` with a `filename` parameter (e.g., 404, 400, 500), the response lacks `Content-Disposition`, and the browser falls back to the last URL path segment — `result`.

Three scenarios trigger this:

1. **`input_filename` is `None`** — `record.input_filename.replace(...)` raises `AttributeError` → unhandled 500.
2. **Result file missing or path `None`** — 404 JSON response.
3. **Job not completed** — 400 JSON response.

## Changes

### 1. `src/purl_resolver/routes/jobs.py` — `download_job_result`

#### Add `import os` and configure logger

Ensure `os` is imported for `os.path.splitext`. The module already has `import logging` and `logger`.

#### Null-guard for `input_filename`

Before using `input_filename` for the download name, check for `None`. If `None`:
- Log a warning with the job ID.
- Fall back to `"unknown"`.

#### Replace `str.replace(".json", "")` with `os.path.splitext`

`str.replace(".json", "")` replaces the first occurrence of `.json` anywhere in the string, not just the extension. Use `os.path.splitext(filename)[0]` to correctly strip only the final extension.

#### Change error responses from `JSONResponse` to `PlainTextResponse`

All error branches in `download_job_result` currently return `JSONResponse` without `Content-Disposition`. Change them to `PlainTextResponse` so the browser displays the error text inline rather than triggering a file download dialog with filename `result`.

Affected branches:
- `manager is None` → 503 `"job_queue_unavailable"`
- `record not found` → 404 `"job_not_found"`
- `record.status != "completed"` → 400 `"result_not_ready"`
- `result_path is None or file missing` → 404 `"result_file_not_found"`

### 2. `tests/test_routes_jobs.py` — new tests

| Test | What it verifies |
|---|---|
| `test_download_content_disposition` | Successful download returns `Content-Disposition` header with filename ending in `_enriched.json`, and the basename matches the original `input_filename`. |
| `test_download_input_filename_none` | `input_filename=None` returns 200 with fallback filename `unknown_enriched.json` in `Content-Disposition`. |
| `test_download_result_file_not_found` | `result_path` pointing to a non-existent file returns 404 with body `"result_file_not_found"`. |

## Not in scope

- TTL race condition (cleanup deleting files between button render and click) — the error responses now show text instead of silent `result` download, which is sufficient mitigation.
- Frontend changes — the `<a download>` pattern is correct; no changes needed.
- Other endpoints — only `download_job_result` is affected.
