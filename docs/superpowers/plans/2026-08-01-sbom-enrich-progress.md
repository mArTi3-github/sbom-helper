# SBOM Enrichment Progress UI — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make SBOM enrichment jobs report live progress (PURL counter + phase) and render it as a progress bar in the job details panel.

**Architecture:** The `jobs` table already has `progress_current` / `progress_total` columns and the API already returns them, but nothing writes them. A nullable `progress_phase` TEXT column is added. The pipeline (`SbomEnrichmentPipeline.process`) gains an optional `ProgressReporter` protocol; `PurlResolutionService.resolve_batch` gains an optional per-PURL `on_progress` callback. `JobManager` wires a throttled reporter that writes progress into the DB (2s throttle, in sync with the existing 2s frontend polling). The frontend replaces the bare "(X / Y)" text with a progress bar plus phase label and percentage.

**Tech Stack:** Python 3.11 / FastAPI / asyncpg (backend), Vue 3 / vue-i18n / Vitest / TypeScript (frontend).

## Global Constraints

- Backend tests run with the project venv: `source .venv/bin/activate` first (all pytest commands below assume it).
- Ruff is the linter: `ruff check src tests` — line length 100, selects `E, F, I, W`.
- pytest `asyncio_mode = "auto"`; existing async tests still use explicit `@pytest.mark.asyncio` — keep that style.
- Frontend tests: `cd frontend && npm test` (vitest). Type check / build: `cd frontend && npm run build` (vue-tsc).
- Frontend i18n: keys go to BOTH `frontend/src/i18n/locales/en.json` and `ru.json`. Plain JSON — no comments.
- No new dependencies.
- Design doc (authoritative): `docs/superpowers/specs/2026-08-01-sbom-enrich-progress-design.md`.
- Phase string values are fixed: `parsing`, `validating_refs`, `resolving`, `enriching`.

---

### Task 1: Schema — add `progress_phase` column + idempotent migration

**Files:**
- Modify: `src/purl_resolver/storage/schema.sql`
- Test: `tests/test_storage.py` (append `TestSchema` class at the end of the file)

**Interfaces:**
- Consumes: nothing.
- Produces: `jobs.progress_phase TEXT` column (nullable), present both in the `CREATE TABLE IF NOT EXISTS` DDL and via `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` for existing databases. `postgres._load_schema()` (existing function in `src/purl_resolver/storage/postgres.py`) loads this file at startup.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_storage.py`:

```python
class TestSchema:

    def test_schema_has_progress_phase_column(self) -> None:
        from purl_resolver.storage import postgres
        postgres.CREATE_TABLE_SQL = None
        schema = postgres._load_schema()
        assert "progress_phase" in schema
        assert "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS progress_phase TEXT" in schema
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_storage.py::TestSchema -v`
Expected: FAIL (assertion error — `progress_phase` not in schema yet)

- [ ] **Step 3: Implement**

In `src/purl_resolver/storage/schema.sql`, add the column to the `jobs` DDL (after `progress_total`):

```sql
    progress_phase   TEXT,
```

And immediately after the `CREATE TABLE IF NOT EXISTS jobs (...)` statement (before the `resolved_purls` comment), add the idempotent migration:

```sql
-- Idempotent migration for existing databases: CREATE TABLE IF NOT EXISTS
-- does not alter tables, so new columns are added explicitly.
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS progress_phase TEXT;
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_storage.py::TestSchema -v`
Expected: PASS

- [ ] **Step 5: Lint and commit**

```bash
ruff check src tests
git add src/purl_resolver/storage/schema.sql tests/test_storage.py
git commit -m "feat: add progress_phase column to jobs schema"
```

---

### Task 2: `JobRecord` and repository — carry `progress_phase`

**Files:**
- Modify: `src/purl_resolver/job_repository.py:13-64`
- Test: `tests/test_job_repository.py`

**Interfaces:**
- Consumes: `jobs.progress_phase` column from Task 1.
- Produces: `JobRecord.progress_phase: str | None` (dataclass field, default `None`), included in `_COLUMNS` so `create`/`get`/`list`/`_row_to_record` handle it. `_row_to_record` indexes every `_COLUMNS` key into the DB row — a missing key raises `KeyError`, so all `MockRecord` fixtures in tests must include it.

- [ ] **Step 1: Write the failing test**

In `tests/test_job_repository.py`:

1. Update the existing `MockRecord(...)` in `test_create_and_get` — add `progress_phase=None` to its kwargs (otherwise `_row_to_record` raises `KeyError` once `_COLUMNS` includes the new key).
2. Add a new test after `test_create_and_get`:

```python
    @pytest.mark.asyncio
    async def test_create_and_get_with_progress_phase(self, repo):
        job_id = _new_id()
        record = JobRecord(
            id=job_id, type="sbom_enrich", status="running",
            progress_current=3, progress_total=10, progress_phase="resolving",
        )
        repo._pool.acquire.return_value.__aenter__.return_value.fetchrow.return_value = MockRecord(
            id=job_id, type="sbom_enrich", status="running",
            progress_current=3, progress_total=10, progress_phase="resolving",
            params_json=None, input_filename=None,
            result_path=None, summary_json=None, results_json=None,
            error_message=None, cancel_requested=0,
            created_at="2026-07-10T12:00:00", started_at=None, finished_at=None,
        )

        await repo.create(record)
        fetched = await repo.get(job_id)

        assert fetched is not None
        assert fetched.progress_phase == "resolving"
        assert fetched.progress_current == 3
        assert fetched.progress_total == 10
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_job_repository.py -v`
Expected: FAIL — `progress_phase` is not a `JobRecord` field yet (and `_row_to_record` fails on the updated existing test)

- [ ] **Step 3: Implement**

In `src/purl_resolver/job_repository.py`:

1. Add the field to `JobRecord` (after `progress_total`):

```python
    progress_phase: str | None = None
