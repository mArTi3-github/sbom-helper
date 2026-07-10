-- Table for persisting SBOM enrichment job state and results.
-- Auto-created on application startup via CREATE TABLE IF NOT EXISTS.

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

-- Table for persisting successful PURL→repository_url resolution results.
-- Auto-created on application startup via CREATE TABLE IF NOT EXISTS.
-- Schema is extensible — new columns should be nullable or have defaults.

CREATE TABLE IF NOT EXISTS resolved_purls (
    purl              TEXT PRIMARY KEY,
    repository_url    TEXT NOT NULL,
    repository_type   TEXT,
    repository_kind   TEXT,
    confidence        TEXT,
    evidence          JSONB DEFAULT '[]',
    warnings          JSONB DEFAULT '[]',
    version_reference TEXT,
    resolver          TEXT NOT NULL DEFAULT 'purl2repo',
    resolved_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
