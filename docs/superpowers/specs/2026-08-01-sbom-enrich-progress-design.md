# SBOM Enrichment Progress UI — Design

## Problem

SBOM enrichment is a long-running job. The `jobs` table, the job API, and the frontend already carry `progress_current` / `progress_total` fields (added in the job queue design), and the frontend renders a bare "(current / total)" text when `progress_total > 0`. However, **the backend never writes progress values** — they stay 0/0 for the entire run. Users clicking a running job see only a spinner and cannot tell how much work remains.

Additionally, a part of the pipeline (external-reference validation) runs before PURL resolution and can take a noticeable amount of time on large SBOMs, during which a counter-only progress would look frozen at 0.

## Solution Overview

Populate the existing progress fields end-to-end and add a proper progress UI in the job details panel:

- Backend reports **the current processing phase** (text) and **a PURL counter** (current / total) during resolution.
- A new nullable `progress_phase` column is added to `jobs`; progress updates are throttled to match the frontend poll interval.
- The frontend replaces the bare counter text with a progress bar: phase label, percentage, and counter.

Chosen scope (variant B): counter + text phase label. Numeric per-phase progress (variant C) was rejected as ~2x the work; counter-only (variant A) was rejected because the validation phase would show a frozen empty progress.

## Backend

### Schema (`storage/schema.sql`)

- Add `progress_phase TEXT` (nullable, no default) to the `jobs` DDL.
- `CREATE TABLE IF NOT EXISTS` does not alter existing tables, so an idempotent migration statement is added to the same file:

```sql
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS progress_phase TEXT;
```

This is the first migration in the project; it is harmless and safe to re-run at every startup.

### Pipeline reporting (`sbom_enrichment.py`)

`SbomEnrichmentPipeline.process()` gains an optional `progress_reporter` parameter implementing a small protocol with two async methods:

- `on_phase(phase: str)` — called at 4 points:
  - `parsing` — before parse + collect
  - `validating_refs` — only when `validate_sbom_refs` is enabled
  - `resolving` — before `resolve_batch`, after `unique_purls` is computed
  - `enriching` — after resolution
- `on_resolved(current: int, total: int)` — called once with `(0, total)` immediately before `resolve_batch` (so the reporter learns the denominator even when `total = 0`), then after each PURL completes in the resolution phase.

The reporter parameter is optional; when absent, behavior is unchanged (default `None`).

### Counter semantics

- `total = len(unique_purls)` — the deduplicated, valid PURLs that need enrichment; exactly the list passed to `resolve_batch`.
- `current` increments once per completed PURL (cache hit or resolver result — both count as processed).
- The summary's `total_purls` includes skipped/ignored/removed on top of the resolved set, so it may differ from `progress_total`. This is documented, expected behavior; the progress denominator is "PURLs being processed", which matches the user-facing meaning.

### `resolve_batch` (`service.py`)

Gains an optional parameter `on_progress: Callable[[int, int], Awaitable[None]] | None = None`, invoked in `_resolve_one` after each PURL finishes (inside the semaphore block). Default `None` keeps the PurlResolver page and all existing callers untouched.

### `JobManager._process_job` (`job_manager.py`)

Creates the reporter and wires it into the pipeline. It writes to the DB via the existing `repo.update_status` (status stays `running`; additionally `progress_current`, `progress_total`, `progress_phase`):

- `progress_total` is written immediately when known (start of `resolving`) so the UI can render 0/M right away.
- `progress_current` is **throttled to at most one write per 2 seconds**, in sync with the frontend poll interval. Rationale: the client reads the DB at most once per 2s, so more frequent writes add no visible freshness but multiply DB writes 4x (500ms) for zero gain; a 2s throttle keeps the stored value never older than the poll interval and is easy to reason about. The throttle stamp (`_last_write`) is set *before* the DB await so a burst of completions within one event-loop tick still coalesces into a single write.
- `progress_phase` is written on every phase change, unconditionally (no throttle).
- **Progress writes are conditional**: a dedicated `JobRepository.update_progress(job_id, **fields)` issues `UPDATE ... WHERE id = $N AND status = 'running' AND cancel_requested = 0`, so an in-flight progress write can never clobber a `cancelled` transition from `cancel_job` (which would otherwise leave the row stuck `running` with `cancel_requested=1` until restart). A final progress write on a cancelled job is a harmless no-op.
- A final write sets `progress_current = total` before the `completed` status update.
- DB write errors are logged as warnings and never fail the job.