```

2. Add the key to `_COLUMNS` (after `"progress_total"`):

```python
    "progress_phase",
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_job_repository.py -v`
Expected: PASS (all tests in file)

- [ ] **Step 5: Lint and commit**

```bash
ruff check src tests
git add src/purl_resolver/job_repository.py tests/test_job_repository.py
git commit -m "feat: carry progress_phase in JobRecord"
```

---

### Task 3: `resolve_batch` — per-PURL `on_progress` callback

**Files:**
- Modify: `src/purl_resolver/service.py:162-180`
- Test: `tests/test_resolve_batch.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `PurlResolutionService.resolve_batch(purls: list[str], resolver: str = "", on_progress: Callable[[int, int], Awaitable[None]] | None = None) -> dict[str, ResolveResponse]`. When provided, `on_progress(current, total)` is awaited after EACH PURL finishes (including cache hits and PURLs without a result), with `current` counting completed PURLs (1-based) and `total = len(purls)`. Default `None` — behavior unchanged for all existing callers.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_resolve_batch.py` (inside `TestResolveBatch`):

```python
    @pytest.mark.asyncio
    async def test_on_progress_called_after_each_purl(self, storage: InMemoryCache) -> None:
        resolver = FakeResolver(
            resolution=Resolution(
                purl="pkg:pypi/requests@2.31.0",
                repository_url="https://github.com/psf/requests",
            )
        )
        purls = [
            "pkg:pypi/requests@2.31.0",
            "pkg:npm/express@4.17.1",
            "pkg:pypi/flask@3.0.0",
        ]
        calls: list[tuple[int, int]] = []

        async def on_progress(current: int, total: int) -> None:
            calls.append((current, total))

        await PurlResolutionService(storage, [resolver]).resolve_batch(
            purls, on_progress=on_progress
        )

        assert calls == [(1, 3), (2, 3), (3, 3)]

    @pytest.mark.asyncio
    async def test_on_progress_counts_unresolved_purls(self, storage: InMemoryCache) -> None:
        resolver = FakeResolver(
            resolution=Resolution(purl="pkg:pypi/requests@2.31.0", repository_url=None)
        )
        calls: list[tuple[int, int]] = []

        async def on_progress(current: int, total: int) -> None:
            calls.append((current, total))

        await PurlResolutionService(storage, [resolver]).resolve_batch(
            ["pkg:pypi/requests@2.31.0"], on_progress=on_progress
        )

        assert calls == [(1, 1)]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_resolve_batch.py -v`
Expected: FAIL — `TypeError: resolve_batch() got an unexpected keyword argument 'on_progress'`

- [ ] **Step 3: Implement**

In `src/purl_resolver/service.py`:

1. Add imports at the top (after the existing `import logging` block):

```python
import itertools
from collections.abc import Awaitable, Callable
```

2. Replace the body of `resolve_batch`:

```python
    async def resolve_batch(
        self,
        purls: list[str],
        resolver: str = "",
        on_progress: Callable[[int, int], Awaitable[None]] | None = None,
    ) -> dict[str, ResolveResponse]:
        batch_limit = self._settings_store.load().batch_semaphore_limit if self._settings_store else _BATCH_SEMAPHORE_LIMIT
        semaphore = asyncio.Semaphore(batch_limit)
        total = len(purls)
        counter = itertools.count(1)

        async def _resolve_one(original: str) -> tuple[str, ResolveResponse | None]:
            async with semaphore:
                result = await self.resolve_purl(original, resolver=resolver)
                key = safe_normalize(original)
                if on_progress is not None:
                    await on_progress(next(counter), total)
                if result.response and result.response.repository_url:
                    return (key, result.response)
                return (key, None)

        tasks = [_resolve_one(p) for p in purls]
        results = await asyncio.gather(*tasks)
        return {k: v for k, v in results if v is not None}
