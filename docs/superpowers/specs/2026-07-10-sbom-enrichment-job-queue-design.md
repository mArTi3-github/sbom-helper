# SBOM Enrichment Job Queue — Design Document

## Problem

SBOM enrichment is a long-running process. Currently it runs synchronously within the HTTP request (`POST /api/v1/resolve/sbom`). If the user closes the browser tab or loses connectivity during enrichment, the result is lost — the enriched SBOM lives only in the server's RAM, while the server continues processing needlessly.

## Solution Overview

Replace the synchronous `POST /api/v1/resolve/sbom` with an async job-based flow:

- A new `jobs` table in PostgreSQL tracks task lifecycle: `queued → running → completed | failed | cancelled`
- An in-process asyncio worker dequeues jobs and processes them sequentially
- Input SBOM files and results are persisted on disk (volume `data/jobs/{job_id}/`)
- Per-PURL statistics are stored as JSON columns in the `jobs` table for immediate display
- The frontend polls job status and provides cancel/delete controls
- A configurable TTL (default 24h) auto-cleans old jobs and files

## Data Model: `jobs` Table

```sql
CREATE TABLE jobs (
    id               TEXT PRIMARY KEY,       -- uuid4
    type             TEXT NOT NULL,          -- 'sbom_enrich'
    status           TEXT NOT NULL,          -- queued | running | completed | failed | cancelled
    progress_current INTEGER DEFAULT 0,      -- components processed so far
    progress_total   INTEGER DEFAULT 0,      -- total components needing enrichment
    params_json      TEXT,                   -- options: remove_unresolved, ignore_patterns
    input_filename   TEXT,                   -- original filename for UI display
    result_path      TEXT,                   -- path to enriched SBOM file (completed only)
    summary_json     TEXT,                   -- {"total_purls": N, "found": N, "not_found": N, "skipped": N, "removed": N, "ignored": N}
    results_json     TEXT,                   -- [{"purl": "...", "status": "found|not_found|removed|ignored", "repository_url": "...", "found_by": "...", "resolver": "..."}]
    error_message    TEXT,                   -- error details (failed only)
    cancel_requested INTEGER DEFAULT 0,      -- boolean flag for cooperative cancellation
    created_at       TEXT NOT NULL,          -- ISO-8601
    started_at       TEXT,
    finished_at      TEXT
);
```

Table is created on app startup via schema migration (existing pattern in `storage/schema.sql`).

## File Storage

- **Input:** `data/jobs/{job_id}/input.json`
- **Result:** `data/jobs/{job_id}/result.json`

Files are deleted on cancel, manual delete, or TTL expiry.

## API Contract

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/jobs/sbom-enrich` | Accept multipart (file + options), create job, return `202 {job_id, status: "queued"}` |
| `GET` | `/api/v1/jobs/{job_id}` | Return status, progress, summary, results, timestamps |
| `GET` | `/api/v1/jobs/{job_id}/result` | Download enriched SBOM file (only `completed`), `Content-Disposition: attachment` |
| `POST` | `/api/v1/jobs/{job_id}/cancel` | Set `cancel_requested = 1`. If terminal status — `409 Conflict` |
| `DELETE` | `/api/v1/jobs/{job_id}` | Delete job record + files from disk immediately |
| `GET` | `/api/v1/jobs` | List recent jobs with pagination (`?limit=20&offset=0`) |

Old `POST /api/v1/resolve/sbom` is **removed**.

## Settings

A new option in the Settings section (persisted in `data/settings.json`):

- **job_ttl_hours** (integer, default: 24) — completed/cancelled/failed jobs older than this are auto-cleaned

## Internal Architecture

### App lifespan

1. Create `asyncio.Queue` (unbounded)
2. Start single worker coroutine `_job_worker` — sequentially processes jobs from the queue
3. Recovery: read all `queued` jobs from DB and re-enqueue; mark `running` jobs as `failed` with "Server restarted during processing"
4. Start clean-up task (every 60s): delete jobs where `finished_at < now - TTL`

### POST /api/v1/jobs/sbom-enrich

- Write `input.json` to `data/jobs/{job_id}/`
- Create `jobs` row with status `queued`
- Push `job_id` into `asyncio.Queue`
- Return `202 {job_id, status: "queued"}`

### Worker (`_job_worker`)

- Pull `job_id` from queue
- Set status → `running`, `started_at`
- Read `input.json`, parse SBOM
- Run `SbomEnrichmentPipeline.process()` with these modifications:
  - Before each component batch, check `cancel_requested` flag in DB; if set → stop, set status → `cancelled`, delete files
  - Periodically update `progress_current` in DB
- On success: write `result.json` to disk, store `summary_json` + `results_json`, set `completed`
- On error: set `failed`, store `error_message`

### Cancel

- `POST /api/v1/jobs/{id}/cancel` sets `cancel_requested = 1`
- Worker checks this flag cooperatively and aborts when set

## Frontend Changes (`SbomUpdater.vue`)

### Layout

- **Top section:** file upload + options (unchanged)
- **Bottom section:** "Recent Jobs" panel (top) + job details (bottom)
  - Recent Jobs: scrollable list of jobs (filename, status icon, creation time). Active job highlighted.
  - Job details: spinner for queued/running, summary cards + results table for completed, error message for failed

### Behavior

1. User clicks "Process" → `POST /api/v1/jobs/sbom-enrich` → job appears in Recent Jobs as `queued`
2. Client polls `GET /api/v1/jobs/{job_id}` every 2s, updates status/progress
3. On `completed`: load summary + results, display in details panel
4. On `cancelled`/`failed`: display appropriate message, inactive state
5. **Cancel** button: visible for `queued`/`running` → `POST /api/v1/jobs/{id}/cancel`
6. **Delete** button: visible for terminal statuses → `DELETE /api/v1/jobs/{id}`, removes from list
7. TTL setting: added to Settings page, persisted via existing settings infrastructure

### Removed

- `api/sbom.ts:resolveSbom()` — no longer needed
- `AbortController` logic — cancellation now server-side
- Direct response handling from POST

## Cancel vs Delete

| Action | Statuses | Effect |
|---|---|---|
| Cancel | `queued`, `running` | Stops processing, deletes partial data, status → `cancelled` |
| Delete | `completed`, `cancelled`, `failed` | Removes DB record + files immediately |

TTL auto-cleanup applies to all terminal-status jobs.

## Edge Cases

### Server restart during processing
- `running` jobs → marked `failed` on startup
- `queued` jobs → re-enqueued from DB

### Concurrent cancellation race
Worker checks `cancel_requested` before each component batch. If cancel arrives mid-batch, that batch finishes, then worker stops. No partial result is saved.

### Large result sets
`results_json` may contain thousands of entries (~2-3 MB for 10k components). PG TEXT handles this. The enriched SBOM itself (potentially much larger) is on disk.

### Two clicks on "Process"
No deduplication — each click creates a separate job. User can cancel duplicates manually.