### API (`routes/jobs.py`)

Add `"progress_phase": record.progress_phase` to the responses of `GET /api/v1/jobs/{job_id}` and `GET /api/v1/jobs` (list). It is `null` for queued jobs and legacy running jobs. `progress_current` / `progress_total` are already present.

## Frontend

### Types (`frontend/src/types/api.ts`)

Add `progress_phase: string | null` to `JobRecord`. The API client (`api/jobs.ts`) needs no changes.

### `SbomUpdater.vue` — job details, queued/running block

Replace the bare "(X / Y)" text with a progress section:

- **Phase label**: `t('sbomUpdater.phase.' + progress_phase)`; when phase is `null` (queued or legacy job) fall back to the existing `t('sbomUpdater.processing')`.
- **Progress bar** (rendered only when `progress_total > 0`): track + fill with `width: current / total * 100%`, filled with `--color-primary`, matching the existing theme; inline scoped styles in the same component, no new dependencies.
- **Counter text**: `{current} / {total} · {percent}%`, percent computed client-side.
- Spinner and Cancel button remain.

Polling is unchanged (2s interval, stops on terminal status).

### i18n (`frontend/src/i18n/locales/en.json`, `ru.json`)

```jsonc
"sbomUpdater": {
  "phase": {
    "parsing":        "Parsing SBOM"        / «Разбор SBOM»,
    "validating_refs": "Validating references" / «Проверка ссылок»,
    "resolving":      "Resolving PURLs"     / «Резолвинг PURL»,
    "enriching":      "Enriching SBOM"      / «Обогащение SBOM»
  },
  "progressCounter": "{current} / {total} · {percent}%"
}
```

No pluralization needed.

## Edge Cases

1. **`progress_total = 0`** (all PURLs invalid or nothing needs enrichment): `resolving` phase starts but the counter stays 0; UI hides the bar and shows the phase label + spinner. The job completes normally with a summary where `skipped > 0`.
2. **Cancellation during resolution**: progress simply stops updating; status `cancelled` is written by `cancel_job` and the worker task is cancelled. Conditional progress writes (see Backend) guarantee a racing progress write cannot flip the row back to `running` — the cancelled transition is final.
3. **DB write failure while reporting progress**: `log warning` and continue; the job must not fail because it cannot report progress. The terminal status write uses the existing code path as before.
4. **Legacy running jobs** (`progress_phase = NULL`): UI shows the fallback label, progress stays 0/0 — graceful degradation.
5. **`validating_refs` phase** appears only when `validate_sbom_refs` is enabled; otherwise the flow is `parsing → resolving → enriching`.
6. **Denominator mismatch**: `progress_total` counts resolvable PURLs; the final summary `total_purls` additionally includes skipped/ignored/removed. Expected and documented.

## Testing

Backend:

- `test_resolve_batch.py`: `on_progress` is called after each PURL with increasing `current` and the correct `total`; without the callback behavior is unchanged.
- Pipeline test (in `test_sbom_enrichment.py` or a new file): reporter receives phases in the right order and `total = len(unique_purls)`; a stub reporter does not break processing.
- `test_job_manager.py`: during resolution the job row has non-zero `progress_current` / `progress_total` and phase `resolving`; the final write before `completed` has `progress_current == progress_total`; the 2s throttle is verified with fake clocks; progress writes go through `update_progress` (conditional on running status).
- `test_routes_jobs.py`: `GET /api/v1/jobs/{id}` and the list return `progress_phase` (including `null` for queued).
- `test_job_repository.py`: round-trip of the new field; `update_progress` issues `UPDATE ... WHERE id = $N AND status = 'running' AND cancel_requested = 0` (regression guard for the cancel race).
- Migration: `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` runs at startup — existing table upgraded, restart idempotent.

Frontend:

- `SbomUpdater.test.ts`: running job with `progress_total > 0` renders the bar with correct width and percent; running job with `progress_total = 0` renders no bar; queued job shows the fallback label; phase label rendering; unknown phase falls back to the processing label.