```

The counter is assigned in actual completion order, so the callback sequence is always `(1, N), (2, N), ..., (N, N)` regardless of task interleaving.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_resolve_batch.py -v`
Expected: PASS (all tests in file — existing ones prove backward compatibility)

- [ ] **Step 5: Lint and commit**

```bash
ruff check src tests
git add src/purl_resolver/service.py tests/test_resolve_batch.py
git commit -m "feat: add per-PURL on_progress callback to resolve_batch"
```

---

### Task 4: Pipeline — `progress_reporter` with phases

**Files:**
- Modify: `src/purl_resolver/sbom_enrichment.py:1-175`
- Create: `tests/test_sbom_enrichment.py`

**Interfaces:**
- Consumes: `resolve_batch(..., on_progress=...)` from Task 3.
- Produces: `SbomEnrichmentPipeline.process(sbom_data, remove_unresolved_no_subcomponents=False, ignore_patterns=None, progress_reporter: ProgressReporter | None = None) -> SbomEnrichmentResult`. `ProgressReporter` is a `Protocol` with `async on_phase(phase: str) -> None` and `async on_resolved(current: int, total: int) -> None`. Phase sequence: `parsing` → (`validating_refs` only when `validate_sbom_refs` enabled) → `resolving` → `enriching`. `on_resolved(0, total)` is emitted once right before `resolve_batch`, then `(k, total)` per PURL via the Task 3 callback. Default `None` — behavior unchanged.

- [ ] **Step 1: Write the failing test**

Create `tests/test_sbom_enrichment.py`:

```python
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from purl_resolver.resolver.interface import Resolution
from purl_resolver.sbom_enrichment import SbomEnrichmentPipeline
from purl_resolver.service import PurlResolutionService
from purl_resolver.settings_store import AppSettings
from purl_resolver.storage.inmemory import InMemoryCache
from tests.helpers import FakeResolver


class RecordingReporter:
    def __init__(self) -> None:
        self.phases: list[str] = []
        self.progress: list[tuple[int, int]] = []

    async def on_phase(self, phase: str) -> None:
        self.phases.append(phase)

    async def on_resolved(self, current: int, total: int) -> None:
        self.progress.append((current, total))


def _sbom_with_purls(purls: list[str]) -> dict:
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "components": [
            {"type": "library", "name": f"comp{i}", "version": "1.0.0", "purl": p}
            for i, p in enumerate(purls)
        ],
    }


@pytest.fixture
def resolution_service() -> PurlResolutionService:
    resolver = FakeResolver(
        resolution=Resolution(
            purl="pkg:pypi/requests@2.31.0",
            repository_url="https://github.com/psf/requests",
        ),
    )
    return PurlResolutionService(InMemoryCache(), [resolver])


class TestProgressReporter:

    @pytest.mark.asyncio
    async def test_reports_phases_and_progress(self, resolution_service) -> None:
        reporter = RecordingReporter()
        pipeline = SbomEnrichmentPipeline(resolution_service)
        await pipeline.process(
            _sbom_with_purls(["pkg:pypi/requests@2.31.0", "pkg:npm/express@4.17.1"]),
            progress_reporter=reporter,
        )
        assert reporter.phases == ["parsing", "resolving", "enriching"]
        assert reporter.progress[0] == (0, 2)
        assert reporter.progress[-1] == (2, 2)
        assert len(reporter.progress) == 3

    @pytest.mark.asyncio
    async def test_zero_total_still_reports_initial_call(self, resolution_service) -> None:
        reporter = RecordingReporter()
        pipeline = SbomEnrichmentPipeline(resolution_service)
        await pipeline.process(
            _sbom_with_purls(["not-a-purl"]),
            progress_reporter=reporter,
        )
        assert reporter.phases == ["parsing", "resolving", "enriching"]
        assert reporter.progress == [(0, 0)]

    @pytest.mark.asyncio
    async def test_validating_refs_phase_when_enabled(self) -> None:
        settings_store = MagicMock()
        settings_store.load.return_value = AppSettings(validate_sbom_refs=True)
        service = PurlResolutionService(
            InMemoryCache(), [FakeResolver()], settings_store=settings_store,
        )
        pipeline = SbomEnrichmentPipeline(service)
        pipeline._validate_external_references = AsyncMock()
        reporter = RecordingReporter()
        await pipeline.process(
            _sbom_with_purls(["pkg:pypi/requests@2.31.0"]),
            progress_reporter=reporter,
        )
        assert reporter.phases == ["parsing", "validating_refs", "resolving", "enriching"]

    @pytest.mark.asyncio
    async def test_without_reporter_unchanged(self, resolution_service) -> None:
        pipeline = SbomEnrichmentPipeline(resolution_service)
        result = await pipeline.process(_sbom_with_purls(["pkg:pypi/requests@2.31.0"]))
        assert result.enriched_sbom["components"][0]["externalReferences"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_sbom_enrichment.py -v`
