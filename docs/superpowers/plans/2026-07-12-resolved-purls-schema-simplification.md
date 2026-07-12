# `resolved_purls` Schema Simplification — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove 6 columns (`repository_type`, `repository_kind`, `confidence`, `evidence`, `warnings`, `version_reference`) from `resolved_purls` table and all storage-layer code. Keep `warnings` in runtime (resolver `Resolution`, API `ResolveResponse`).

**Architecture:** Dataclass/schema changes propagate outward: resolver interfaces → storage interfaces → storage implementations → CSV → migration script → tests.

**Tech Stack:** Python 3.12+, FastAPI, asyncpg, Pydantic, dataclasses, pytest.

## Global Constraints

- `resolved_purls` final columns: `purl`, `repository_url`, `resolver`, `resolved_at` only
- `resolver` column: `TEXT NOT NULL` (no default)
- `warnings` is removed from DB/CSV/inmemory storage but kept in `Resolution` (resolver/interface.py) and `ResolveResponse` (schemas.py)
- All existing tests must pass after changes; no new functionality

---

### Task 1: Core dataclasses — resolver/interface.py and schemas.py

**Files:**
- Modify: `src/purl_resolver/resolver/interface.py:23-28`
- Modify: `src/purl_resolver/schemas.py:19-24,59-63`

**Interfaces:**
- Consumes: nothing (root of dependency tree)
- Produces: updated `Resolution` and `ResolveResponse` dataclasses for all downstream tasks

- [ ] **Step 1: Edit `resolver/interface.py` — remove 5 fields from `Resolution`**

```python
@dataclass(frozen=True)
class Resolution:
    purl: str
    repository_url: str | None = None
    warnings: list[str] = field(default_factory=list)
```

- [ ] **Step 2: Edit `schemas.py` — remove 5 fields from `ResolveResponse`, remove `confidence` from `PurlListParams`**

```python
class ResolveResponse(BaseModel):
    purl: str
    repository_url: str | None = None
    warnings: list[str] = []
    resolver: str = ""
    found_by: str = ""
    resolved_at: str = ""
```

Remove `confidence: str | None = None` from `PurlListParams` (line 59).

- [ ] **Step 3: Run tests that directly use these models to verify no import regressions**

Run: `.venv/bin/python -c "from src.purl_resolver.resolver.interface import Resolution; from src.purl_resolver.schemas import ResolveResponse; print('OK')"`
Expected: OK

- [ ] **Step 4: Commit**

```bash
git add src/purl_resolver/resolver/interface.py src/purl_resolver/schemas.py
git commit -m "refactor: remove unused fields from Resolution and ResolveResponse"
```

---

### Task 2: Storage interfaces — PurlRow, UpsertRow, PurlFilters

**Files:**
- Modify: `src/purl_resolver/storage/interface.py:10-73`

**Interfaces:**
- Consumes: updated `ResolveResponse` from Task 1 (used in `from_response`/`to_resolve_response`)
- Produces: updated `PurlRow`, `UpsertRow`, `PurlFilters` for Tasks 3-5

- [ ] **Step 1: Remove 6 fields from `PurlFilters`**

```python
@dataclass
class PurlFilters:
    search: str | None = None
    resolver: str | None = None
    date_from: date | None = None
    date_to: date | None = None
```

- [ ] **Step 2: Remove 6 fields from `PurlRow`**

```python
@dataclass
class PurlRow:
    purl: str
    repository_url: str
    resolver: str = ""
    resolved_at: str = ""
```

- [ ] **Step 3: Update `PurlRow.from_response` and `to_resolve_response`** — remove the 6 fields from both methods

```python
@classmethod
def from_response(cls, r: ResolveResponse) -> PurlRow:
    return cls(
        purl=r.purl,
        repository_url=r.repository_url,
        resolver=r.resolver,
        resolved_at=r.resolved_at or "",
    )

def to_resolve_response(self) -> ResolveResponse:
    return ResolveResponse(
        purl=self.purl,
        repository_url=self.repository_url,
        resolver=self.resolver,
        resolved_at=self.resolved_at,
    )
```

- [ ] **Step 4: Remove 6 fields from `UpsertRow`**

```python
@dataclass
class UpsertRow:
    purl: str
    repository_url: str
    resolver: str = "purl2repo"
```

- [ ] **Step 5: Commit**

