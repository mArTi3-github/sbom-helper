# SBOM Enrichment Job Queue — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace synchronous `POST /api/v1/resolve/sbom` with an async job-queue system where SBOM enrichment runs in a background asyncio worker, results are persisted to disk + database, and users can track/cancel/delete jobs via new API endpoints and a reworked frontend.

**Architecture:** Single-process asyncio worker using `asyncio.Queue`, `jobs` table in existing PostgreSQL, results on disk at `data/jobs/{job_id}/`. Old synchronous endpoint is removed entirely. Frontend polls job status and displays job history.

**Tech Stack:** FastAPI, asyncpg, Vue 3 + TypeScript, pytest + vitest

## Global Constraints

- No new external services (Redis, Celery, RabbitMQ)
- Python 3.12+, PostgreSQL required for jobs (no InMemoryCache fallback for jobs)
- Follow existing code patterns: Storage ABC for resolved_purls, JobRepository as separate class for jobs table
- Follow frontend test patterns: vitest with happy-dom, mountWithI18n helper, vi.mock for API modules
- New UI text must be added to both `en.json` and `ru.json`
- YAGNI — one sequential worker, no retry/backoff for jobs themselves

---

### Task 1: Database schema + JobRepository

**Files:**
- Modify: `src/purl_resolver/storage/schema.sql`
- Create: `src/purl_resolver/job_repository.py`
- Create: `tests/test_job_repository.py`

**Interfaces:**
- Consumes: `asyncpg.Pool` (from `storage.postgres`)
- Produces: `JobRepository` class with methods for full CRUD + status queries

- [ ] **Step 1: Add `jobs` table DDL to schema.sql**

Append to `src/purl_resolver/storage/schema.sql`:

```sql
CREATE TABLE IF NOT EXISTS jobs (
    id               TEXT PRIMARY KEY,
    type             TEXT NOT NULL,
    status           TEXT NOT NULL,
    progress_current INTEGER DEFAULT 0,
    progress_total   INTEGER DEFAULT 0,
    params_json      TEXT,
    input_filename   TEXT,
    result_path      TEXT,
    summary_json     TEXT,
    results_json     TEXT,
    error_message    TEXT,
    cancel_requested INTEGER DEFAULT 0,
    created_at       TEXT NOT NULL,
    started_at       TEXT,
    finished_at      TEXT
);
```

- [ ] **Step 2: Define `JobRecord` dataclass**

In `src/purl_resolver/job_repository.py`:

```python
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import asyncpg


@dataclass
class JobRecord:
    id: str
    type: str
    status: str  # queued | running | completed | failed | cancelled
    progress_current: int = 0
    progress_total: int = 0
    params_json: str | None = None
    input_filename: str | None = None
    result_path: str | None = None
    summary_json: str | None = None
    results_json: str | None = None
    error_message: str | None = None
    cancel_requested: int = 0
    created_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None

    def get_params(self) -> dict[str, Any]:
        return json.loads(self.params_json) if self.params_json else {}

    def get_summary(self) -> dict[str, Any] | None:
        return json.loads(self.summary_json) if self.summary_json else None

    def get_results(self) -> list[dict[str, Any]] | None:
        return json.loads(self.results_json) if self.results_json else None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())
```

- [ ] **Step 3: Implement `JobRepository`**

In `src/purl_resolver/job_repository.py`:

```python
_COLUMNS = (
    "id", "type", "status", "progress_current", "progress_total",
    "params_json", "input_filename", "result_path",
    "summary_json", "results_json", "error_message",
    "cancel_requested", "created_at", "started_at", "finished_at"
)

class JobRepository:

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create(self, record: JobRecord) -> None:
        record.created_at = _now()
        async with self._pool.acquire() as conn:
            await conn.execute(
                f"INSERT INTO jobs ({', '.join(_COLUMNS)}) "
                f"VALUES ({', '.join(f'${i+1}' for i in range(len(_COLUMNS)))})",
                *[getattr(record, c) for c in _COLUMNS]
            )

    async def get(self, job_id: str) -> JobRecord | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM jobs WHERE id = $1", job_id)
        return self._row_to_record(row) if row else None

    async def list(
        self,
        type_filter: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[JobRecord]:
        if type_filter:
            query = "SELECT * FROM jobs WHERE type = $1 ORDER BY created_at DESC LIMIT $2 OFFSET $3"
            params = [type_filter, limit, offset]
        else:
            query = "SELECT * FROM jobs ORDER BY created_at DESC LIMIT $1 OFFSET $2"
            params = [limit, offset]
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
        return [self._row_to_record(r) for r in rows]

    async def update_status(
        self,
        job_id: str,
        status: str,
        **fields: Any,
    ) -> None:
        set_parts = ["status = $1"]
        values: list[Any] = [status]
        i = 2
        for key, val in fields.items():
            set_parts.append(f"{key} = ${i}")
            values.append(val)
            i += 1
        values.append(job_id)
        async with self._pool.acquire() as conn:
            await conn.execute(
                f"UPDATE jobs SET {', '.join(set_parts)} WHERE id = ${i}",
                *values
            )

    async def delete(self, job_id: str) -> bool:
        async with self._pool.acquire() as conn:
            result = await conn.execute("DELETE FROM jobs WHERE id = $1", job_id)
        return result != "DELETE 0"

    async def get_queued(self) -> list[JobRecord]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM jobs WHERE status = 'queued' ORDER BY created_at ASC"
            )
        return [self._row_to_record(r) for r in rows]

    async def get_stuck_running(self) -> list[JobRecord]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM jobs WHERE status = 'running'"
            )
        return [self._row_to_record(r) for r in rows]

    async def get_expired(self, ttl_hours: int) -> list[JobRecord]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM jobs WHERE status IN ('completed','failed','cancelled') "
                "AND finished_at IS NOT NULL "
                "AND finished_at < NOW() - make_interval(hours => $1)",
                ttl_hours
            )
        return [self._row_to_record(r) for r in rows]

    @staticmethod
    def _row_to_record(row: asyncpg.Record) -> JobRecord:
        return JobRecord(**{k: row[k] for k in _COLUMNS})
```

