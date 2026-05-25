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