```bash
git add src/purl_resolver/storage/interface.py
git commit -m "refactor: remove unused fields from PurlRow, UpsertRow, PurlFilters"
```

---

### Task 3: Resolvers — purl2repo, librariesio, ecosystems

**Files:**
- Modify: `src/purl_resolver/resolver/purl2repo.py:71-82`
- Modify: `src/purl_resolver/resolver/librariesio.py:90-97`
- Modify: `src/purl_resolver/resolver/ecosystems.py:97-104`

**Interfaces:**
- Consumes: updated `Resolution` from Task 1
- Produces: updated `Resolution` objects with only `purl`, `repository_url`, `warnings`

- [ ] **Step 1: Edit `purl2repo.py` — remove 5 fields from return**

```python
return Resolution(
    purl=purl,
    repository_url=result.repository_url,
    warnings=list(result.warnings),
)
```

- [ ] **Step 2: Edit `librariesio.py` — remove 4 fields from return**

```python
return Resolution(
    purl=purl,
    repository_url=repo_url,
)
```

- [ ] **Step 3: Edit `ecosystems.py` — remove 4 fields from return**

```python
return Resolution(
    purl=purl,
    repository_url=repo_url,
)
```

- [ ] **Step 4: Run resolver unit tests to verify they still pass**

Run: `.venv/bin/python -m pytest tests/test_ecosystems_resolver.py tests/test_librariesio_resolver.py tests/test_purl2repo_resolver.py -v --no-header -q 2>&1 | tail -20`
Expected: all passing

- [ ] **Step 5: Commit**

```bash
git add src/purl_resolver/resolver/purl2repo.py src/purl_resolver/resolver/librariesio.py src/purl_resolver/resolver/ecosystems.py
git commit -m "refactor: remove unused fields from resolver return values"
```

---

### Task 4: Service layer

**Files:**
- Modify: `src/purl_resolver/service.py:141-151,162-167,206-211`

**Interfaces:**
- Consumes: updated `Resolution` (Task 1), updated `ResolveResponse` (Task 1), updated `Storage.store` (Tasks 5-6 will match)
- Produces: updated `ResolveResponse` with only purl, repository_url, warnings, resolver, found_by, resolved_at

- [ ] **Step 1: Edit `resolve_purl` — remove 6 fields from `ResolveResponse` construction (lines 141-151)**

Replace:
```python
response = ResolveResponse(
    purl=purl_key,
    repository_url=repo_url,
    repository_type=resolution.repository_type,
    repository_kind=resolution.repository_kind,
    confidence=resolution.confidence,
    evidence=list(resolution.evidence),
    warnings=list(resolution.warnings),
    version_reference=resolution.version_reference,
    resolver=r.name,
    found_by="resolver",
)
```
With:
```python
response = ResolveResponse(
    purl=purl_key,
    repository_url=repo_url,
    warnings=list(resolution.warnings),
    resolver=r.name,
    found_by="resolver",
)
```

- [ ] **Step 2: Update the "no URL found" fallback (line 162-167)** — no change needed, `ResolveResponse` still accepts `warnings`

- [ ] **Step 3: Update `store_preexisting_references` (line 206-211)** — remove `evidence`

Replace:
```python
await self._storage.store(ResolveResponse(
    purl=purl_key,
    repository_url=vcs_refs[0]["url"],
    evidence=["from SBOM externalReferences"],
    resolver=resolver,
))
```
With:
```python
await self._storage.store(ResolveResponse(
    purl=purl_key,
    repository_url=vcs_refs[0]["url"],
    resolver=resolver,
))
```

- [ ] **Step 4: Run service tests**

Run: `.venv/bin/python -m pytest tests/test_service_validation.py -v --no-header -q 2>&1 | tail -20`
Expected: all passing

- [ ] **Step 5: Commit**

```bash
git add src/purl_resolver/service.py
git commit -m "refactor: remove unused fields from service layer construction"
```

---

### Task 5: PostgreSQL storage implementation

**Files:**
- Modify: `src/purl_resolver/storage/postgres.py`

**Interfaces:**
- Consumes: updated `PurlRow`, `UpsertRow` (Task 2)
- Produces: PostgreSQL storage with only 4 columns in all SQL

- [ ] **Step 1: Update `lookup()` — remove 6 fields from row reading (lines 49-60)**

