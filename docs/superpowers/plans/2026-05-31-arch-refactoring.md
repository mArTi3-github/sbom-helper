# Architecture Refactoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract CSV logic into csv_io module, type upsert_many with UpsertRow, eliminate PurlRowResponse.

**Architecture:** Three focused refactoring tasks: (1) new csv_io module with pure functions for CSV parsing/rendering, (2) UpsertRow dataclass replaces untyped dict in upsert_many interface, (3) PurlRowResponse deleted, ResolveResponse used directly at API boundary.

**Tech Stack:** Python, pytest, csv stdlib module

---

## File Map

| Action | File | Purpose |
|--------|------|---------|
| Modify | `src/purl_resolver/storage/interface.py` | Add UpsertRow dataclass, update upsert_many signature |
| Modify | `src/purl_resolver/storage/inmemory.py` | Read UpsertRow fields directly |
| Modify | `src/purl_resolver/storage/postgres.py` | Read UpsertRow fields directly |
| Create | `src/purl_resolver/csv_io.py` | Pure CSV parsing/rendering functions |
| Modify | `src/purl_resolver/router.py` | Delegate CSV logic to csv_io |
| Modify | `src/purl_resolver/schemas.py` | Remove PurlRowResponse, update PurlListResponse |
| Modify | `tests/test_db_admin.py` | Update tests for new interfaces |

---

### Task 1: Add UpsertRow dataclass to storage interface

**Files:**
- Modify: `src/purl_resolver/storage/interface.py`

- [ ] **Step 1: Add UpsertRow and update upsert_many signature**

Read `src/purl_resolver/storage/interface.py`. Add the UpsertRow dataclass before the Storage ABC. Update the upsert_many signature.

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date

from ..schemas import ResolveResponse


@dataclass
class PurlFilters:
    search: str | None = None
    resolver: str | None = None
    confidence: str | None = None
    date_from: date | None = None
    date_to: date | None = None


@dataclass
class PurlRow:
    purl: str
    repository_url: str
    repository_type: str | None
    repository_kind: str | None
    confidence: str | None
    evidence: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    version_reference: str | None = None
    resolver: str = ""
    resolved_at: str = ""


@dataclass
class UpsertRow:
    purl: str
    repository_url: str
    repository_type: str | None = None
    repository_kind: str | None = None
    confidence: str | None = None
    evidence: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    version_reference: str | None = None
    resolver: str = "purl2repo"


class Storage(ABC):

    @abstractmethod
    async def lookup(self, purl: str) -> ResolveResponse | None: ...

    @abstractmethod
    async def store(self, result: ResolveResponse) -> None: ...

    @abstractmethod
    async def list_purls(
        self,
        offset: int,
        limit: int,
        filters: PurlFilters,
        sort_by: str = "resolved_at",
        sort_order: str = "desc",
    ) -> list[PurlRow]: ...

    @abstractmethod
    async def count_purls(self, filters: PurlFilters) -> int: ...

    @abstractmethod
    async def update_purl(
        self, old_purl: str, purl: str, repository_url: str
    ) -> bool: ...

    @abstractmethod
    async def delete_purls(self, purls: list[str]) -> int: ...

    @abstractmethod
    async def upsert_many(
        self, rows: list[UpsertRow]
    ) -> tuple[int, int]: ...
```

- [ ] **Step 2: Verify existing tests still pass**

Run: `.venv/bin/pytest tests/ --ignore=tests/e2e -q`

Expected: Tests that call upsert_many with dicts will fail (type mismatch). This is expected — Tasks 2 and 3 fix the implementations.

- [ ] **Step 3: Commit**

```bash
git add src/purl_resolver/storage/interface.py
git commit -m "refactor: add UpsertRow dataclass, update upsert_many signature"
```

---

### Task 2: Update InMemoryCache for UpsertRow

**Files:**
- Modify: `src/purl_resolver/storage/inmemory.py`

- [ ] **Step 1: Rewrite upsert_many to use UpsertRow**

Replace the existing `upsert_many` method. The new implementation reads typed fields directly — no more `str(row.get(...))` or `json.loads()`.

```python
async def upsert_many(
    self, rows: list[UpsertRow]
) -> tuple[int, int]:
    upserted = 0
    errors = 0
    for row in rows:
        if not row.purl or not row.repository_url:
            errors += 1
            continue
        self._store[row.purl] = ResolveResponse(
            purl=row.purl,
            repository_url=row.repository_url,
            repository_type=row.repository_type,
            repository_kind=row.repository_kind,
            confidence=row.confidence,
            evidence=row.evidence,
            warnings=row.warnings,
            version_reference=row.version_reference,
        )
        upserted += 1
    return (upserted, errors)
