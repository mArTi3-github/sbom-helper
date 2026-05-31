# Test Suite Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve test quality and coverage by fixing async markers, removing duplicates, adding missing Postgres e2e tests, and adding direct unit tests for untested functions.

**Architecture:** Five independent tasks touching test files only (no source changes). Each task is self-contained and can be committed independently.

**Tech Stack:** pytest, pytest-asyncio, testcontainers[postgres], asyncpg

---

## Task 1: Fix async test markers in test_db_admin.py

**Files:**
- Modify: `tests/test_db_admin.py`

Async test classes `TestInMemoryCacheList`, `TestInMemoryCacheCount`, `TestInMemoryCacheUpdate` define `async def test_*` methods without `@pytest.mark.asyncio`. They work in auto mode but are fragile. Add explicit markers.

- [ ] **Step 1: Add asyncio marker import**

In `tests/test_db_admin.py`, add `import pytest` is already present. No import change needed — just add markers.

- [ ] **Step 2: Add @pytest.mark.asyncio to async test classes**

Add the marker to each async test method in the three classes. Example for `TestInMemoryCacheList`:

```python
class TestInMemoryCacheList:
    @pytest.mark.asyncio
    async def test_list_all_returns_all(self, populated_storage):
        rows = await populated_storage.list_purls(0, 50, PurlFilters())
        assert len(rows) == 3
        purls = {r.purl for r in rows}
        assert purls == {"pkg:pypi/requests", "pkg:npm/express", "pkg:pypi/flask"}

    @pytest.mark.asyncio
    async def test_list_with_limit(self, populated_storage):
        rows = await populated_storage.list_purls(0, 2, PurlFilters())
        assert len(rows) == 2

    @pytest.mark.asyncio
    async def test_list_with_offset(self, populated_storage):
        rows = await populated_storage.list_purls(2, 10, PurlFilters())
        assert len(rows) == 1

    @pytest.mark.asyncio
    async def test_list_with_search(self, populated_storage):
        rows = await populated_storage.list_purls(0, 50, PurlFilters(search="flask"))
        assert len(rows) == 1
        assert rows[0].purl == "pkg:pypi/flask"

    @pytest.mark.asyncio
    async def test_list_with_resolver_filter(self, populated_storage):
        rows = await populated_storage.list_purls(0, 50, PurlFilters(resolver="purl2repo"))
        assert len(rows) == 3

    @pytest.mark.asyncio
    async def test_list_with_confidence_filter(self, populated_storage):
        rows = await populated_storage.list_purls(0, 50, PurlFilters(confidence="high"))
        assert len(rows) == 2

    @pytest.mark.asyncio
    async def test_list_with_confidence_filter_no_match(self, populated_storage):
        rows = await populated_storage.list_purls(0, 50, PurlFilters(confidence="medium"))
        assert len(rows) == 0

    @pytest.mark.asyncio
    async def test_list_sort_by_purl_asc(self, populated_storage):
        rows = await populated_storage.list_purls(0, 50, PurlFilters(), sort_by="purl", sort_order="asc")
        purls = [r.purl for r in rows]
        assert purls == ["pkg:npm/express", "pkg:pypi/flask", "pkg:pypi/requests"]

    @pytest.mark.asyncio
    async def test_list_sort_by_confidence_desc(self, populated_storage):
        rows = await populated_storage.list_purls(0, 50, PurlFilters(), sort_by="confidence", sort_order="desc")
        assert rows[0].confidence == "low"
```

Same pattern for `TestInMemoryCacheCount` (2 methods) and `TestInMemoryCacheUpdate` (3 methods).