```python
return PurlRow(
    purl=row["purl"],
    repository_url=row["repository_url"],
    resolver=row.get("resolver", ""),
    resolved_at=str(row.get("resolved_at", "")),
).to_resolve_response()
```

- [ ] **Step 2: Update `store()` — remove 6 columns from INSERT/UPDATE (lines 64-90)**

```python
await conn.execute(
    """
    INSERT INTO resolved_purls (
        purl, repository_url, resolver
    ) VALUES ($1, $2, $3)
    ON CONFLICT (purl) DO UPDATE SET
        repository_url = EXCLUDED.repository_url,
        resolver = EXCLUDED.resolver,
        resolved_at = NOW()
    """,
    result.purl,
    result.repository_url,
    result.resolver or "purl2repo",
)
```

- [ ] **Step 3: Update `_SORTABLE_COLUMNS` — remove `confidence`**

```python
_SORTABLE_COLUMNS: frozenset[str] = frozenset({
    "purl", "repository_url", "resolver", "resolved_at",
})
```

- [ ] **Step 4: Update `_build_filter_sql()` — remove `confidence` filter block (lines 114-116)**

Remove:
```python
if filters.confidence is not None:
    clauses.append(f"confidence = ${idx}")
    params.append(filters.confidence)
    idx += 1
```

- [ ] **Step 5: Update `list_purls()` — remove 6 fields from row reading (lines 153-166)**

```python
return [
    PurlRow(
        purl=r["purl"],
        repository_url=r["repository_url"],
        resolver=r.get("resolver", "purl2repo"),
        resolved_at=str(r["resolved_at"]),
    )
    for r in rows
]
```

- [ ] **Step 6: Update `update_purl()` — remove 6 columns from INSERT on rename (lines 193-210)**

Replace the entire `else` block:
```python
else:
    await conn.execute(
        "DELETE FROM resolved_purls WHERE purl = $1", old_purl
    )
    await conn.execute(
        """INSERT INTO resolved_purls (
            purl, repository_url, resolver
        ) VALUES ($1, $2, $3)""",
        purl,
        repository_url,
        existing.get("resolver", "purl2repo"),
    )
```

- [ ] **Step 7: Update `upsert_many()` — remove 6 columns from INSERT/UPDATE (lines 235-259)**

```python
await conn.execute(
    """INSERT INTO resolved_purls (
        purl, repository_url, resolver
    ) VALUES ($1, $2, $3)
    ON CONFLICT (purl) DO UPDATE SET
        repository_url = EXCLUDED.repository_url,
        resolver = EXCLUDED.resolver,
        resolved_at = NOW()""",
    row.purl,
    row.repository_url,
    row.resolver,
)
```

- [ ] **Step 8: Commit**

```bash
git add src/purl_resolver/storage/postgres.py
git commit -m "refactor: remove unused columns from postgres storage"
```

---

### Task 6: InMemory storage implementation

**Files:**
- Modify: `src/purl_resolver/storage/inmemory.py`

**Interfaces:**
- Consumes: updated `PurlRow`, `ResolveResponse` (Tasks 1-2)
- Produces: in-memory storage without the 6 fields

- [ ] **Step 1: Remove `confidence` from `sort_keys` (line 40)**

Remove `"confidence": lambda x: x.confidence or "",`

- [ ] **Step 2: Remove `confidence` filter check from `_matches_filters` (lines 55-56)**

Remove:
```python
if filters.confidence and filters.confidence != r.confidence:
    return False
```

- [ ] **Step 3: Update `update_purl()` — remove 5 fields (lines 85-94)**

```python
updated = ResolveResponse(
    purl=purl,
    repository_url=repository_url,
)
```

- [ ] **Step 4: Update `upsert_many()` — remove 5 fields (lines 117-126)**

```python
self._store[row.purl] = ResolveResponse(
    purl=row.purl,
    repository_url=row.repository_url,
)
```

- [ ] **Step 5: Commit**

```bash
git add src/purl_resolver/storage/inmemory.py
git commit -m "refactor: remove unused fields from inmemory storage"
```

---

### Task 7: CSV I/O

**Files:**
- Modify: `src/purl_resolver/csv_io.py`

**Interfaces:**
- Consumes: updated `PurlRow`, `UpsertRow` (Task 2)
- Produces: CSV that writes/reads only 4 columns

- [ ] **Step 1: Update `parse_csv_import()` — remove 6 field reads (lines 35-48)**