- [ ] **Step 4: Write tests for JobRepository**

Create `tests/test_job_repository.py`:

```python
from __future__ import annotations

from unittest.mock import ANY, AsyncMock, MagicMock

import pytest

from purl_resolver.job_repository import JobRecord, JobRepository, _new_id


class MockRecord:
    """Simulates asyncpg.Record for testing."""
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


@pytest.fixture
def repo():
    pool = AsyncMock()
    pool.acquire = AsyncMock()
    pool.acquire.return_value.__aenter__ = AsyncMock()
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return JobRepository(pool)


class TestJobRepository:
    @pytest.mark.asyncio
    async def test_create_and_get(self, repo):
        job_id = _new_id()
        record = JobRecord(id=job_id, type="sbom_enrich", status="queued")
        repo._pool.acquire.return_value.__aenter__.return_value.fetchrow.return_value = MockRecord(
            id=job_id, type="sbom_enrich", status="queued",
            progress_current=0, progress_total=0,
            params_json=None, input_filename=None,
            result_path=None, summary_json=None, results_json=None,
            error_message=None, cancel_requested=0,
            created_at="2026-07-10T12:00:00", started_at=None, finished_at=None,
        )

        await repo.create(record)
        fetched = await repo.get(job_id)

        assert fetched is not None
        assert fetched.id == job_id
        assert fetched.status == "queued"

    @pytest.mark.asyncio
    async def test_get_not_found(self, repo):
        repo._pool.acquire.return_value.__aenter__.return_value.fetchrow.return_value = None
        fetched = await repo.get("nonexistent")
        assert fetched is None

    @pytest.mark.asyncio
    async def test_update_status(self, repo):
        conn = repo._pool.acquire.return_value.__aenter__.return_value
        await repo.update_status("job-1", "running", started_at="2026-07-10T12:00:00")
        conn.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_success(self, repo):
        conn = repo._pool.acquire.return_value.__aenter__.return_value
        conn.execute.return_value = "DELETE 1"
        result = await repo.delete("job-1")
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_not_found(self, repo):
        conn = repo._pool.acquire.return_value.__aenter__.return_value
        conn.execute.return_value = "DELETE 0"
        result = await repo.delete("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_get_queued(self, repo):
        conn = repo._pool.acquire.return_value.__aenter__.return_value
        conn.fetch.return_value = []
        results = await repo.get_queued()
        assert results == []

    @pytest.mark.asyncio
    async def test_get_stuck_running(self, repo):
        conn = repo._pool.acquire.return_value.__aenter__.return_value
        conn.fetch.return_value = []
        results = await repo.get_stuck_running()
        assert results == []

    @pytest.mark.asyncio
    async def test_get_expired(self, repo):
        conn = repo._pool.acquire.return_value.__aenter__.return_value
        conn.fetch.return_value = []
        results = await repo.get_expired(ttl_hours=24)
        assert results == []

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_job_repository.py -v`
Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/purl_resolver/storage/schema.sql src/purl_resolver/job_repository.py tests/test_job_repository.py
git commit -m "feat: add jobs table and JobRepository"
```

---

### Task 2: JobManager — async worker, queue, recovery, cleanup

**Files:**
- Create: `src/purl_resolver/job_manager.py`
- Create: `tests/test_job_manager.py`

**Interfaces:**
- Consumes: `JobRepository`, asyncpg Pool, `PurlResolutionService`, settings store, file system at `data/jobs/`
- Produces: `JobManager` class with `start()`, `stop()`, `create_job()`, `get_job()`, `list_jobs()`, `cancel_job()`, `delete_job()`

- [ ] **Step 1: Write `JobManager` class skeleton**

```python
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from .job_repository import JobRecord, JobRepository, _new_id, _now
from .sbom_enrichment import SbomEnrichmentPipeline
from .sbom.parser import SbomParseError

logger = logging.getLogger(__name__)

JOBS_DIR = Path("/app/data/jobs")


class JobManager:

    def __init__(
        self,
        pool: asyncpg.Pool,
        resolution_service: PurlResolutionService,
        job_ttl_hours: int = 24,
    ) -> None:
        self._repo = JobRepository(pool)
        self._resolution_service = resolution_service
        self._job_ttl_hours = job_ttl_hours
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None
        self._cleanup_task: asyncio.Task | None = None
```

- [ ] **Step 2: Implement `start()` — recovery + start workers**

```python
    async def start(self) -> None:
        JOBS_DIR.mkdir(parents=True, exist_ok=True)

        # Recover stuck running jobs
        stuck = await self._repo.get_stuck_running()
        for job in stuck:
            await self._repo.update_status(
                job.id, "failed",
                error_message="Server restarted during processing",
                finished_at=_now(),
            )
            logger.warning("Marked stuck job %s as failed", job.id)

        # Re-enqueue queued jobs
        queued = await self._repo.get_queued()
        for job in queued:
            await self._queue.put(job.id)
            logger.info("Re-enqueued job %s", job.id)

        # Start worker
        self._worker_task = asyncio.create_task(self._run_worker())
        # Start cleanup loop
        self._cleanup_task = asyncio.create_task(self._run_cleanup())
```

- [ ] **Step 3: Implement `stop()`**

```python
    async def stop(self) -> None:
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
```

- [ ] **Step 4: Implement `create_job()`, `get_job()`, `list_jobs()`, `cancel_job()`, `delete_job()`**

```python
    def update_ttl(self, ttl_hours: int) -> None:
        self._job_ttl_hours = ttl_hours

    async def create_job(
        self,
        input_bytes: bytes,
        input_filename: str,
        params: dict,
    ) -> JobRecord:
        job_id = _new_id()
        job_dir = JOBS_DIR / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        input_path = job_dir / "input.json"
        input_path.write_bytes(input_bytes)

        record = JobRecord(
            id=job_id,
            type="sbom_enrich",
            status="queued",
            params_json=json.dumps(params),
            input_filename=input_filename,
        )
        await self._repo.create(record)
        await self._queue.put(job_id)
        logger.info("Created job %s (file: %s)", job_id, input_filename)
        return record

    async def get_job(self, job_id: str) -> JobRecord | None:
        return await self._repo.get(job_id)

    async def list_jobs(self, limit: int = 20, offset: int = 0) -> list[JobRecord]:
        return await self._repo.list(type_filter="sbom_enrich", limit=limit, offset=offset)

    async def cancel_job(self, job_id: str) -> bool:
        record = await self._repo.get(job_id)
        if not record or record.status in ("completed", "failed", "cancelled"):
            return False
        await self._repo.update_status(job_id, record.status, cancel_requested=1)
        return True

    async def delete_job(self, job_id: str) -> bool:
        record = await self._repo.get(job_id)
        if not record:
            return False
        # Remove files
        job_dir = JOBS_DIR / job_id
        if job_dir.exists():
            import shutil
            shutil.rmtree(job_dir)
        await self._repo.delete(job_id)
        return True
