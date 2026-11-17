-- Table for persisting SBOM enrichment job state and results.
-- Auto-created on application startup via CREATE TABLE IF NOT EXISTS.

CREATE TABLE IF NOT EXISTS jobs (
    id               TEXT PRIMARY KEY,
    type             TEXT NOT NULL,
    status           TEXT NOT NULL,
    progress_current INTEGER DEFAULT 0,
    progress_total   INTEGER DEFAULT 0,
    progress_phase   TEXT,
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

-- Idempotent migration for existing databases: CREATE TABLE IF NOT EXISTS
-- does not alter tables, so new columns are added explicitly.
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS progress_phase TEXT;

-- Table for persisting successful PURL→repository_url resolution results.
-- Auto-created on application startup via CREATE TABLE IF NOT EXISTS.
-- Schema is extensible — new columns should be nullable or have defaults.

CREATE TABLE IF NOT EXISTS resolved_purls (
    purl           TEXT PRIMARY KEY,
    repository_url TEXT NOT NULL,
    resolver       TEXT NOT NULL,
    resolved_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Table for caching source archive link lookups by PURL.
-- Auto-created on application startup via CREATE TABLE IF NOT EXISTS.

CREATE TABLE IF NOT EXISTS purl_source_archives (
    purl               TEXT PRIMARY KEY,
    version            TEXT NOT NULL,
    match_type         TEXT NOT NULL,
    reason             TEXT,
    archive_url        TEXT,
    archive_url_commit TEXT,
    matched_ref        TEXT,
    matched_ref_type   TEXT,
    matched_version    TEXT,
    repository_url     TEXT,
    resolver           TEXT NOT NULL,
    resolved_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_purl_source_archives_match_type
    ON purl_source_archives (match_type);