```python
rows.append(UpsertRow(
    purl=purl,
    repository_url=repo,
    resolver=row.get("resolver") or "import-csv",
))
```

Also remove the `_parse_jsonb_field` calls for `evidence` and `warnings` and the variables.

- [ ] **Step 2: Update `render_csv_export()` — remove 6 columns from header and data rows (lines 68-85)**

```python
writer.writerow([
    "purl", "repository_url", "resolver", "resolved_at",
])
for r in rows:
    writer.writerow([
        r.purl,
        r.repository_url,
        r.resolver,
        r.resolved_at,
    ])
```

- [ ] **Step 3: Update `_parse_jsonb_field` — check if still needed**

After removing `evidence` and `warnings` from `parse_csv_import`, `_parse_jsonb_field` is no longer called anywhere. Remove the function entirely.

- [ ] **Step 4: Commit**

```bash
git add src/purl_resolver/csv_io.py
git commit -m "refactor: remove unused columns from CSV I/O"
```

---

### Task 8: DB admin service

**Files:**
- Modify: `src/purl_resolver/db_admin_service.py:32-38`

**Interfaces:**
- Consumes: updated `PurlFilters` (Task 2)
- Produces: same API contract but without `confidence` filter

- [ ] **Step 1: Remove `confidence=params.confidence` from `PurlFilters` construction (line 35)**

```python
filters = PurlFilters(
    search=params.search,
    resolver=params.resolver,
    date_from=params.date_from,
    date_to=params.date_to,
)
```

- [ ] **Step 2: Commit**

```bash
git add src/purl_resolver/db_admin_service.py
git commit -m "refactor: remove confidence filter from db admin service"
```

---

### Task 9: Migration script

**Files:**
- Create: `scripts/migrate-resolved-purls.sql`

- [ ] **Step 1: Create `scripts/migrate-resolved-purls.sql`**

```sql
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
```

- [ ] **Step 2: Commit**

```bash
git add scripts/migrate-resolved-purls.sql
git commit -m "feat: add migration script for resolved_purls schema"
```

---

### Task 10: Update schema.sql

**Files:**
- Modify: `src/purl_resolver/storage/schema.sql`

- [ ] **Step 1: Update DDL to 4 columns only**