```

Also add the import at the top: `from .interface import PurlFilters, PurlRow, UpsertRow, Storage`

- [ ] **Step 2: Run tests**

Run: `.venv/bin/pytest tests/test_db_admin.py -v`

Expected: All 42 tests pass.

- [ ] **Step 3: Commit**

```bash
git add src/purl_resolver/storage/inmemory.py
git commit -m "refactor: InMemoryCache upsert_many reads UpsertRow fields directly"
```

---

### Task 3: Update PostgresCache for UpsertRow

**Files:**
- Modify: `src/purl_resolver/storage/postgres.py`

- [ ] **Step 1: Rewrite upsert_many to use UpsertRow**

Replace the existing `upsert_many` method. Remove all `row.get(...)` and `json.loads()` calls — read typed fields directly.

```python
async def upsert_many(
    self, rows: list[UpsertRow]
) -> tuple[int, int]:
    upserted = 0
    errors = 0

    async with self._pool.acquire() as conn:
        async with conn.transaction():
            for row in rows:
                if not row.purl or not row.repository_url:
                    errors += 1
                    continue

                await conn.execute(
                    """INSERT INTO resolved_purls (
                        purl, repository_url, repository_type, repository_kind,
                        confidence, evidence, warnings, version_reference, resolver
                    ) VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb, $8, $9)
                    ON CONFLICT (purl) DO UPDATE SET
                        repository_url = EXCLUDED.repository_url,
                        repository_type = EXCLUDED.repository_type,
                        repository_kind = EXCLUDED.repository_kind,
                        confidence = EXCLUDED.confidence,
                        evidence = EXCLUDED.evidence,
                        warnings = EXCLUDED.warnings,
                        version_reference = EXCLUDED.version_reference,
                        resolver = EXCLUDED.resolver,
                        resolved_at = NOW()""",
                    row.purl,
                    row.repository_url,
                    row.repository_type,
                    row.repository_kind,
                    row.confidence,
                    json.dumps(row.evidence),
                    json.dumps(row.warnings),
                    row.version_reference,
                    row.resolver,
                )
                upserted += 1

    return (upserted, errors)
```

Also add the import: `from .interface import PurlFilters, PurlRow, UpsertRow, Storage`

- [ ] **Step 2: Run tests**

Run: `.venv/bin/pytest tests/test_db_admin.py -v`

Expected: All 42 tests pass.

- [ ] **Step 3: Commit**

```bash
git add src/purl_resolver/storage/postgres.py
git commit -m "refactor: PostgresCache upsert_many reads UpsertRow fields directly"
```

---

### Task 4: Create csv_io module

**Files:**
- Create: `src/purl_resolver/csv_io.py`
- Create: `tests/test_csv_io.py`

- [ ] **Step 1: Write tests for csv_io**

Create `tests/test_csv_io.py`:

```python
from __future__ import annotations

import csv
import io

from purl_resolver.csv_io import detect_delimiter, parse_csv_import, render_csv_export
from purl_resolver.storage.interface import UpsertRow, PurlRow


class TestDetectDelimiter:
    def test_semicolon(self):
        assert detect_delimiter("purl;repository_url") == ";"

    def test_comma(self):
        assert detect_delimiter("purl,repository_url") == ","

    def test_default_semicolon(self):
        assert detect_delimiter("single_column") == ";"