Expected: FAIL — `TypeError: process() got an unexpected keyword argument 'progress_reporter'`

- [ ] **Step 3: Implement**

In `src/purl_resolver/sbom_enrichment.py`:

1. Add to the imports (after `from dataclasses import dataclass`):

```python
from typing import Protocol
```

2. Add the protocol after the imports block (before `logger`):

```python
class ProgressReporter(Protocol):
    async def on_phase(self, phase: str) -> None: ...

    async def on_resolved(self, current: int, total: int) -> None: ...
```

3. Change the `process` signature:

```python
    async def process(
        self,
        sbom_data: dict,
        remove_unresolved_no_subcomponents: bool = False,
        ignore_patterns: list[dict[str, str]] | None = None,
        progress_reporter: ProgressReporter | None = None,
    ) -> SbomEnrichmentResult:
        """Parse, collect, deduplicate, resolve, enrich, and report."""
        if progress_reporter is not None:
            await progress_reporter.on_phase("parsing")
        CycloneDXParser.parse(sbom_data)
```

4. Inside the validation block, report the phase before validating (replace `await self._validate_external_references(components, app_settings)` with):

```python
            if app_settings.validate_sbom_refs:
                if progress_reporter is not None:
                    await progress_reporter.on_phase("validating_refs")
                await self._validate_external_references(components, app_settings)
```

5. Replace the resolution block:

```python
        if progress_reporter is not None:
            await progress_reporter.on_phase("resolving")
            await progress_reporter.on_resolved(0, len(unique_purls))

        async def _report_resolved(current: int, total: int) -> None:
            if progress_reporter is not None:
                await progress_reporter.on_resolved(current, total)

        resolved = await self._resolution_service.resolve_batch(
            unique_purls,
            resolver="import-sbom",
            on_progress=_report_resolved,
        )
        await self._resolution_service.store_preexisting_references(
            components, resolver="import-sbom"
        )

        removed: list[dict] = []
        if progress_reporter is not None:
            await progress_reporter.on_phase("enriching")
        enrich_sbom(sbom_data, components, resolved)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_sbom_enrichment.py -v`
Expected: PASS (all 4 tests)

- [ ] **Step 5: Regression check, lint and commit**

```bash
pytest tests/test_sbom_integration.py tests/test_resolve_batch.py -q
ruff check src tests
git add src/purl_resolver/sbom_enrichment.py tests/test_sbom_enrichment.py
git commit -m "feat: report phases and PURL progress from enrichment pipeline"
```

---

### Task 5: `JobManager` — throttled progress reporter wiring

**Files:**
- Modify: `src/purl_resolver/job_manager.py:1-237`
- Test: `tests/test_job_manager.py`

**Interfaces:**
- Consumes: `pipeline.process(..., progress_reporter=...)` from Task 4; `JobRepository.update_status(job_id, status, **fields)` (existing).
- Produces: module-level `_JobProgressReporter` class with `__init__(self, repo: JobRepository, job_id: str, throttle_seconds: float = _PROGRESS_THROTTLE_SECONDS, monotonic: Callable[[], float] = time.monotonic)` and methods `async on_phase(phase: str) -> None`, `async on_resolved(current: int, total: int) -> None`. DB writes never raise (errors are logged). `_process_job` passes a reporter into the pipeline. The injectable `monotonic` clock is what makes the throttle testable.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_job_manager.py`:

1. Extend the imports at the top:

```python
from purl_resolver.job_manager import JobManager, JOBS_DIR, _JobProgressReporter
from purl_resolver.resolver.interface import Resolution
from purl_resolver.service import PurlResolutionService
from purl_resolver.storage.inmemory import InMemoryCache
from tests.helpers import FakeResolver
```

2. Append the reporter unit tests and the integration test (after the existing `TestJobManager` class):

```python
class FakeClock:
    def __init__(self, values: list[float]) -> None:
        self._values = list(values)

    def __call__(self) -> float:
        return self._values.pop(0)


