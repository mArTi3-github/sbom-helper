# `resolved_purls` Schema Simplification — Design Document

## Problem

The `resolved_purls` table has 10 columns. Five of them (`repository_type`, `repository_kind`, `confidence`, `evidence`, `version_reference`) carry low practical value and are difficult to populate consistently across resolvers. `warnings` stores per-resolution diagnostics but is only meaningful at runtime — caching it in the DB table (which should store only successful resolution results) is unnecessary.

## Scope

**Remove columns from `resolved_purls`:** `repository_type`, `repository_kind`, `confidence`, `evidence`, `warnings`, `version_reference`.

**Keep:** `purl`, `repository_url`, `resolver`, `resolved_at` (unchanged).

**`warnings`** is removed from DB/CSV/inmemory storage but **retained in runtime** (resolver `Resolution`, API `ResolveResponse`, service layer) — the API endpoint `/api/v1/resolve` will still return warnings to the client.

## Final Table Schema

```sql
CREATE TABLE IF NOT EXISTS resolved_purls (
    purl           TEXT PRIMARY KEY,
    repository_url TEXT NOT NULL,
    resolver       TEXT NOT NULL,
    resolved_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

## Files Changed

### 1. Dataclass / Schema layer

| File | Change |
|---|---|
| `resolver/interface.py` — `Resolution` | Remove `repository_type`, `repository_kind`, `confidence`, `evidence`, `version_reference`. Keep `warnings`. |
| `schemas.py` — `ResolveResponse`, `PurlListParams` | Remove `repository_type`, `repository_kind`, `confidence`, `evidence`, `version_reference` from `ResolveResponse`. Remove `confidence` from `PurlListParams`. Keep `warnings` in `ResolveResponse`. |
| `storage/interface.py` — `PurlRow`, `UpsertRow`, `PurlFilters` | Remove all 6 columns. Remove `confidence` from `PurlFilters`. |

### 2. Resolvers

| File | Change |
|---|---|
| `resolver/purl2repo.py` | Remove `repository_type`, `repository_kind`, `confidence`, `evidence`, `version_reference` from return. Keep `warnings`. |
| `resolver/librariesio.py` | Remove `repository_type`, `repository_kind`, `confidence`, `evidence` from return. Keep `warnings`. |
| `resolver/ecosystems.py` | Same as librariesio. |

### 3. Service layer

| File | Change |
|---|---|
| `service.py` | Remove the 6 columns from `ResolveResponse` construction (lines 144-149). Keep `warnings` (line 148). Remove `evidence` from `store_preexisting_references` (line 209). |

### 4. Storage implementations

| File | Change |
|---|---|
| `storage/postgres.py` | Remove all 6 columns from all SQL statements (store, lookup, list, update_purl, upsert_many — 9 locations). Remove `confidence` from `_SORTABLE_COLUMNS` and `_build_filter_sql`. |
| `storage/inmemory.py` | Remove the 6 columns from `update_purl` and `upsert_many`. Remove `confidence` from `sort_keys` and `_matches_filters`. |
| `storage/schema.sql` | New DDL with 4 columns only. |

### 5. CSV I/O

| File | Change |
|---|---|
| `csv_io.py` | Remove all 6 columns from `parse_csv_import` and `render_csv_export`. |

### 6. Admin service

| File | Change |
|---|---|
| `db_admin_service.py` | Remove `confidence` from `PurlFilters` construction. |

### 7. Migration script

| File | Content |
|---|---|
| `scripts/migrate-resolved-purls.sql` | See Migration section below. |

### 8. Tests (~10-12 files)

Remove the 6 columns from all fixtures, assertions, and test helpers in:
- `tests/test_storage.py`
- `tests/test_api.py`
- `tests/test_service_validation.py`
- `tests/test_db_admin_service.py`
- `tests/test_db_admin.py`
- `tests/test_csv_io.py`
- `tests/test_resolve_batch.py`
- `tests/conftest.py`
- `tests/test_ecosystems_resolver.py`
- `tests/test_librariesio_resolver.py`
- `tests/test_purl2repo_resolver.py`
- `tests/e2e/test_postgres.py`
- `tests/e2e/test_ecosystems.py`
- `tests/test_librariesio_integration.py`

Keep `warnings` assertions where they test runtime behavior (resolver warnings, API warnings). Remove them only where they test DB/CSV persistence of warnings.

## Migration Strategy

A one-time SQL script (`scripts/migrate-resolved-purls.sql`) to be run manually:

```sql
-- Optional: pg_dump backup (run before migration)
-- pg_dump -U sbom -d sbom --table=resolved_purls --data-only --column-inserts > resolved_purls_backup.sql

BEGIN;

-- Step 1: create new table with final schema
CREATE TABLE resolved_purls_new (
    purl           TEXT PRIMARY KEY,
    repository_url TEXT NOT NULL,
    resolver       TEXT NOT NULL,
    resolved_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Step 2: migrate only the kept columns (7M rows — expect minutes)
INSERT INTO resolved_purls_new (purl, repository_url, resolver, resolved_at)
SELECT purl, repository_url, resolver, resolved_at FROM resolved_purls;

-- Step 3: verify row count
-- (uncomment after step 2 to check)
-- SELECT 'old' AS tbl, COUNT(*) FROM resolved_purls
-- UNION ALL
-- SELECT 'new', COUNT(*) FROM resolved_purls_new;

-- Step 4: swap tables (millisecond downtime window)
ALTER TABLE resolved_purls RENAME TO resolved_purls_old;
ALTER TABLE resolved_purls_new RENAME TO resolved_purls;

COMMIT;

-- Cleanup (after verification period, days later):
-- DROP TABLE resolved_purls_old;
```

The script is idempotent (fails fast if `resolved_purls_new` already exists). The `_old` table is kept as an instant rollback mechanism — reversing the rename restores the original state.

## Rollback

1. Revert code changes (git checkout)
2. Swap table names back:
   ```sql
   BEGIN;
   ALTER TABLE resolved_purls RENAME TO resolved_purls_new;
   ALTER TABLE resolved_purls_old RENAME TO resolved_purls;
   COMMIT;
   ```
3. Optionally drop `resolved_purls_new`