- [ ] **Step 3: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_db_admin.py -v --tb=short`
Expected: All 50 tests pass

- [ ] **Step 4: Commit**

```bash
git add tests/test_db_admin.py
git commit -m "test: add explicit @pytest.mark.asyncio to async storage tests"
```

---

## Task 2: Fix async test markers in test_storage.py

**Files:**
- Modify: `tests/test_storage.py`

Same issue as Task 1 — `TestInMemoryCache` async methods lack markers.

- [ ] **Step 1: Add @pytest.mark.asyncio to async test methods**

```python
class TestInMemoryCache:

    @pytest.mark.asyncio
    async def test_lookup_returns_none_for_missing(self, storage: InMemoryCache) -> None:
        result = await storage.lookup("pkg:pypi/unknown@1.0")
        assert result is None

    @pytest.mark.asyncio
    async def test_store_and_lookup(self, storage: InMemoryCache) -> None:
        response = ResolveResponse(
            purl="pkg:pypi/requests",
            repository_url="https://github.com/psf/requests",
            repository_type="github",
            repository_kind="source_code",
            confidence="high",
        )
        await storage.store(response)
        cached = await storage.lookup("pkg:pypi/requests")
        assert cached is not None
        assert cached.repository_url == "https://github.com/psf/requests"

    @pytest.mark.asyncio
    async def test_store_overwrites_existing(self, storage: InMemoryCache) -> None:
        response_old = ResolveResponse(
            purl="pkg:pypi/example",
            repository_url="https://github.com/old/example",
        )
        response_new = ResolveResponse(
            purl="pkg:pypi/example",
            repository_url="https://github.com/new/example",
        )
        await storage.store(response_old)
        await storage.store(response_new)
        cached = await storage.lookup("pkg:pypi/example")
        assert cached is not None
        assert cached.repository_url == "https://github.com/new/example"

    @pytest.mark.asyncio
    async def test_clear_removes_all(self, storage: InMemoryCache) -> None:
        response = ResolveResponse(
            purl="pkg:pypi/requests",
            repository_url="https://github.com/psf/requests",
        )
        await storage.store(response)
        storage.clear()
        assert await storage.lookup("pkg:pypi/requests") is None
```

Same for all `TestResolvePurl` async methods (9 methods) — add `@pytest.mark.asyncio` to each.

- [ ] **Step 2: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_storage.py -v --tb=short`
Expected: All 14 tests pass

- [ ] **Step 3: Commit**

```bash
git add tests/test_storage.py
git commit -m "test: add explicit @pytest.mark.asyncio to async service tests"
```

---

## Task 3: Remove duplicate InMemoryCache tests from test_db_admin.py

**Files:**
- Modify: `tests/test_db_admin.py`

Classes `TestInMemoryCacheList`, `TestInMemoryCacheCount`, `TestInMemoryCacheUpdate` test InMemoryCache directly. These are redundant because:
- The same operations are tested through `TestAdminListPurls`, `TestAdminUpdatePurl`, etc. via the HTTP API
- `test_storage.py` already covers basic InMemoryCache store/lookup/clear

Remove these three classes entirely (14 test methods).

- [ ] **Step 1: Delete the three duplicate classes**

Remove from `tests/test_db_admin.py`:
- `class TestInMemoryCacheList` (9 methods)
- `class TestInMemoryCacheCount` (2 methods)
- `class TestInMemoryCacheUpdate` (3 methods)

- [ ] **Step 2: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_db_admin.py -v --tb=short`
Expected: All remaining tests pass (36 tests, down from 50)

- [ ] **Step 3: Commit**

```bash
git add tests/test_db_admin.py
git commit -m "test: remove duplicate InMemoryCache tests covered by API tests"
```

---

## Task 4: Add Postgres e2e tests for list/count/update/delete/upsert

**Files:**
- Modify: `tests/e2e/test_postgres.py`

Current e2e tests only cover `store()` and `lookup()`. Add coverage for the remaining 5 Storage interface methods.

- [ ] **Step 1: Add test helper for populating test data**

Add a fixture and helper at the top of the test file:

```python
async def _seed_data(cache: PostgresCache) -> None:
    entries = [
        ResolveResponse(
            purl="pkg:pypi/requests",
            repository_url="https://github.com/psf/requests",
            repository_type="github",
            repository_kind="source_code",
            confidence="high",
            evidence=["homepage from PyPI"],
            warnings=[],
        ),
        ResolveResponse(
            purl="pkg:npm/express",
            repository_url="https://github.com/expressjs/express",
            repository_type="github",
            repository_kind="source_code",
            confidence="low",
            evidence=[],
            warnings=["registry mismatch"],
        ),
        ResolveResponse(
            purl="pkg:pypi/flask",
            repository_url="https://github.com/pallets/flask",
            repository_type="github",
            repository_kind="source_code",
            confidence="high",
            evidence=["homepage from PyPI"],
            warnings=[],
        ),
    ]
    for e in entries:
        await cache.store(e)