class TestJobProgressReporter:

    @pytest.mark.asyncio
    async def test_throttles_intermediate_writes(self, mock_repo) -> None:
        # Clock values consumed in this order:
        #   initial write, 2 skipped checks, throttle-expired write, final write
        clock = FakeClock([0.0, 0.0, 0.1, 3.0, 9.0, 9.0])
        reporter = _JobProgressReporter(mock_repo, "j1", monotonic=clock)

        await reporter.on_resolved(0, 10)    # initial -> write (0, 10)
        await reporter.on_resolved(1, 10)    # 0.0 - 0.0 < 2 -> skip
        await reporter.on_resolved(2, 10)    # 0.1 - 0.0 < 2 -> skip
        await reporter.on_resolved(5, 10)    # 3.0 - 0.1 >= 2 -> write (5, 10)
        await reporter.on_resolved(10, 10)   # current == total -> forced write

        writes = [
            c.kwargs for c in mock_repo.update_status.call_args_list
            if "progress_current" in c.kwargs
        ]
        assert writes == [
            {"progress_current": 0, "progress_total": 10},
            {"progress_current": 5, "progress_total": 10},
            {"progress_current": 10, "progress_total": 10},
        ]

    @pytest.mark.asyncio
    async def test_phase_writes_unconditionally(self, mock_repo) -> None:
        reporter = _JobProgressReporter(mock_repo, "j1", monotonic=lambda: 1.0)

        await reporter.on_phase("parsing")
        await reporter.on_phase("resolving")

        assert mock_repo.update_status.call_count == 2
        mock_repo.update_status.assert_any_call("j1", "running", progress_phase="parsing")
        mock_repo.update_status.assert_any_call("j1", "running", progress_phase="resolving")

    @pytest.mark.asyncio
    async def test_db_error_is_swallowed(self, mock_repo) -> None:
        mock_repo.update_status.side_effect = RuntimeError("db down")
        reporter = _JobProgressReporter(mock_repo, "j1")

        await reporter.on_phase("resolving")
        await reporter.on_resolved(0, 10)


class TestProcessJobProgress:

    @pytest.mark.asyncio
    async def test_process_job_reports_progress(self, manager, mock_repo, tmp_path) -> None:
        record = JobRecord(
            id="j1", type="sbom_enrich", status="queued",
            params_json=json.dumps({"remove_unresolved_no_subcomponents": False}),
        )
        mock_repo.get.return_value = record
        resolver = FakeResolver(
            resolution=Resolution(
                purl="pkg:pypi/requests@2.31.0",
                repository_url="https://github.com/psf/requests",
            ),
        )
        manager._resolution_service = PurlResolutionService(InMemoryCache(), [resolver])

        sbom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "components": [
                {"type": "library", "name": "requests", "version": "2.31.0", "purl": "pkg:pypi/requests@2.31.0"},
                {"type": "library", "name": "flask", "version": "3.0.0", "purl": "pkg:pypi/flask@3.0.0"},
            ],
        }
        with patch("purl_resolver.job_manager.JOBS_DIR", tmp_path):
            (tmp_path / "j1").mkdir(parents=True)
            (tmp_path / "j1" / "input.json").write_text(json.dumps(sbom))
            await manager._process_job("j1")

        progress_calls = [
            c.kwargs for c in mock_repo.update_status.call_args_list
            if "progress_" in " | ".join(c.kwargs)
        ]
        phases = [k["progress_phase"] for k in progress_calls if "progress_phase" in k]
        totals = [k["progress_total"] for k in progress_calls if "progress_total" in k]
        last_progress = [k for k in progress_calls if "progress_current" in k][-1]

        assert phases == ["parsing", "resolving", "enriching"]
        assert totals and totals[0] == 2
        assert last_progress["progress_current"] == 2
        assert last_progress["progress_total"] == 2

        statuses = [c.args[1] for c in mock_repo.update_status.call_args_list]
        assert statuses[-1] == "completed"