```

- [ ] **Step 5: Implement `_run_worker()`**

```python
    async def _run_worker(self) -> None:
        while True:
            job_id = await self._queue.get()
            try:
                await self._process_job(job_id)
            except Exception:
                logger.exception("Unhandled error processing job %s", job_id)
            finally:
                self._queue.task_done()

    async def _process_job(self, job_id: str) -> None:
        record = await self._repo.get(job_id)
        if not record:
            return

        # Check cancellation before starting
        if record.cancel_requested:
            await self._repo.update_status(
                job_id, "cancelled", finished_at=_now()
            )
            job_dir = JOBS_DIR / job_id
            if job_dir.exists():
                import shutil
                shutil.rmtree(job_dir)
            return

        await self._repo.update_status(
            job_id, "running", started_at=_now()
        )

        try:
            input_path = JOBS_DIR / job_id / "input.json"
            sbom_data = json.loads(input_path.read_text())

            params = record.get_params()
            remove_unresolved = params.get("remove_unresolved_no_subcomponents", False)
            ignore_patterns = params.get("ignore_patterns")

            pipeline = SbomEnrichmentPipeline(self._resolution_service)

            # Total is the number of components after collect — approximated here
            # by the pipeline itself. We set progress_total after parsing.
            # For now we update progress after resolution completes.

            result = await pipeline.process(
                sbom_data,
                remove_unresolved_no_subcomponents=remove_unresolved,
                ignore_patterns=ignore_patterns,
            )

            # Save result to disk
            result_path = JOBS_DIR / job_id / "result.json"
            result_path.write_text(
                json.dumps(result.enriched_sbom, indent=2)
            )

            # Save summary + results to DB
            await self._repo.update_status(
                job_id, "completed",
                result_path=str(result_path),
                summary_json=json.dumps(result.report),
                results_json=json.dumps(result.report.get("results", [])),
                finished_at=_now(),
            )

        except SbomParseError as e:
            await self._repo.update_status(
                job_id, "failed",
                error_message=f"Invalid SBOM: {e}",
                finished_at=_now(),
            )
        except Exception as e:
            await self._repo.update_status(
                job_id, "failed",
                error_message=str(e),
                finished_at=_now(),
            )
```

**Note on progress tracking:** The current `SbomEnrichmentPipeline.process()` does not expose progress callbacks. Adding per-component progress requires refactoring the pipeline. For the initial implementation, progress tracking is omitted (progress_current stays 0). A follow-up task can add fine-grained progress. The total number of components needing enrichment is available but not wired through yet.

- [ ] **Step 6: Implement `_run_cleanup()`**

```python
    async def _run_cleanup(self) -> None:
        while True:
            await asyncio.sleep(60)
            try:
                expired = await self._repo.get_expired(self._job_ttl_hours)
                for job in expired:
                    job_dir = JOBS_DIR / job.id
                    if job_dir.exists():
                        import shutil
                        shutil.rmtree(job_dir)
                    await self._repo.delete(job.id)
                    logger.info("Cleaned up expired job %s", job.id)
            except Exception:
                logger.exception("Error during job cleanup")
```

- [ ] **Step 7: Write tests for JobManager**

Create `tests/test_job_manager.py` with tests for:
- `create_job()` creates record + puts on queue
- `get_job()` returns record
- `list_jobs()` returns paginated records
- `cancel_job()` sets `cancel_requested` flag
- `delete_job()` removes files + record
- `start()` recovers stuck `running` → `failed`
- `start()` re-enqueues `queued` jobs
- `stop()` cancels worker task

Use `AsyncMock` for `JobRepository` and fake file system.

- [ ] **Step 8: Run tests**

Run: `pytest tests/test_job_manager.py -v`
Expected: all tests PASS

- [ ] **Step 9: Commit**

```bash
git add src/purl_resolver/job_manager.py tests/test_job_manager.py
git commit -m "feat: add JobManager with async worker, recovery, cleanup"
```

---

### Task 3: Settings — add job_ttl_hours

**Files:**
- Modify: `src/purl_resolver/settings_store.py`
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/views/Settings.vue`
- Modify: `frontend/src/i18n/locales/en.json`
- Modify: `frontend/src/i18n/locales/ru.json`

**Interfaces:**
- Consumes: existing AppSettings pattern
- Produces: `AppSettings.job_ttl_hours` field available in settings API

- [ ] **Step 1: Add `job_ttl_hours` to `AppSettings`**

In `src/purl_resolver/settings_store.py`, add field:

```python
job_ttl_hours: int = Field(default=24, ge=1, le=720)
```

- [ ] **Step 2: Add to frontend types**

In `frontend/src/types/api.ts`:

Add to `SettingsResponse`:
```ts
job_ttl_hours: number
```

Add to `SettingsUpdate`:
```ts
job_ttl_hours?: number
```

- [ ] **Step 3: Add UI field to Settings.vue**

In `frontend/src/views/Settings.vue`, add a new section (in the "Network & Performance" section or create a new "Job Management" section):