```sql
CREATE TABLE IF NOT EXISTS resolved_purls (
    purl           TEXT PRIMARY KEY,
    repository_url TEXT NOT NULL,
    resolver       TEXT NOT NULL,
    resolved_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

- [ ] **Step 2: Commit**

```bash
git add src/purl_resolver/storage/schema.sql
git commit -m "refactor: update schema.sql to 4-column resolved_purls"
```

---

### Task 11: Update tests — storage tests

**Files:**
- Modify: `tests/test_storage.py`

- [ ] **Step 1: Remove the 6 fields from all test fixtures and assertions**

All fixtures in `test_storage.py` use `repository_type`, `repository_kind`, `confidence`, `evidence`, `warnings`, `version_reference`. Remove them from every dict and assertion.

- [ ] **Step 2: Run to verify**

Run: `.venv/bin/python -m pytest tests/test_storage.py -v --no-header -q 2>&1 | tail -20`
Expected: all passing

- [ ] **Step 3: Commit**

```bash
git add tests/test_storage.py
git commit -m "test: update storage tests for simplified schema"
```

---

### Task 12: Update tests — API tests

**Files:**
- Modify: `tests/test_api.py`

- [ ] **Step 1: Remove 6 fields from fixtures and assertions**

Remove `repository_type`, `repository_kind`, `confidence`, `evidence`, `warnings`, `version_reference` from `purl_row_dict` fixtures. Keep the assertions that verify `warnings` is a list in the response (it's still in `ResolveResponse`).

- [ ] **Step 2: Run to verify**

Run: `.venv/bin/python -m pytest tests/test_api.py -v --no-header -q 2>&1 | tail -20`
Expected: all passing

- [ ] **Step 3: Commit**

```bash
git add tests/test_api.py
git commit -m "test: update API tests for simplified schema"
```

---

### Task 13: Update tests — service validation tests

**Files:**
- Modify: `tests/test_service_validation.py`

- [ ] **Step 1: Remove 6 fields from all fixtures**

Remove from every `purl_dict`/`row` construction. Keep `warnings` in test data (it's still in runtime).

- [ ] **Step 2: Run to verify**

Run: `.venv/bin/python -m pytest tests/test_service_validation.py -v --no-header -q 2>&1 | tail -20`
Expected: all passing

- [ ] **Step 3: Commit**

```bash
git add tests/test_service_validation.py
git commit -m "test: update service validation tests for simplified schema"
```

---

### Task 14: Update tests — CSV I/O tests

**Files:**
- Modify: `tests/test_csv_io.py`

- [ ] **Step 1: Remove 6 columns from CSV test data and assertions**

Update all test CSV strings and row constructions. Remove assertions on the 5 deleted columns. Keep assertions on `warnings` only if testing API-level behavior (not CSV persistence).

- [ ] **Step 2: Run to verify**

Run: `.venv/bin/python -m pytest tests/test_csv_io.py -v --no-header -q 2>&1 | tail -20`
Expected: all passing

- [ ] **Step 3: Commit**

```bash
git add tests/test_csv_io.py
git commit -m "test: update CSV tests for simplified schema"
```

---

### Task 15: Update tests — DB admin tests

**Files:**
- Modify: `tests/test_db_admin.py`, `tests/test_db_admin_service.py`

- [ ] **Step 1: Remove 5-6 fields from all fixtures and assertions**

- In `test_db_admin_service.py`: remove `repository_type`, `repository_kind`, `confidence` from fixtures
- In `test_db_admin.py`: remove all 6 from fixtures, update `confidence` query param test, update column list assertions

- [ ] **Step 2: Run to verify**

Run: `.venv/bin/python -m pytest tests/test_db_admin.py tests/test_db_admin_service.py -v --no-header -q 2>&1 | tail -20`
Expected: all passing

- [ ] **Step 3: Commit**

```bash
git add tests/test_db_admin.py tests/test_db_admin_service.py
git commit -m "test: update db admin tests for simplified schema"
```

---

### Task 16: Update tests — resolver tests (ecosystems, librariesio, purl2repo)

**Files:**
- Modify: `tests/test_ecosystems_resolver.py`
- Modify: `tests/test_librariesio_resolver.py`
- Modify: `tests/test_purl2repo_resolver.py`

- [ ] **Step 1: Remove assertions on deleted fields**

Remove `assert result.repository_kind`, `assert result.confidence`, `assert result.evidence` lines. Keep assertions on `warnings`.

- [ ] **Step 2: Run to verify**

Run: `.venv/bin/python -m pytest tests/test_ecosystems_resolver.py tests/test_librariesio_resolver.py tests/test_purl2repo_resolver.py -v --no-header -q 2>&1 | tail -20`
Expected: all passing

- [ ] **Step 3: Commit**

```bash
git add tests/test_ecosystems_resolver.py tests/test_librariesio_resolver.py tests/test_purl2repo_resolver.py
git commit -m "test: update resolver tests for simplified schema"
```

---

### Task 17: Update tests — e2e tests and conftest

**Files:**
- Modify: `tests/e2e/test_postgres.py`
- Modify: `tests/e2e/test_ecosystems.py`
- Modify: `tests/conftest.py`
- Modify: `tests/test_resolve_batch.py`
- Modify: `tests/test_librariesio_integration.py`

- [ ] **Step 1: Remove 5-6 fields from fixtures and assertions in each file**

`tests/conftest.py:16-19` — remove from fixture
`tests/e2e/test_postgres.py:46-51,60-65,103-108,129-134,142-163,203,231,305` — remove fields
`tests/e2e/test_ecosystems.py:22-24` — remove assertion on `version_reference` etc.
`tests/test_resolve_batch.py` — remove from fixtures
`tests/test_librariesio_integration.py` — keep warnings tests (they test runtime only)

- [ ] **Step 2: Run to verify**

Run: `.venv/bin/python -m pytest tests/ -v --no-header -q 2>&1 | tail -40`
Expected: all passing

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/test_postgres.py tests/e2e/test_ecosystems.py tests/conftest.py tests/test_resolve_batch.py tests/test_librariesio_integration.py
git commit -m "test: update e2e and integration tests for simplified schema"
```

---

### Task 18: Final verification

- [ ] **Step 1: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -v --no-header -q 2>&1 | tail -40`
Expected: all tests passing

- [ ] **Step 2: Run linter**

Run: `ruff check src/ tests/` (or equivalent)
Expected: no errors