```

- [ ] **Step 2: Add TestE2EPostgresListPurls class**

```python
class TestE2EPostgresListPurls:

    async def test_list_all(self, cache: PostgresCache) -> None:
        await _seed_data(cache)
        rows = await cache.list_purls(0, 50, PurlFilters())
        assert len(rows) == 3
        purls = {r.purl for r in rows}
        assert purls == {"pkg:pypi/requests", "pkg:npm/express", "pkg:pypi/flask"}

    async def test_list_with_limit(self, cache: PostgresCache) -> None:
        await _seed_data(cache)
        rows = await cache.list_purls(0, 2, PurlFilters())
        assert len(rows) == 2

    async def test_list_with_offset(self, cache: PostgresCache) -> None:
        await _seed_data(cache)
        rows = await cache.list_purls(2, 10, PurlFilters())
        assert len(rows) == 1

    async def test_list_with_search(self, cache: PostgresCache) -> None:
        await _seed_data(cache)
        rows = await cache.list_purls(0, 50, PurlFilters(search="flask"))
        assert len(rows) == 1
        assert rows[0].purl == "pkg:pypi/flask"

    async def test_list_with_confidence_filter(self, cache: PostgresCache) -> None:
        await _seed_data(cache)
        rows = await cache.list_purls(0, 50, PurlFilters(confidence="high"))
        assert len(rows) == 2

    async def test_list_sort_by_purl_asc(self, cache: PostgresCache) -> None:
        await _seed_data(cache)
        rows = await cache.list_purls(0, 50, PurlFilters(), sort_by="purl", sort_order="asc")
        purls = [r.purl for r in rows]
        assert purls == ["pkg:npm/express", "pkg:pypi/flask", "pkg:pypi/requests"]
```

- [ ] **Step 3: Add TestE2EPostgresCountPurls class**

```python
class TestE2EPostgresCountPurls:

    async def test_count_all(self, cache: PostgresCache) -> None:
        await _seed_data(cache)
        count = await cache.count_purls(PurlFilters())
        assert count == 3

    async def test_count_with_search(self, cache: PostgresCache) -> None:
        await _seed_data(cache)
        count = await cache.count_purls(PurlFilters(search="pypi"))
        assert count == 2

    async def test_count_with_confidence_filter(self, cache: PostgresCache) -> None:
        await _seed_data(cache)
        count = await cache.count_purls(PurlFilters(confidence="low"))
        assert count == 1
```

- [ ] **Step 4: Add TestE2EPostgresUpdatePurl class**

```python
class TestE2EPostgresUpdatePurl:

    async def test_update_repository_url(self, cache: PostgresCache) -> None:
        await _seed_data(cache)
        ok = await cache.update_purl(
            "pkg:pypi/requests", "pkg:pypi/requests", "https://github.com/psf/requests-v3"
        )
        assert ok is True
        row = await cache.lookup("pkg:pypi/requests")
        assert row is not None
        assert row.repository_url == "https://github.com/psf/requests-v3"

    async def test_update_rekey_purl(self, cache: PostgresCache) -> None:
        await _seed_data(cache)
        ok = await cache.update_purl(
            "pkg:pypi/requests", "pkg:pypi/requests3", "https://github.com/psf/requests3"
        )
        assert ok is True
        old = await cache.lookup("pkg:pypi/requests")
        assert old is None
        new = await cache.lookup("pkg:pypi/requests3")
        assert new is not None
        assert new.repository_url == "https://github.com/psf/requests3"

    async def test_update_not_found(self, cache: PostgresCache) -> None:
        ok = await cache.update_purl(
            "pkg:pypi/nonexistent", "pkg:pypi/nonexistent", "https://example.com"
        )
        assert ok is False