```html
<div class="card">
  <div class="card-title">{{ t('settings.jobManagement.title') }}</div>
  <div class="field-row">
    <div class="field-label">
      <label>{{ t('settings.jobManagement.ttlLabel') }}</label>
      <p class="field-desc">{{ t('settings.jobManagement.ttlDesc') }}</p>
    </div>
    <div class="field-input">
      <input type="number" v-model.number="settings.job_ttl_hours" min="1" max="720" />
    </div>
  </div>
</div>
```

- [ ] **Step 4: Add i18n keys**

In `frontend/src/i18n/locales/en.json`, add under `settings`:
```json
"jobManagement": {
  "title": "Job Management",
  "ttlLabel": "Job result TTL (hours)",
  "ttlDesc": "Completed, cancelled, and failed jobs are automatically deleted after this many hours."
}
```

In `frontend/src/i18n/locales/ru.json`, add under `settings`:
```json
"jobManagement": {
  "title": "Управление задачами",
  "ttlLabel": "Время жизни результатов задач (часы)",
  "ttlDesc": "Завершённые, отменённые и завершившиеся ошибкой задачи автоматически удаляются через указанное количество часов."
}
```

- [ ] **Step 5: Run backend tests**

Run: `pytest tests/ -v -x`
Expected: all tests PASS

- [ ] **Step 6: Run frontend tests**

Run: `npm run test -- --run` in `frontend/`
Expected: all tests PASS

- [ ] **Step 7: Commit**

```bash
git add src/purl_resolver/settings_store.py frontend/src/types/api.ts frontend/src/views/Settings.vue frontend/src/i18n/locales/en.json frontend/src/i18n/locales/ru.json
git commit -m "feat: add job_ttl_hours setting"
```

---

### Task 4: API routes for jobs

**Files:**
- Create: `src/purl_resolver/routes/jobs.py`
- Create: `tests/test_routes_jobs.py`

**Interfaces:**
- Consumes: `request.app.state.job_manager` (JobManager)
- Produces: 6 API endpoints for job lifecycle

- [ ] **Step 1: Create routes/jobs.py**

```python
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import JSONResponse, FileResponse

from ..config import sbom_settings
from ..job_manager import JobManager

router = APIRouter()


@router.post("/api/v1/jobs/sbom-enrich", status_code=status.HTTP_202_ACCEPTED)
async def create_sbom_enrich_job(
    request: Request,
    file: UploadFile = File(...),
    remove_unresolved_no_subcomponents: bool = Form(False),
    ignore_patterns: str | None = Form(None),
) -> JSONResponse:
    raw = await file.read()
    if len(raw) > sbom_settings.max_file_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={
                "error": "file_too_large",
                "max_size_mb": sbom_settings.max_file_size // (1024 * 1024),
            },
        )

    # Validate JSON parseability
    try:
        json.loads(raw)
    except json.JSONDecodeError:
        return JSONResponse(status_code=400, content={"error": "invalid_json"})

    parsed_patterns = None
    if ignore_patterns:
        try:
            parsed_patterns = json.loads(ignore_patterns)
            if not isinstance(parsed_patterns, list):
                parsed_patterns = None
        except json.JSONDecodeError:
            parsed_patterns = None

    params = {
        "remove_unresolved_no_subcomponents": remove_unresolved_no_subcomponents,
    }
    if parsed_patterns:
        params["ignore_patterns"] = parsed_patterns

    manager: JobManager = request.app.state.job_manager
    job = await manager.create_job(raw, file.filename or "unknown.json", params)

    return JSONResponse(content={"job_id": job.id, "status": job.status})


@router.get("/api/v1/jobs/{job_id}")
async def get_job(request: Request, job_id: str) -> JSONResponse:
    manager: JobManager = request.app.state.job_manager
    record = await manager.get_job(job_id)
    if not record:
        raise HTTPException(status_code=404, content={"error": "job_not_found"})
    return JSONResponse(content={
        "job_id": record.id,
        "type": record.type,
        "status": record.status,
        "progress_current": record.progress_current,
        "progress_total": record.progress_total,
        "input_filename": record.input_filename,
        "summary": record.get_summary(),
        "results": record.get_results(),
        "error_message": record.error_message,
        "created_at": record.created_at,
        "started_at": record.started_at,
        "finished_at": record.finished_at,
    })


@router.get("/api/v1/jobs/{job_id}/result")
async def download_job_result(request: Request, job_id: str) -> FileResponse:
    manager: JobManager = request.app.state.job_manager
    record = await manager.get_job(job_id)
    if not record:
        raise HTTPException(status_code=404, content={"error": "job_not_found"})
    if record.status != "completed":
        raise HTTPException(
            status_code=400,
            content={"error": "result_not_ready", "status": record.status},
        )
    path = Path(record.result_path) if record.result_path else None
    if not path or not path.exists():
        raise HTTPException(status_code=404, content={"error": "result_file_not_found"})
    return FileResponse(
        path=path,
        filename=record.input_filename.replace(".json", "") + "_enriched.json",
        media_type="application/json",
    )


@router.post("/api/v1/jobs/{job_id}/cancel")
async def cancel_job(request: Request, job_id: str) -> JSONResponse:
    manager: JobManager = request.app.state.job_manager
    success = await manager.cancel_job(job_id)
    if not success:
        record = await manager.get_job(job_id)
        if not record:
            raise HTTPException(status_code=404, content={"error": "job_not_found"})
        raise HTTPException(
            status_code=409,
            content={"error": "job_already_terminal", "status": record.status},
        )
    return JSONResponse(content={"job_id": job_id, "status": "cancelled"})


@router.delete("/api/v1/jobs/{job_id}")
async def delete_job(request: Request, job_id: str) -> JSONResponse:
    manager: JobManager = request.app.state.job_manager
    success = await manager.delete_job(job_id)
    if not success:
        raise HTTPException(status_code=404, content={"error": "job_not_found"})
    return JSONResponse(content={"job_id": job_id, "deleted": True})


@router.get("/api/v1/jobs")
async def list_jobs(
    request: Request,
    limit: int = 20,
    offset: int = 0,
) -> JSONResponse:
    manager: JobManager = request.app.state.job_manager
    records = await manager.list_jobs(limit=limit, offset=offset)
    return JSONResponse(content={
        "jobs": [
            {
                "job_id": r.id,
                "type": r.type,
                "status": r.status,
                "progress_current": r.progress_current,
                "progress_total": r.progress_total,
                "input_filename": r.input_filename,
                "summary": r.get_summary(),
                "error_message": r.error_message,
                "created_at": r.created_at,
                "started_at": r.started_at,
                "finished_at": r.finished_at,
            }
            for r in records
        ],
    })
```