class TestParseCsvImport:
    def test_basic_import(self):
        text = "purl;repository_url\npkg:pypi/test;https://github.com/test\n"
        rows, errors = parse_csv_import(text)
        assert len(rows) == 1
        assert len(errors) == 0
        assert rows[0].purl == "pkg:pypi/test"
        assert rows[0].repository_url == "https://github.com/test"

    def test_empty_purl_error(self):
        text = "purl;repository_url\n;https://github.com/test\n"
        rows, errors = parse_csv_import(text)
        assert len(rows) == 0
        assert len(errors) == 1
        assert "empty purl" in errors[0]["error"]

    def test_empty_repository_url_error(self):
        text = "purl;repository_url\npkg:pypi/test;\n"
        rows, errors = parse_csv_import(text)
        assert len(rows) == 0
        assert len(errors) == 1
        assert "empty repository_url" in errors[0]["error"]

    def test_optional_columns(self):
        text = "purl;repository_url;confidence;resolver\npkg:pypi/test;https://github.com/test;high;custom\n"
        rows, errors = parse_csv_import(text)
        assert len(rows) == 1
        assert rows[0].confidence == "high"
        assert rows[0].resolver == "custom"

    def test_jsonb_fields(self):
        text = 'purl;repository_url;evidence;warnings\npkg:pypi/test;https://github.com/test;["reason1"];["warn1"]\n'
        rows, errors = parse_csv_import(text)
        assert len(rows) == 1
        assert rows[0].evidence == ["reason1"]
        assert rows[0].warnings == ["warn1"]

    def test_bom_handled(self):
        text = "\ufeffpurl;repository_url\npkg:pypi/test;https://github.com/test\n"
        rows, errors = parse_csv_import(text)
        assert len(rows) == 1
        assert rows[0].purl == "pkg:pypi/test"

    def test_trailing_newlines(self):
        text = "purl;repository_url\npkg:pypi/test;https://github.com/test\n\n\n"
        rows, errors = parse_csv_import(text)
        assert len(rows) == 1

    def test_missing_columns(self):
        text = "purl\npkg:pypi/test\n"
        rows, errors = parse_csv_import(text)
        assert len(rows) == 0
        assert len(errors) == 1
        assert "repository_url" in errors[0]["error"]


class TestRenderCsvExport:
    def test_basic_export(self):
        rows = [PurlRow(
            purl="pkg:pypi/test",
            repository_url="https://github.com/test",
            repository_type="github",
            repository_kind="source_code",
            confidence="high",
            evidence=["reason1"],
            warnings=[],
            version_reference=None,
            resolver="purl2repo",
            resolved_at="2026-05-31 12:00:00",
        )]
        result = render_csv_export(rows)
        assert "pkg:pypi/test" in result
        assert "https://github.com/test" in result
        assert ";" in result

    def test_empty_export(self):
        result = render_csv_export([])
        lines = result.strip().split("\n")
        assert len(lines) == 1  # header only
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_csv_io.py -v`

Expected: FAIL with "module not found" or "function not defined"

- [ ] **Step 3: Implement csv_io**

Create `src/purl_resolver/csv_io.py`:

```python
from __future__ import annotations

import csv
import io
import json

from .storage.interface import PurlRow, UpsertRow


def detect_delimiter(text: str) -> str:
    first_line = text.split("\n", 1)[0]
    if ";" in first_line:
        return ";"
    return ","


def parse_csv_import(text: str) -> tuple[list[UpsertRow], list[dict]]:
    delimiter = detect_delimiter(text)
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)

    if reader.fieldnames is None or not reader.fieldnames:
        return [], [{"row": 1, "error": "CSV has no header row"}]

    if "purl" not in reader.fieldnames or "repository_url" not in reader.fieldnames:
        return [], [{"row": 1, "error": "CSV must contain 'purl' and 'repository_url' columns"}]

    rows: list[UpsertRow] = []
    errors: list[dict] = []
    row_num = 1

    for row in reader:
        row_num += 1
        purl = (row.get("purl") or "").strip()
        repo = (row.get("repository_url") or "").strip()

        if not purl:
            errors.append({"row": row_num, "error": "empty purl"})
            continue
        if not repo:
            errors.append({"row": row_num, "error": "empty repository_url"})
            continue

        evidence = _parse_jsonb_field(row.get("evidence"))
        warnings = _parse_jsonb_field(row.get("warnings"))

        rows.append(UpsertRow(
            purl=purl,
            repository_url=repo,
            repository_type=row.get("repository_type") or None,
            repository_kind=row.get("repository_kind") or None,
            confidence=row.get("confidence") or None,
            evidence=evidence,
            warnings=warnings,
            version_reference=row.get("version_reference") or None,
            resolver=row.get("resolver") or "purl2repo",
        ))

    return rows, errors