```

- [ ] **Step 5: Add TestE2EPostgresDeletePurls class**

```python
class TestE2EPostgresDeletePurls:

    async def test_delete_single(self, cache: PostgresCache) -> None:
        await _seed_data(cache)
        deleted = await cache.delete_purls(["pkg:pypi/requests"])
        assert deleted == 1
        assert await cache.lookup("pkg:pypi/requests") is None

    async def test_delete_multiple(self, cache: PostgresCache) -> None:
        await _seed_data(cache)
        deleted = await cache.delete_purls(["pkg:pypi/requests", "pkg:npm/express"])
        assert deleted == 2
        assert await cache.lookup("pkg:pypi/requests") is None
        assert await cache.lookup("pkg:npm/express") is None

    async def test_delete_nonexistent(self, cache: PostgresCache) -> None:
        deleted = await cache.delete_purls(["pkg:pypi/nonexistent"])
        assert deleted == 0

    async def test_delete_empty_list(self, cache: PostgresCache) -> None:
        deleted = await cache.delete_purls([])
        assert deleted == 0
```

- [ ] **Step 6: Add TestE2EPostgresUpsertMany class**

```python
class TestE2EPostgresUpsertMany:

    async def test_upsert_new_rows(self, cache: PostgresCache) -> None:
        from purl_resolver.storage.interface import UpsertRow
        rows = [
            UpsertRow(
                purl="pkg:pypi/newpkg",
                repository_url="https://github.com/new/pkg",
                confidence="high",
            ),
        ]
        upserted, errors = await cache.upsert_many(rows)
        assert upserted == 1
        assert errors == 0
        cached = await cache.lookup("pkg:pypi/newpkg")
        assert cached is not None
        assert cached.repository_url == "https://github.com/new/pkg"

    async def test_upsert_overwrites_existing(self, cache: PostgresCache) -> None:
        from purl_resolver.storage.interface import UpsertRow
        await _seed_data(cache)
        rows = [
            UpsertRow(
                purl="pkg:pypi/requests",
                repository_url="https://github.com/psf/requests-v4",
            ),
        ]
        upserted, errors = await cache.upsert_many(rows)
        assert upserted == 1
        assert errors == 0
        cached = await cache.lookup("pkg:pypi/requests")
        assert cached is not None
        assert cached.repository_url == "https://github.com/psf/requests-v4"

    async def test_upsert_empty_list(self, cache: PostgresCache) -> None:
        from purl_resolver.storage.interface import UpsertRow
        upserted, errors = await cache.upsert_many([])
        assert upserted == 0
        assert errors == 0
```

- [ ] **Step 7: Run e2e tests to verify they pass**

Run: `.venv/bin/pytest tests/e2e/test_postgres.py -v --tb=short`
Expected: All 22 tests pass (was 5)

- [ ] **Step 8: Commit**

```bash
git add tests/e2e/test_postgres.py
git commit -m "test: add Postgres e2e tests for list/count/update/delete/upsert"
```

---

## Task 5: Add direct unit test for resolve_batch()

**Files:**
- Create: `tests/test_resolve_batch.py`

`resolve_batch()` in `service.py` is only tested indirectly through SBOM integration. Add a focused unit test.

- [ ] **Step 1: Create test file with resolve_batch tests**

```python
from __future__ import annotations

import pytest

from purl_resolver.resolver.interface import Resolution
from purl_resolver.service import resolve_batch
from purl_resolver.storage.inmemory import InMemoryCache

from tests.helpers import FakeResolver


@pytest.fixture
def storage() -> InMemoryCache:
    return InMemoryCache()