```

Note: the integration test relies on the fast in-memory pipeline: intermediate writes get throttled by the real `time.monotonic`, while the forced writes `(0, total)` and `(total, total)` always land — so no time mocking is needed here.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_job_manager.py -v`
Expected: FAIL — `ImportError: cannot import name '_JobProgressReporter'`

- [ ] **Step 3: Implement**

In `src/purl_resolver/job_manager.py`:

1. Add imports (extend the existing `import os` / `from pathlib import Path` block):

```python
import time
from collections.abc import Callable
from typing import Any
```

2. After `JOBS_DIR = ...` (module level):

```python
_PROGRESS_THROTTLE_SECONDS = 2.0


class _JobProgressReporter:
    """Writes pipeline progress into the jobs table, throttling DB writes.

    Forced writes happen on phase changes and on the initial (0, total) and
    final (total, total) progress events; intermediate writes are throttled
    to ``throttle_seconds`` (default 2.0, matching the frontend poll interval).
    DB errors are logged and swallowed — progress reporting never fails a job.
    """

    def __init__(
        self,
        repo: JobRepository,
        job_id: str,
        throttle_seconds: float = _PROGRESS_THROTTLE_SECONDS,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._repo = repo
        self._job_id = job_id
        self._throttle_seconds = throttle_seconds
        self._monotonic = monotonic
        self._last_write = 0.0

    async def on_phase(self, phase: str) -> None:
        await self._write(progress_phase=phase)

    async def on_resolved(self, current: int, total: int) -> None:
        if current == 0 or current == total:
            await self._write(progress_current=current, progress_total=total)
            return
        if self._monotonic() - self._last_write >= self._throttle_seconds:
            await self._write(progress_current=current, progress_total=total)

    async def _write(self, **fields: Any) -> None:
        try:
            await self._repo.update_status(self._job_id, "running", **fields)
            self._last_write = self._monotonic()
        except Exception:
            logger.warning("Failed to update progress for job %s", self._job_id, exc_info=True)
```

3. In `_process_job`, replace the pipeline construction and call:

```python
            pipeline = SbomEnrichmentPipeline(self._resolution_service)
            reporter = _JobProgressReporter(self._repo, job_id)

            result = await pipeline.process(
                sbom_data,
                remove_unresolved_no_subcomponents=remove_unresolved,
                ignore_patterns=ignore_patterns,
                progress_reporter=reporter,
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_job_manager.py -v`
Expected: PASS (all tests in file, including the pre-existing ones)

- [ ] **Step 5: Lint and commit**

```bash
ruff check src tests
git add src/purl_resolver/job_manager.py tests/test_job_manager.py
git commit -m "feat: report job progress with 2s throttled DB writes"
```

---

### Task 6: API routes — expose `progress_phase`

**Files:**
- Modify: `src/purl_resolver/routes/jobs.py:87-100` (get_job response) and `src/purl_resolver/routes/jobs.py:168-184` (list response)
- Test: `tests/test_routes_jobs.py`

**Interfaces:**
- Consumes: `JobRecord.progress_phase` from Task 2.
- Produces: `"progress_phase": str | None` in both `GET /api/v1/jobs/{job_id}` and `GET /api/v1/jobs` response objects.

- [ ] **Step 1: Write the failing test**

In `tests/test_routes_jobs.py`:

1. In `TestGetJob.test_existing`, add `progress_phase="resolving"` to the `JobRecord(...)` and assert the response field:

```python
        assert data["progress_phase"] == "resolving"
```

2. Add a new test in `TestGetJob`:

```python
    def test_queued_has_null_progress_phase(self, client, mock_manager):
        record = JobRecord(
            id="job-1", type="sbom_enrich", status="queued",
            params_json='{"remove_unresolved_no_subcomponents": false}',
            input_filename="test.json",
        )
        mock_manager.get_job.return_value = record
        response = client.get("/api/v1/jobs/job-1")
        assert response.status_code == 200
        data = response.json()
        assert data["progress_phase"] is None
```

3. In `TestListJobs.test_with_records`, add `progress_phase="resolving"` to the `JobRecord(...)` and assert:

```python
        assert data["jobs"][0]["progress_phase"] == "resolving"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_routes_jobs.py -v`
Expected: FAIL — `KeyError: 'progress_phase'` in the two response-parsing assertions

- [ ] **Step 3: Implement**

In `src/purl_resolver/routes/jobs.py`:

1. In `get_job` response dict, add after `"progress_total"`:

```python
        "progress_phase": record.progress_phase,
```

2. In `list_jobs` response dict, add after `"progress_total"`:

```python
                "progress_phase": r.progress_phase,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_routes_jobs.py -v`
Expected: PASS (all tests in file)

- [ ] **Step 5: Lint and commit**

```bash
ruff check src tests
git add src/purl_resolver/routes/jobs.py tests/test_routes_jobs.py
git commit -m "feat: expose progress_phase in job API responses"
```

---

### Task 7: Frontend types, i18n keys, test fixtures

**Files:**
- Modify: `frontend/src/types/api.ts:85-98`
- Modify: `frontend/src/i18n/locales/en.json` (`sbomUpdater` block)
- Modify: `frontend/src/i18n/locales/ru.json` (`sbomUpdater` block)
- Modify: `frontend/src/views/SbomUpdater.test.ts` (the three JobRecord fixtures `runningJob`, `completedJob`, `failedJob`)

**Interfaces:**
- Consumes: API response field from Task 6.
- Produces: `JobRecord.progress_phase: string | null` (required type member), i18n keys `sbomUpdater.phase.{parsing,validating_refs,resolving,enriching}` and `sbomUpdater.progressCounter` (named params `current`, `total`, `percent`) in both locales. `progressCounter` uses named interpolation — vue-i18n renders `{current}` placeholders.

- [ ] **Step 1: Write the failing test**

Update the three JobRecord fixtures in `frontend/src/views/SbomUpdater.test.ts` — add `progress_phase: null` after the `progress_total` line in each of `runningJob`, `completedJob`, `failedJob`. (TypeScript will fail the build/typecheck without it.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm run build`
Expected: FAIL — `Property 'progress_phase' is missing in type ... but required in type 'JobRecord'`

- [ ] **Step 3: Implement**

1. `frontend/src/types/api.ts` — add to `JobRecord` (after `progress_total`):

```ts
  progress_phase: string | null
```

2. `frontend/src/i18n/locales/en.json` — inside the `sbomUpdater` object, after `"queued"`:

```json
    "phase": {
      "parsing": "Parsing SBOM",
      "validating_refs": "Validating references",
      "resolving": "Resolving PURLs",
      "enriching": "Enriching SBOM"
    },
    "progressCounter": "{current} / {total} · {percent}%"
```

3. `frontend/src/i18n/locales/ru.json` — inside the `sbomUpdater` object, after `"queued"`:

```json
    "phase": {
      "parsing": "Разбор SBOM",
      "validating_refs": "Проверка ссылок",
      "resolving": "Резолвинг PURL",
      "enriching": "Обогащение SBOM"
    },
    "progressCounter": "{current} / {total} · {percent}%"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm run build && npm test`
Expected: PASS — build succeeds, all existing frontend tests pass

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/api.ts frontend/src/i18n/locales/en.json frontend/src/i18n/locales/ru.json frontend/src/views/SbomUpdater.test.ts
git commit -m "feat: add progress_phase type and i18n keys for job progress"
```

---

### Task 8: Frontend — progress bar in job details

**Files:**
- Modify: `frontend/src/views/SbomUpdater.vue:53-63` (template), `154-187` (script), `467-479` (styles)
- Test: `frontend/src/views/SbomUpdater.test.ts`

**Interfaces:**
- Consumes: `JobRecord.progress_phase` and i18n keys from Task 7.
- Produces: in the `queued`/`running` details block: `.phase-label`, `.progress-track` / `.progress-fill` (bar only when `progress_total > 0`), `.progress-text` counter. Computed `progressPercent` (0–100, client-side), `phaseLabel`, `progressCounter`.

- [ ] **Step 1: Write the failing test**

Append to `frontend/src/views/SbomUpdater.test.ts` (after the last test in the describe block):

```ts
  it('renders progress bar and phase for a running job', async () => {
    const resolvingJob: JobRecord = { ...runningJob, progress_phase: 'resolving' }
    listJobsMock.mockResolvedValue({ jobs: [resolvingJob] })
    getJobMock.mockResolvedValue(resolvingJob)
    const wrapper = mountUpdater()
    await flushPromises()

    await wrapper.find('.job-row').trigger('click')
    await flushPromises()

    expect(wrapper.find('.progress-track').exists()).toBe(true)
    expect(wrapper.find('.progress-fill').attributes('style')).toContain('width: 50%')
    expect(wrapper.find('.phase-label').text()).toBe('Resolving PURLs')
    expect(wrapper.find('.progress-text').text()).toBe('5 / 10 · 50%')
  })

  it('hides progress bar when total is zero', async () => {
    const zeroJob: JobRecord = {
      ...runningJob,
      progress_current: 0,
      progress_total: 0,
      progress_phase: 'resolving',
    }
    listJobsMock.mockResolvedValue({ jobs: [zeroJob] })
    getJobMock.mockResolvedValue(zeroJob)
    const wrapper = mountUpdater()
    await flushPromises()

    await wrapper.find('.job-row').trigger('click')
    await flushPromises()

    expect(wrapper.find('.progress-track').exists()).toBe(false)
    expect(wrapper.find('.phase-label').text()).toBe('Resolving PURLs')
  })

  it('falls back to processing label when phase is null', async () => {
    const noPhaseJob: JobRecord = { ...runningJob, progress_phase: null }
    listJobsMock.mockResolvedValue({ jobs: [noPhaseJob] })
    getJobMock.mockResolvedValue(noPhaseJob)
    const wrapper = mountUpdater()
    await flushPromises()

    await wrapper.find('.job-row').trigger('click')
    await flushPromises()

    expect(wrapper.find('.phase-label').text()).toBe('Processing SBOM...')
  })
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test`
Expected: FAIL — the three new tests (no `.progress-track` / `.phase-label` elements yet)

- [ ] **Step 3: Implement**

In `frontend/src/views/SbomUpdater.vue`:

1. Replace the `queued / running` block (lines 53–63) with:

```html
      <!-- queued / running -->
      <div v-if="activeJob.status === 'queued' || activeJob.status === 'running'" class="loading">
        <span class="spinner"></span>
        <div class="progress-section">
          <div class="progress-header">
            <span class="phase-label">{{ phaseLabel }}</span>
            <span v-if="activeJob.progress_total > 0" class="progress-text">{{ progressCounter }}</span>
          </div>
          <div v-if="activeJob.progress_total > 0" class="progress-track">
            <div class="progress-fill" :style="{ width: progressPercent + '%' }"></div>
          </div>
        </div>
        <button class="btn-cancel" @click="handleCancel" :disabled="cancelling">
          {{ t('common.cancel') }}
        </button>
      </div>
```

2. In the script section, add computed properties after `activeJob`:

```ts
const progressPercent = computed(() => {
  const total = activeJob.value?.progress_total ?? 0
  const current = activeJob.value?.progress_current ?? 0
  if (total <= 0) return 0
  return Math.min(100, Math.round((current / total) * 100))
})

const phaseLabel = computed(() => {
  const phase = activeJob.value?.progress_phase
  return phase ? t('sbomUpdater.phase.' + phase) : t('sbomUpdater.processing')
})

const progressCounter = computed(() => {
  const job = activeJob.value
  if (!job || job.progress_total <= 0) return ''
  return t('sbomUpdater.progressCounter', {
    current: job.progress_current,
    total: job.progress_total,
    percent: progressPercent.value,
  })
})
```

3. In the styles section, replace `.progress-text` with:

```css
.progress-section {
  flex: 1;
  min-width: 0;
}

.progress-header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.phase-label {
  font-size: 0.9rem;
}

.progress-text {
  font-size: 0.85rem;
  color: var(--color-muted-light);
}

.progress-track {
  margin-top: 0.35rem;
  height: 0.5rem;
  border-radius: var(--border-radius-full);
  background: var(--color-table-header-bg);
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  border-radius: var(--border-radius-full);
  background: var(--color-primary);
  transition: width 0.4s ease;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test && npm run build`
Expected: PASS — all frontend tests (new + existing) and the type check

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/SbomUpdater.vue frontend/src/views/SbomUpdater.test.ts
git commit -m "feat: show enrichment progress bar with phase in job details"
```

---

### Task 9: Full regression + final check

**Files:** none (verification only)

- [ ] **Step 1: Run the full backend test suite**

```bash
source .venv/bin/activate && pytest -q
```
Expected: all tests pass (including e2e, which use testcontainers PostgreSQL — requires Docker).

- [ ] **Step 2: Run the full frontend suite**

```bash
cd frontend && npm test && npm run build
```
Expected: all tests pass, type check clean.

- [ ] **Step 3: Lint**

```bash
ruff check src tests
```
Expected: no findings.

- [ ] **Step 4: Manual smoke test (optional but recommended)**

Start the stack (`docker compose up --build` or `docker-compose up`), open the "Enrich SBOM" page, upload an SBOM with several hundred components, click the job, and confirm: phase label cycles through "Parsing SBOM" → "Resolving PURLs" (with the bar filling) → "Enriching SBOM", and the counter ends at `N / N · 100%` before the results table appears.