def _parse_jsonb_field(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    except (json.JSONDecodeError, TypeError):
        pass
    return []


def render_csv_export(rows: list[PurlRow]) -> str:
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow([
        "purl", "repository_url", "repository_type", "repository_kind",
        "confidence", "evidence", "warnings", "version_reference",
        "resolver", "resolved_at",
    ])
    for r in rows:
        writer.writerow([
            r.purl,
            r.repository_url,
            r.repository_type or "",
            r.repository_kind or "",
            r.confidence or "",
            json.dumps(r.evidence),
            json.dumps(r.warnings),
            r.version_reference or "",
            r.resolver,
            r.resolved_at,
        ])
    return output.getvalue()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_csv_io.py -v`

Expected: All 12 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/purl_resolver/csv_io.py tests/test_csv_io.py
git commit -m "refactor: add csv_io module with pure CSV parsing/rendering functions"
```

---

### Task 5: Update router to use csv_io

**Files:**
- Modify: `src/purl_resolver/router.py`

- [ ] **Step 1: Replace CSV parsing in import endpoint with csv_io**

In `import_csv_endpoint`, replace the inline CSV parsing (lines ~213-266) with a call to `csv_io.parse_csv_import`. The router should:

1. Decode raw bytes with `utf-8-sig`
2. Call `parse_csv_import(text)` to get `rows: list[UpsertRow]` and `errors`
3. Call `storage.upsert_many(rows)` or handle skip_existing strategy
4. Return `ImportResponse`

The router no longer needs `csv`, `io` imports for parsing — only for response construction.

- [ ] **Step 2: Replace CSV rendering in export endpoint with csv_io**

In `export_csv_endpoint`, replace the inline CSV writing (lines ~326-346) with a call to `csv_io.render_csv_export`. The router should:

1. Build filters and fetch rows from storage
2. Call `render_csv_export(rows)` to get CSV string
3. Encode to bytes and return as Response

- [ ] **Step 3: Run all tests**

Run: `.venv/bin/pytest tests/ --ignore=tests/e2e -q`

Expected: All tests pass (117 + 12 csv_io tests).

- [ ] **Step 4: Commit**

```bash
git add src/purl_resolver/router.py
git commit -m "refactor: router delegates CSV logic to csv_io module"
```

---

### Task 6: Remove PurlRowResponse

**Files:**
- Modify: `src/purl_resolver/schemas.py`
- Modify: `src/purl_resolver/router.py`

- [ ] **Step 1: Update schemas.py**

Remove the `PurlRowResponse` class. Change `PurlListResponse.rows` to use `ResolveResponse`:

```python
class PurlListResponse(BaseModel):
    rows: list[ResolveResponse]
    total: int
    page: int
    page_size: int
```

- [ ] **Step 2: Update router list_purls_endpoint**

Replace `PurlRowResponse` construction with `ResolveResponse`:

```python
row_responses = [
    ResolveResponse(
        purl=r.purl,
        repository_url=r.repository_url,
        repository_type=r.repository_type,
        repository_kind=r.repository_kind,
        confidence=r.confidence,
        evidence=r.evidence,
        warnings=r.warnings,
        version_reference=r.version_reference,
    )
    for r in rows
]
```

Remove `PurlRowResponse` from imports.

- [ ] **Step 3: Run all tests**

Run: `.venv/bin/pytest tests/ --ignore=tests/e2e -q`

Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add src/purl_resolver/schemas.py src/purl_resolver/router.py
git commit -m "refactor: remove PurlRowResponse, use ResolveResponse at API boundary"
```

---

### Task 7: Run full test suite and verify

**Files:** None (verification only)

- [ ] **Step 1: Run full test suite**

Run: `.venv/bin/pytest tests/ --ignore=tests/e2e -v`

Expected: All tests pass. Count should be ~129 (117 original + 12 csv_io tests).

- [ ] **Step 2: Verify no regressions in existing behavior**

Run: `.venv/bin/pytest tests/test_api.py tests/test_storage.py tests/test_sbom_integration.py -v`

Expected: All existing tests pass unchanged.

- [ ] **Step 3: Final commit if any fixups needed**

```bash
git add -A
git commit -m "fix: address test failures from architecture refactoring"
```

---

### Task 8: Update specs and docs

**Files:**
- Modify: `specs/architecture/layers.md`
- Modify: `specs/INDEX.md`
- Modify: `docs/superpowers/specs/2026-05-31-arch-refactoring-design.md` (mark as implemented)

- [ ] **Step 1: Update architecture spec**

In `specs/architecture/layers.md`, add `csv_io.py` to the file listing and update the Storage Layer section to mention UpsertRow.

- [ ] **Step 2: Update INDEX.md**

Add a task mapping entry: "Refactor CSV import/export or storage interface" → `architecture/layers.md`

- [ ] **Step 3: Commit**

```bash
git add specs/
git commit -m "docs: update specs for architecture refactoring"
```