class TestResolveBatch:

    @pytest.mark.asyncio
    async def test_resolves_multiple_purls(self, storage: InMemoryCache) -> None:
        resolver = FakeResolver(
            resolution=Resolution(
                purl="pkg:pypi/requests@2.31.0",
                repository_url="https://github.com/psf/requests",
                repository_type="github",
                repository_kind="source_code",
                confidence="high",
            )
        )
        purls = [
            "pkg:pypi/requests@2.31.0",
            "pkg:npm/express@4.17.1",
            "pkg:pypi/flask@3.0.0",
        ]
        result = await resolve_batch(purls, storage, [resolver])
        assert len(result) == 3
        for key, url in result.items():
            assert url == "https://github.com/psf/requests"

    @pytest.mark.asyncio
    async def test_skips_purls_with_no_repository_url(self, storage: InMemoryCache) -> None:
        resolver = FakeResolver(
            resolution=Resolution(
                purl="pkg:pypi/requests@2.31.0",
                repository_url=None,
            )
        )
        purls = ["pkg:pypi/requests@2.31.0"]
        result = await resolve_batch(purls, storage, [resolver])
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_uses_normalized_keys(self, storage: InMemoryCache) -> None:
        resolver = FakeResolver(
            resolution=Resolution(
                purl="pkg:pypi/requests@2.31.0",
                repository_url="https://github.com/psf/requests",
            )
        )
        purls = ["pkg:pypi/requests@2.31.0", "pkg:pypi/requests@3.0.0"]
        result = await resolve_batch(purls, storage, [resolver])
        assert len(result) == 1
        assert "pkg:pypi/requests" in result

    @pytest.mark.asyncio
    async def test_empty_purl_list(self, storage: InMemoryCache) -> None:
        resolver = FakeResolver()
        result = await resolve_batch([], storage, [resolver])
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_stores_resolved_results_in_storage(self, storage: InMemoryCache) -> None:
        resolver = FakeResolver(
            resolution=Resolution(
                purl="pkg:pypi/requests@2.31.0",
                repository_url="https://github.com/psf/requests",
                confidence="high",
            )
        )
        purls = ["pkg:pypi/requests@2.31.0"]
        await resolve_batch(purls, storage, [resolver])
        cached = await storage.lookup("pkg:pypi/requests")
        assert cached is not None
        assert cached.repository_url == "https://github.com/psf/requests"
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_resolve_batch.py -v --tb=short`
Expected: All 5 tests pass

- [ ] **Step 3: Commit**

```bash
git add tests/test_resolve_batch.py
git commit -m "test: add direct unit tests for resolve_batch()"
```

---

## Task 6: Add direct unit tests for csv_io.py

**Files:**
- Create: `tests/test_csv_io.py`

`csv_io.py` functions (`detect_delimiter`, `parse_csv_import`, `render_csv_export`) are only tested indirectly through the API. Add direct unit tests.

- [ ] **Step 1: Create test file**

```python
from __future__ import annotations

import json

from purl_resolver.csv_io import detect_delimiter, parse_csv_import, render_csv_export
from purl_resolver.storage.interface import PurlRow


class TestDetectDelimiter:

    def test_semicolon_delimiter(self) -> None:
        assert detect_delimiter("purl;repository_url") == ";"

    def test_comma_delimiter(self) -> None:
        assert detect_delimiter("purl,repository_url") == ","

    def test_prefers_semicolon_over_comma(self) -> None:
        assert detect_delimiter("purl,repo;extra") == ";"

    def test_defaults_to_comma(self) -> None:
        assert detect_delimiter("purl repository_url") == ","