- [ ] **Step 2: Write tests for job routes**

Create `tests/test_routes_jobs.py`. Mock the `JobManager` at `request.app.state.job_manager`. Test:

- `POST /api/v1/jobs/sbom-enrich` — success (202)
- `POST /api/v1/jobs/sbom-enrich` — file too large (413)
- `POST /api/v1/jobs/sbom-enrich` — invalid JSON (400)
- `GET /api/v1/jobs/{id}` — existing job (200)
- `GET /api/v1/jobs/{id}` — not found (404)
- `GET /api/v1/jobs/{id}/result` — completed (200, FileResponse)
- `GET /api/v1/jobs/{id}/result` — not completed (400)
- `POST /api/v1/jobs/{id}/cancel` — success (200)
- `POST /api/v1/jobs/{id}/cancel` — terminal status (409)
- `DELETE /api/v1/jobs/{id}` — success (200)
- `DELETE /api/v1/jobs/{id}` — not found (404)
- `GET /api/v1/jobs` — list (200)

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_routes_jobs.py -v`
Expected: all tests PASS

- [ ] **Step 4: Commit**

```bash
git add src/purl_resolver/routes/jobs.py tests/test_routes_jobs.py
git commit -m "feat: add job lifecycle API routes"
```

---

### Task 5: Wire up in main.py + router.py, remove old endpoint

**Files:**
- Modify: `src/purl_resolver/router.py`
- Modify: `src/purl_resolver/routes/resolve.py`
- Modify: `src/purl_resolver/main.py`
- Modify: `tests/test_sbom_integration.py`
- Delete: tests for removed synchronous endpoint

- [ ] **Step 1: Remove `/api/v1/resolve/sbom` from routes/resolve.py**

Delete lines 43-109 (the `resolve_sbom_endpoint` function and its decorator). Keep the `resolve_endpoint` for single PURL resolution.

- [ ] **Step 2: Remove old route from router**

In `src/purl_resolver/router.py`, the old route is already included via `resolve_router`. No change needed to the include — the route is simply removed from `routes/resolve.py`.

Add the jobs router:

```python
from .routes.jobs import router as jobs_router

router.include_router(jobs_router)
```

- [ ] **Step 3: Add JobManager to main.py lifespan**

In `src/purl_resolver/main.py`:

Import:
```python
from .job_manager import JobManager
```

In `lifespan`, after creating `resolution_service` and before the `try: yield`:

```python
    # Job manager for async SBOM enrichment
    if isinstance(app.state.storage, PostgresCache):
        app.state.job_manager = JobManager(
            pool=pool,
            resolution_service=app.state.resolution_service,
            job_ttl_hours=app_settings.job_ttl_hours,
        )
        await app.state.job_manager.start()
        logger.info("Job manager started")
    else:
        logger.warning("PostgreSQL unavailable — job queue disabled")
        app.state.job_manager = None
```

In the `finally` block, stop the job manager:

```python
        if app.state.job_manager is not None:
            await app.state.job_manager.stop()
```

- [ ] **Step 4: Update tests for removed endpoint**

In `tests/test_sbom_integration.py`:
- Remove tests that call `POST /api/v1/resolve/sbom`
- Tests for the pipeline itself (`TestValidateExistingRefs`) use the pipeline class directly and should be kept
- Tests for SBOM parsing validation can be adapted to call the new job endpoint or tested at the pipeline level

- [ ] **Step 5: Run all backend tests**

Run: `pytest tests/ -v -x`
Expected: all tests PASS (some may be removed/adapted in step 4)

- [ ] **Step 6: Commit**

```bash
git add src/purl_resolver/router.py src/purl_resolver/routes/resolve.py src/purl_resolver/main.py tests/test_sbom_integration.py
git commit -m "feat: wire JobManager into app lifespan, remove old sync sbom endpoint"
```

---

### Task 6: Frontend — types + API module for jobs

**Files:**
- Create: `frontend/src/api/jobs.ts`
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/api/sbom.ts`

- [ ] **Step 1: Add job types to api.ts**

```ts
export type JobStatus = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'

export interface JobRecord {
  job_id: string
  type: string
  status: JobStatus
  progress_current: number
  progress_total: number
  input_filename: string | null
  summary: SbomSummary | null
  results: SbomResultItem[] | null
  error_message: string | null
  created_at: string | null
  started_at: string | null
  finished_at: string | null
}

export interface JobListResponse {
  jobs: JobRecord[]
}

export interface JobCreateResponse {
  job_id: string
  status: JobStatus
}
```

- [ ] **Step 2: Create api/jobs.ts**

```ts
import { apiFetch } from './client'
import type { JobRecord, JobCreateResponse, JobListResponse } from '../types/api'

export function createSbomEnrichJob(
  file: File,
  removeUnresolved: boolean,
  ignorePatterns: IgnorePatternItem[],
): Promise<JobCreateResponse> {
  const formData = new FormData()
  formData.append('file', file)
  if (removeUnresolved) formData.append('remove_unresolved_no_subcomponents', 'true')
  if (ignorePatterns.length > 0) formData.append('ignore_patterns', JSON.stringify(ignorePatterns))
  return apiFetch<JobCreateResponse>('/api/v1/jobs/sbom-enrich', {
    method: 'POST',
    body: formData,
  })
}

export function getJob(jobId: string): Promise<JobRecord> {
  return apiFetch<JobRecord>(`/api/v1/jobs/${jobId}`)
}

export function cancelJob(jobId: string): Promise<{ job_id: string; status: string }> {
  return apiFetch(`/api/v1/jobs/${jobId}/cancel`, { method: 'POST' })
}

export function deleteJob(jobId: string): Promise<{ job_id: string; deleted: boolean }> {
  return apiFetch(`/api/v1/jobs/${jobId}`, { method: 'DELETE' })
}

export function listJobs(limit = 20, offset = 0): Promise<JobListResponse> {
  return apiFetch<JobListResponse>(`/api/v1/jobs?limit=${limit}&offset=${offset}`)
}

export function downloadJobResultUrl(jobId: string): string {
  return `/api/v1/jobs/${jobId}/result`
}
```

