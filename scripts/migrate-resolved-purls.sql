-- Migration: remove unused columns from resolved_purls
-- Run manually after deploying schema-simplification code.
-- Optional backup (run before migration):
--   pg_dump -U sbom -d sbom --table=resolved_purls --data-only --column-inserts > resolved_purls_backup.sql

BEGIN;

CREATE TABLE resolved_purls_new (
    purl           TEXT PRIMARY KEY,
    repository_url TEXT NOT NULL,
    resolver       TEXT NOT NULL,
    resolved_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO resolved_purls_new (purl, repository_url, resolver, resolved_at)
SELECT purl, repository_url, resolver, resolved_at FROM resolved_purls;

ALTER TABLE resolved_purls RENAME TO resolved_purls_old;
ALTER TABLE resolved_purls_new RENAME TO resolved_purls;

COMMIT;

-- Verify:
-- SELECT COUNT(*) FROM resolved_purls;
-- SELECT COUNT(*) FROM resolved_purls_old;
-- Both should match.

-- Cleanup after verification period:
-- DROP TABLE resolved_purls_old;