class TestParseCsvImport:

    def test_valid_csv_semicolon(self) -> None:
        csv_text = "purl;repository_url\npkg:pypi/requests;https://github.com/psf/requests\n"
        rows, errors = parse_csv_import(csv_text)
        assert len(rows) == 1
        assert len(errors) == 0
        assert rows[0].purl == "pkg:pypi/requests"
        assert rows[0].repository_url == "https://github.com/psf/requests"

    def test_valid_csv_comma(self) -> None:
        csv_text = "purl,repository_url\npkg:pypi/requests,https://github.com/psf/requests\n"
        rows, errors = parse_csv_import(csv_text)
        assert len(rows) == 1
        assert rows[0].purl == "pkg:pypi/requests"

    def test_missing_columns_returns_error(self) -> None:
        csv_text = "purl\npkg:pypi/requests\n"
        rows, errors = parse_csv_import(csv_text)
        assert len(rows) == 0
        assert len(errors) == 1
        assert "repository_url" in errors[0]["error"]

    def test_empty_purl_returns_error(self) -> None:
        csv_text = "purl;repository_url\n;https://example.com\n"
        rows, errors = parse_csv_import(csv_text)
        assert len(rows) == 0
        assert len(errors) == 1
        assert errors[0]["error"] == "empty purl"

    def test_empty_repository_url_returns_error(self) -> None:
        csv_text = "purl;repository_url\npkg:pypi/test;\n"
        rows, errors = parse_csv_import(csv_text)
        assert len(rows) == 0
        assert len(errors) == 1
        assert errors[0]["error"] == "empty repository_url"

    def test_optional_columns_parsed(self) -> None:
        csv_text = (
            "purl;repository_url;confidence;resolver\n"
            "pkg:pypi/test;https://example.com;high;custom\n"
        )
        rows, errors = parse_csv_import(csv_text)
        assert len(rows) == 1
        assert rows[0].confidence == "high"
        assert rows[0].resolver == "custom"

    def test_jsonb_evidence_parsed(self) -> None:
        csv_text = (
            'purl;repository_url;evidence;warnings\n'
            'pkg:pypi/test;https://example.com;["a","b"];["w1"]\n'
        )
        rows, errors = parse_csv_import(csv_text)
        assert len(rows) == 1
        assert rows[0].evidence == ["a", "b"]
        assert rows[0].warnings == ["w1"]

    def test_bom_prefix_handled(self) -> None:
        csv_text = "\ufeffpurl;repository_url\npkg:pypi/test;https://example.com\n"
        rows, errors = parse_csv_import(csv_text)
        assert len(rows) == 1
        assert rows[0].purl == "pkg:pypi/test"

    def test_no_header_returns_error(self) -> None:
        rows, errors = parse_csv_import("")
        assert len(rows) == 0
        assert len(errors) == 1

    def test_multiple_rows(self) -> None:
        csv_text = (
            "purl;repository_url\n"
            "pkg:pypi/a;https://example.com/a\n"
            "pkg:npm/b;https://example.com/b\n"
            "pkg:pypi/c;https://example.com/c\n"
        )
        rows, errors = parse_csv_import(csv_text)
        assert len(rows) == 3
        assert len(errors) == 0


class TestRenderCsvExport:

    def test_renders_header_and_rows(self) -> None:
        rows = [
            PurlRow(
                purl="pkg:pypi/requests",
                repository_url="https://github.com/psf/requests",
                repository_type="github",
                repository_kind="source_code",
                confidence="high",
                evidence=["homepage"],
                warnings=[],
                version_reference=None,
                resolver="purl2repo",
                resolved_at="2024-01-01",
            ),
        ]
        csv_text = render_csv_export(rows)
        lines = csv_text.strip().split("\n")
        assert len(lines) == 2
        assert "purl" in lines[0]
        assert ";" in lines[0]

    def test_uses_semicolon_delimiter(self) -> None:
        rows = [
            PurlRow(
                purl="pkg:pypi/test",
                repository_url="https://example.com",
            ),
        ]
        csv_text = render_csv_export(rows)
        first_line = csv_text.split("\n")[0]
        assert ";" in first_line
        assert "," not in first_line.split(";")[0]

    def test_jsonb_fields_rendered(self) -> None:
        rows = [
            PurlRow(
                purl="pkg:pypi/test",
                repository_url="https://example.com",
                evidence=["a", "b"],
                warnings=["w1"],
            ),
        ]
        csv_text = render_csv_export(rows)
        data_line = csv_text.strip().split("\n")[1]
        assert '"a"' in data_line
        assert '"w1"' in data_line

    def test_empty_rows(self) -> None:
        csv_text = render_csv_export([])
        lines = csv_text.strip().split("\n")
        assert len(lines) == 1  # header only
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_csv_io.py -v --tb=short`
Expected: All tests pass

- [ ] **Step 3: Commit**

```bash
git add tests/test_csv_io.py
git commit -m "test: add direct unit tests for csv_io.py"
```

---

## Final Verification

- [ ] **Step 1: Run full test suite**

Run: `.venv/bin/pytest tests/ -v --tb=short`
Expected: All tests pass

- [ ] **Step 2: Verify test count changed**

Before: 122 tests. After: approximately 122 - 14 (removed duplicates) + 17 (new Postgres e2e) + 5 (resolve_batch) + 17 (csv_io) = ~147 tests

Run: `.venv/bin/pytest tests/ --co -q | tail -1`
Expected: ~147 tests collected