- [ ] **Step 3: Remove `resolveSbom` from api/sbom.ts**

Delete the `resolveSbom` function (lines 16-31). Keep `getIgnorePatterns` and `saveIgnorePatterns`.

Remove the `SbomResponse` import since `resolveSbom` was the only consumer.

- [ ] **Step 4: Run frontend type check**

Run: `npx vue-tsc --noEmit` in `frontend/`
Expected: no type errors

- [ ] **Step 5: Run frontend tests**

Run: `npm run test -- --run` in `frontend/`
Expected: tests that imported `resolveSbom` from `api/sbom.ts` may fail — this is expected; they will be fixed in Task 8.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/jobs.ts frontend/src/types/api.ts frontend/src/api/sbom.ts
git commit -m "feat: add frontend job API module and types"
```

---

### Task 7: Frontend — RecentJobs component

**Files:**
- Create: `frontend/src/components/RecentJobs.vue`
- Create: `frontend/src/components/RecentJobs.test.ts`
- Modify: `frontend/src/i18n/locales/en.json`
- Modify: `frontend/src/i18n/locales/ru.json`

- [ ] **Step 1: Create RecentJobs.vue**

```vue
<template>
  <div class="recent-jobs">
    <div class="recent-jobs-title">{{ t('recentJobs.title') }}</div>
    <div v-if="jobs.length === 0" class="empty-state">{{ t('recentJobs.empty') }}</div>
    <div v-for="job in jobs" :key="job.job_id"
      :class="['job-row', { 'job-active': job.job_id === activeId }]"
      @click="$emit('select', job.job_id)">
      <span :class="['job-status-icon', 'status-' + job.status]">
        <template v-if="job.status === 'queued'">⏳</template>
        <template v-else-if="job.status === 'running'">🔄</template>
        <template v-else-if="job.status === 'completed'">✅</template>
        <template v-else-if="job.status === 'failed'">❌</template>
        <template v-else-if="job.status === 'cancelled'">🚫</template>
      </span>
      <span class="job-filename">{{ job.input_filename || job.job_id }}</span>
      <span class="job-time">{{ formatTime(job.created_at) }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { JobRecord } from '../types/api'

const props = defineProps<{
  jobs: JobRecord[]
  activeId: string | null
}>()

defineEmits<{
  select: [jobId: string]
}>()

const { t } = useI18n()

function formatTime(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleString()
}
</script>
```

- [ ] **Step 2: Write RecentJobs tests**

Create `frontend/src/components/RecentJobs.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { mountWithI18n } from '../tests/i18n'
import RecentJobs from './RecentJobs.vue'
import type { JobRecord } from '../types/api'

const mockJobs: JobRecord[] = [
  { job_id: '1', type: 'sbom_enrich', status: 'completed', progress_current: 0, progress_total: 0, input_filename: 'bom.json', summary: null, results: null, error_message: null, created_at: '2026-07-10T12:00:00', started_at: null, finished_at: null },
  { job_id: '2', type: 'sbom_enrich', status: 'running', progress_current: 5, progress_total: 10, input_filename: 'app.json', summary: null, results: null, error_message: null, created_at: '2026-07-10T12:05:00', started_at: null, finished_at: null },
]

describe('RecentJobs', () => {
  it('renders job rows', () => {
    const wrapper = mountWithI18n(RecentJobs, { props: { jobs: mockJobs, activeId: null } })
    expect(wrapper.findAll('.job-row').length).toBe(2)
  })

  it('highlights active job', () => {
    const wrapper = mountWithI18n(RecentJobs, { props: { jobs: mockJobs, activeId: '1' } })
    expect(wrapper.find('.job-active').exists()).toBe(true)
  })

  it('emits select on click', async () => {
    const wrapper = mountWithI18n(RecentJobs, { props: { jobs: mockJobs, activeId: null } })
    await wrapper.findAll('.job-row')[0].trigger('click')
    expect(wrapper.emitted('select')).toBeTruthy()
    expect(wrapper.emitted('select')![0]).toEqual(['1'])
  })

  it('shows empty state when no jobs', () => {
    const wrapper = mountWithI18n(RecentJobs, { props: { jobs: [], activeId: null } })
    expect(wrapper.text()).toContain('No recent jobs')
  })
})
```

- [ ] **Step 3: Add i18n keys**

In `en.json`:
```json
"recentJobs": {
  "title": "Recent Jobs",
  "empty": "No recent jobs"
}
```

In `ru.json`:
```json
"recentJobs": {
  "title": "Недавние задачи",
  "empty": "Нет недавних задач"
}
```

- [ ] **Step 4: Run frontend tests**

Run: `npm run test -- --run` in `frontend/`
Expected: all new tests PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/RecentJobs.vue frontend/src/components/RecentJobs.test.ts frontend/src/i18n/locales/en.json frontend/src/i18n/locales/ru.json
git commit -m "feat: add RecentJobs component"
```

---

### Task 8: Frontend — rework SbomUpdater.vue

**Files:**
- Modify: `frontend/src/views/SbomUpdater.vue`
- Modify: `frontend/src/views/SbomUpdater.test.ts`
- Modify: `frontend/src/i18n/locales/en.json`
- Modify: `frontend/src/i18n/locales/ru.json`

- [ ] **Step 1: Rewrite the template with jobs panel + details layout**

Replace the template to add:
- Top section: file upload + options (unchanged)
- Bottom section: `RecentJobs` component (top sub-section) + job details (bottom sub-section)
- Job details: spinner for queued/running, cancel button, summary + results for completed, error for failed

Template structure:

```vue
<template>
  <div class="container">
    <h1>{{ t('sbomUpdater.title') }}</h1>
    <p class="subtitle">{{ t('sbomUpdater.subtitle') }}</p>

    <FileUploadZone accept=".json" :max-size="200" @file-selected="onFileSelected" />

    <div class="options-section">
      <label class="checkbox-row">
        <input type="checkbox" v-model="removeUnresolved" />
        <span>{{ t('sbomUpdater.removeUnresolved') }}</span>
      </label>
    </div>

    <div class="card">
      <div class="card-title">{{ t('sbomUpdater.ignorePatterns') }}</div>
      <!-- pattern rows unchanged -->
    </div>

    <div class="toolbar">
      <button :disabled="!selectedFile || submitting" @click="handleProcess">
        {{ t('sbomUpdater.process') }}
      </button>
    </div>

    <!-- Recent Jobs + Details -->
    <div v-if="jobs.length > 0" class="jobs-section">
      <RecentJobs :jobs="jobs" :active-id="activeJobId" @select="selectJob" />
    </div>

    <div v-if="activeJobId && activeJob" class="job-details">
      <!-- queued / running -->
      <div v-if="activeJob.status === 'queued' || activeJob.status === 'running'" class="loading">
        <span class="spinner"></span>
        <span>{{ t('sbomUpdater.processing') }}</span>
        <span v-if="activeJob.progress_total > 0" class="progress-text">
          ({{ activeJob.progress_current }} / {{ activeJob.progress_total }})
        </span>
        <button class="btn-cancel" @click="handleCancel" :disabled="cancelling">
          {{ t('common.cancel') }}
        </button>
      </div>

      <!-- completed -->
      <div v-if="activeJob.status === 'completed' && activeJob.summary" class="results">
        <!-- summary cards + results table + download button (same as current UI) -->
        <!-- But download button calls downloadJobResultUrl(activeJobId) -->
      </div>

      <!-- failed -->
      <div v-if="activeJob.status === 'failed'" class="error-msg">
        {{ activeJob.error_message || t('sbomUpdater.failed') }}
      </div>

      <!-- cancelled -->
      <div v-if="activeJob.status === 'cancelled'" class="info-msg">
        {{ t('sbomUpdater.cancelled') }}
      </div>

      <!-- Delete button for terminal statuses -->
      <div v-if="isTerminal(activeJob.status)" class="toolbar">
        <button class="btn-delete-job" @click="handleDelete" :disabled="deleting">
          {{ t('common.delete') }}
        </button>
      </div>
    </div>
  </div>
</template>
```

- [ ] **Step 2: Rewrite the script section**

```ts
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import FileUploadZone from '../components/FileUploadZone.vue'
import RecentJobs from '../components/RecentJobs.vue'
import { getIgnorePatterns, saveIgnorePatterns } from '../api/sbom'
import { createSbomEnrichJob, getJob, cancelJob, deleteJob, listJobs, downloadJobResultUrl } from '../api/jobs'
import { ApiError } from '../api/client'
import { useSettingsStore } from '../stores/useSettingsStore'
import { safeUrl } from '../composables/useDownload'
import type { IgnorePatternItem, JobRecord, JobStatus } from '../types/api'

const { t } = useI18n()

const selectedFile = ref<File | null>(null)
const removeUnresolved = ref(false)
const submitting = ref(false)
const error = ref<string | null>(null)
const cancelling = ref(false)
const deleting = ref(false)

const patternRows = ref<IgnorePatternItem[]>([])
const savingPatterns = ref(false)
const patternsSaved = ref(false)

const jobs = ref<JobRecord[]>([])
const activeJobId = ref<string | null>(null)
const activeJob = computed(() => jobs.value.find(j => j.job_id === activeJobId.value) || null)

let pollTimer: ReturnType<typeof setInterval> | null = null
let saveTimer: ReturnType<typeof setTimeout> | null = null

function isTerminal(status: JobStatus): boolean {
  return status === 'completed' || status === 'failed' || status === 'cancelled'
}

function onFileSelected(file: File) {
  selectedFile.value = file
  error.value = null
}

async function handleProcess() {
  if (!selectedFile.value) return
  error.value = null
  submitting.value = true
  try {
    const res = await createSbomEnrichJob(
      selectedFile.value,
      removeUnresolved.value,
      collectPatterns(),
    )
    // Add job to list and select it
    activeJobId.value = res.job_id
    // Reload full job list
    await loadJobs()
    startPolling(res.job_id)
  } catch (e: unknown) {
    if (e instanceof ApiError) {
      error.value = t('errors.' + e.error, e.data)
    } else if (e instanceof Error) {
      error.value = t('errors.network_error')
    } else {
      error.value = t('errors.unexpected_error')
    }
  } finally {
    submitting.value = false
  }
}

function startPolling(jobId: string) {
  stopPolling()
  pollTimer = setInterval(async () => {
    try {
      const record = await getJob(jobId)
      const idx = jobs.value.findIndex(j => j.job_id === jobId)
      if (idx >= 0) {
        jobs.value[idx] = record
      }
      if (isTerminal(record.status)) {
        stopPolling()
      }
    } catch {
      stopPolling()
    }
  }, 2000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

async function selectJob(jobId: string) {
  activeJobId.value = jobId
  stopPolling()
  const record = jobs.value.find(j => j.job_id === jobId)
  if (record && !isTerminal(record.status)) {
    startPolling(jobId)
  }
}

async function handleCancel() {
  if (!activeJobId.value) return
  cancelling.value = true
  try {
    await cancelJob(activeJobId.value)
    await loadJobs()
  } catch {
    // ignore
  } finally {
    cancelling.value = false
  }
}

async function handleDelete() {
  if (!activeJobId.value) return
  deleting.value = true
  try {
    await deleteJob(activeJobId.value)
    jobs.value = jobs.value.filter(j => j.job_id !== activeJobId.value)
    activeJobId.value = jobs.value.length > 0 ? jobs.value[0].job_id : null
  } catch {
    // ignore
  } finally {
    deleting.value = false
  }
}

async function loadJobs() {
  try {
    const data = await listJobs(20, 0)
    jobs.value = data.jobs
  } catch {
    // ignore
  }
}

function downloadResultUrl(): string {
  return activeJobId.value ? downloadJobResultUrl(activeJobId.value) : '#'
}

function downloadResult() {
  if (!activeJobId.value) return
  window.open(downloadJobResultUrl(activeJobId.value), '_blank')
}

// Ignore patterns methods unchanged...

onMounted(async () => {
  try {
    const data = await getIgnorePatterns()
    patternRows.value = data.patterns.length > 0 ? data.patterns : [{ field: '', pattern: '' }]
  } catch {
    patternRows.value = [{ field: '', pattern: '' }]
  }
  await loadJobs()
})

onUnmounted(() => {
  stopPolling()
  if (saveTimer) clearTimeout(saveTimer)
})
```

- [ ] **Step 3: Add the results display for completed jobs**

The completed job display reuses the existing summary-grid + results table + download button pattern, but reads from `activeJob.summary` and `activeJob.results` instead of `result`. The download button uses the server endpoint URL rather than generating a blob.

Summary grid template (reuse existing summary-item blocks):
```html
<div v-if="activeJob.status === 'completed' && activeJob.summary" class="results">
  <div class="summary-grid">
    <div class="summary-item">
      <div class="summary-value">{{ activeJob.summary.total_purls }}</div>
      <div class="summary-label">{{ t('sbomUpdater.total') }}</div>
    </div>
    <!-- ... other summary items ... -->
  </div>

  <div class="table-wrapper">
    <table>
      <thead>
        <tr>
          <th>{{ t('sbomUpdater.purl') }}</th>
          <th>{{ t('sbomUpdater.status') }}</th>
          <th>{{ t('sbomUpdater.repoUrl') }}</th>
          <th>{{ t('sbomUpdater.foundBy') }}</th>
          <th>{{ t('sbomUpdater.resolver') }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(item, i) in activeJob.results" :key="i">
          <!-- ... same as current ... -->
        </tr>
      </tbody>
    </table>
  </div>

  <div class="toolbar">
    <a :href="downloadResultUrl()" class="btn-primary" download>
      {{ t('sbomUpdater.downloadEnriched') }}
    </a>
  </div>
</div>
```

- [ ] **Step 4: Rewrite tests**

Update `frontend/src/views/SbomUpdater.test.ts` to:
- Mock `api/jobs.ts` module instead of `resolveSbom` from `api/sbom.ts`
- Test job creation flow
- Test polling behavior
- Test cancel/delete
- Test job selection from history
- Test completed job display with summary + results
- Test error display

Remove tests for `AbortController` (no longer relevant).

- [ ] **Step 5: Add i18n keys**

In `en.json`:
```json
"sbomUpdater": {
  // existing keys kept, add:
  "cancelled": "Job was cancelled",
  "failed": "Job failed",
  "queued": "Waiting to start..."
}
```

In `ru.json`:
```json
"sbomUpdater": {
  // existing keys kept, add:
  "cancelled": "Задача отменена",
  "failed": "Ошибка выполнения",
  "queued": "Ожидание запуска..."
}
```

- [ ] **Step 6: Run frontend tests**

Run: `npm run test -- --run` in `frontend/`
Expected: all tests PASS

- [ ] **Step 7: Commit**

```bash
git add frontend/src/views/SbomUpdater.vue frontend/src/views/SbomUpdater.test.ts frontend/src/i18n/locales/en.json frontend/src/i18n/locales/ru.json
git commit -m "feat: rework SbomUpdater for job-based async enrichment"
```

---

### Task 9: Backend tests — integration and edge cases

**Files:**
- Create/Modify: `tests/test_sbom_integration.py` (finalize remaining test adjustments)
- Modify: `tests/conftest.py` if needed

- [ ] **Step 1: Ensure all pipeline-level tests still pass**

The pipeline tests (`TestValidateExistingRefs`) use `SbomEnrichmentPipeline` directly and should be untouched. Verify they still pass.

- [ ] **Step 2: Add integration test for full job flow (optional)**

Consider adding a higher-level integration test that mocks `JobRepository` and tests the full flow: create job → queue → worker processes → completed → download result. This can be done as a single async test with mocked resolver.

- [ ] **Step 3: Run full test suite**

Run: `pytest tests/ -v`
Expected: all PASS

- [ ] **Step 4: Commit if any changes were made**

---

### Spec Coverage Check

| Spec requirement | Task(s) |
|---|---|
| `jobs` table with `queued → running → completed/failed/cancelled` states | Task 1 (DDL) + Task 2 (JobManager state transitions) |
| File storage on disk (`data/jobs/{job_id}/`) | Task 2 (`_process_job` writes to disk) |
| API: `POST /api/v1/jobs/sbom-enrich` → 202 | Task 4 |
| API: `GET /api/v1/jobs/{id}` with status/progress/summary/results | Task 4 |
| API: `GET /api/v1/jobs/{id}/result` → file download | Task 4 |
| API: `POST /api/v1/jobs/{id}/cancel` | Task 4 |
| API: `DELETE /api/v1/jobs/{id}` | Task 4 |
| API: `GET /api/v1/jobs` → list recent | Task 4 |
| Removal of old `POST /api/v1/resolve/sbom` | Task 5 |
| Sequential worker (single coroutine) | Task 2 (`_run_worker` loop) |
| Cancel vs Delete distinction | Task 2 (`cancel_job` sets flag, `delete_job` removes completely) |
| Recovery: stuck `running` → `failed` on startup | Task 2 (`start()` calls `get_stuck_running`) |
| Recovery: requeue `queued` on startup | Task 2 (`start()` calls `get_queued` + `put`) |
| TTL cleanup periodic task | Task 2 (`_run_cleanup` every 60s) |
| `job_ttl_hours` setting in Settings UI | Task 3 |
| Frontend: RecentJobs panel | Task 7 |
| Frontend: job details (spinner/summary/table/cancel/delete) | Task 8 |
| Frontend: polling every 2s | Task 8 (`startPolling` setInterval) |
| Remove AbortController from frontend | Task 8 (no longer imported) |
| Cancel = no partial result saved | Task 2 (`_process_job` checks flag early, returns without saving) |
