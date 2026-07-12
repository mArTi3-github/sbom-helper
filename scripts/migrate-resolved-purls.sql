-- Migration: remove unused columns from resolved_purls
-- Run manually AFTER deploying schema-simplification code (NOT before).
-- Optional backup (run before migration):
--   pg_dump -U sbom -d sbom --table=resolved_purls --data-only --column-inserts > resolved_purls_backup.sql

-- Guard: abort if the old columns are already gone (migration already applied or wrong schema).
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'resolved_purls' AND column_name = 'version_reference'
  ) THEN
    RAISE EXCEPTION 'resolved_purls already migrated or schema unexpected — aborting';
  END IF;
END $$;

BEGIN;

-- Disable statement timeout for this session (7M rows may take time).
SET statement_timeout = 0;

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
