# Phase 2 Refactoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor sbom-helper to reduce boilerplate, improve readability, and prepare for future feature growth.

**Architecture:** Three independent refactoring changes applied in sequence: (1) add conversion methods to PurlRow data model, (2) extract URL validation from resolve_purl into a private function, (3) split router.py into domain-specific sub-routers under a routes/ package.

**Tech Stack:** Python 3.12+, FastAPI, asyncpg, pytest, pytest-asyncio

---

## File Structure

```
src/purl_resolver/
├── storage/
│   ├── interface.py          — MODIFY: add from_response() and to_resolve_response() to PurlRow
│   └── postgres.py           — MODIFY: use to_resolve_response() in lookup()
├── service.py                — MODIFY: extract _validate_cached_url(), simplify resolve_purl()
├── routes/                   — CREATE: new package
│   ├── __init__.py           — CREATE: empty
│   ├── resolve.py            — CREATE: POST /api/v1/resolve, POST /api/v1/resolve/sbom
│   ├── db_admin.py           — CREATE: all /api/v1/db/* endpoints
│   └── settings.py           — CREATE: GET/PATCH /api/v1/settings, _rebuild_resolvers()
├── router.py                 — MODIFY: keep pages + health, mount sub-routers
└── main.py                   — NO CHANGES (already uses root router)

tests/
├── test_service_validation.py — MODIFY: add unit tests for _validate_cached_url()
├── test_api.py               — NO CHANGES (imports root router)
├── test_db_admin.py          — NO CHANGES (imports root router)
└── test_sbom_integration.py  — NO CHANGES (imports root router)
```

---

## Task 1: P5 — Add conversion methods to PurlRow

**Files:**
- Modify: `src/purl_resolver/storage/interface.py`
- Modify: `src/purl_resolver/router.py:161-174`
- Modify: `src/purl_resolver/storage/postgres.py:42-59`

- [ ] **Step 1: Add `from_response()` classmethod to PurlRow**

In `src/purl_resolver/storage/interface.py`, add after the `PurlRow` dataclass fields (after line 30):

```python
    @classmethod
    def from_response(cls, r: ResolveResponse) -> PurlRow:
        return cls(
            purl=r.purl,
            repository_url=r.repository_url,
            repository_type=r.repository_type,
            repository_kind=r.repository_kind,
            confidence=r.confidence,
            evidence=r.evidence,
            warnings=r.warnings,
            version_reference=r.version_reference,
            resolver=r.resolver,
            resolved_at=r.resolved_at or "",
        )
```

- [ ] **Step 2: Add `to_resolve_response()` method to PurlRow**

In `src/purl_resolver/storage/interface.py`, add after `from_response()`:

```python
    def to_resolve_response(self) -> ResolveResponse:
        return ResolveResponse(
            purl=self.purl,
            repository_url=self.repository_url,
            repository_type=self.repository_type,
            repository_kind=self.repository_kind,
            confidence=self.confidence,
            evidence=self.evidence,
            warnings=self.warnings,
            version_reference=self.version_reference,
            resolver=self.resolver,
            resolved_at=self.resolved_at,
        )
```

- [ ] **Step 3: Run existing tests to verify no regressions**

Run: `.venv/bin/pytest tests/ -v`
Expected: All existing tests PASS (methods are purely additive)

- [ ] **Step 4: Refactor `list_purls_endpoint` in router.py**

In `src/purl_resolver/router.py`, replace lines 161-174:

```python
    # BEFORE (lines 161-174):
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
            resolver=r.resolver,
            resolved_at=r.resolved_at,
        )
        for r in rows
    ]

    # AFTER:
    row_responses = [r.to_resolve_response() for r in rows]
```

- [ ] **Step 5: Refactor `lookup()` in postgres.py**

In `src/purl_resolver/storage/postgres.py`, replace lines 42-59:

```python
    # BEFORE (lines 42-59):
    async def lookup(self, purl: str) -> ResolveResponse | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM resolved_purls WHERE purl = $1", purl
            )
        if row is None:
            return None
        return ResolveResponse(
            purl=row["purl"],
            repository_url=row["repository_url"],
            repository_type=row.get("repository_type"),
            repository_kind=row.get("repository_kind"),
            confidence=row.get("confidence"),
            evidence=self._decode_jsonb(row.get("evidence")),
            warnings=self._decode_jsonb(row.get("warnings")),
            version_reference=row.get("version_reference"),
            resolver=row.get("resolver", ""),
        )

    # AFTER:
    async def lookup(self, purl: str) -> ResolveResponse | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM resolved_purls WHERE purl = $1", purl
            )
        if row is None:
            return None
        return PurlRow(
            purl=row["purl"],
            repository_url=row["repository_url"],
            repository_type=row.get("repository_type"),
            repository_kind=row.get("repository_kind"),
            confidence=row.get("confidence"),
            evidence=self._decode_jsonb(row.get("evidence")),
            warnings=self._decode_jsonb(row.get("warnings")),
            version_reference=row.get("version_reference"),
            resolver=row.get("resolver", ""),
            resolved_at=str(row.get("resolved_at", "")),
        ).to_resolve_response()
```

- [ ] **Step 6: Run tests to verify refactoring**

Run: `.venv/bin/pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 7: Commit P5 changes**

```bash
git add src/purl_resolver/storage/interface.py src/purl_resolver/router.py src/purl_resolver/storage/postgres.py
git commit -m "refactor: add conversion methods to PurlRow, reduce mapping boilerplate"
```

---

## Task 2: P1 — Extract URL validation from resolve_purl

**Files:**
- Modify: `src/purl_resolver/service.py`
- Modify: `tests/test_service_validation.py`

- [ ] **Step 1: Write failing test for `_validate_cached_url` — settings_store is None**

In `tests/test_service_validation.py`, add:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from purl_resolver.schemas import ResolveResponse
from purl_resolver.service import _validate_cached_url


@pytest.mark.asyncio
async def test_validate_cached_url_returns_cached_when_no_settings_store():
    cached = ResolveResponse(
        purl="pkg:pypi/requests",
        repository_url="https://github.com/psf/requests",
    )
    result = await _validate_cached_url(cached, None, "pkg:pypi/requests", AsyncMock())
    assert result == cached
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_service_validation.py::test_validate_cached_url_returns_cached_when_no_settings_store -v`
Expected: FAIL with `ImportError: cannot import name '_validate_cached_url'`

- [ ] **Step 3: Write failing test — validate_db_urls is False**

In `tests/test_service_validation.py`, add:

```python
@pytest.mark.asyncio
async def test_validate_cached_url_returns_cached_when_validation_disabled():
    cached = ResolveResponse(
        purl="pkg:pypi/requests",
        repository_url="https://github.com/psf/requests",
    )
    settings_store = MagicMock()
    settings_store.load.return_value = MagicMock(validate_db_urls=False)
    result = await _validate_cached_url(cached, settings_store, "pkg:pypi/requests", AsyncMock())
    assert result == cached
```

- [ ] **Step 4: Write failing test — date matches today**

In `tests/test_service_validation.py`, add:

```python
from datetime import datetime


@pytest.mark.asyncio
async def test_validate_cached_url_returns_cached_when_resolved_today():
    cached = ResolveResponse(
        purl="pkg:pypi/requests",
        repository_url="https://github.com/psf/requests",
        resolved_at=datetime.now().isoformat(),
    )
    settings_store = MagicMock()
    settings_store.load.return_value = MagicMock(validate_db_urls=True)
    result = await _validate_cached_url(cached, settings_store, "pkg:pypi/requests", AsyncMock())
    assert result == cached
```

- [ ] **Step 5: Write failing test — VALID URL**

In `tests/test_service_validation.py`, add:

```python
from purl_resolver.url_validator import UrlValidationResult


@pytest.mark.asyncio
async def test_validate_cached_url_updates_resolved_at_on_valid_url():
    cached = ResolveResponse(
        purl="pkg:pypi/requests",
        repository_url="https://github.com/psf/requests",
        resolved_at="2020-01-01T00:00:00",
    )
    settings_store = MagicMock()
    settings_store.load.return_value = MagicMock(
        validate_db_urls=True,
        github_token=None,
        url_validation_timeout=5,
    )
    storage = AsyncMock()
    with pytest.patch("purl_resolver.service.validate_url", return_value=UrlValidationResult.VALID):
        result = await _validate_cached_url(cached, settings_store, "pkg:pypi/requests", storage)
    assert result == cached
    storage.store.assert_called_once_with(cached)
```

- [ ] **Step 6: Write failing test — INVALID URL**

In `tests/test_service_validation.py`, add:

```python
@pytest.mark.asyncio
async def test_validate_cached_url_deletes_cache_on_invalid_url():
    cached = ResolveResponse(
        purl="pkg:pypi/requests",
        repository_url="https://github.com/psf/requests",
        resolved_at="2020-01-01T00:00:00",
    )
    settings_store = MagicMock()
    settings_store.load.return_value = MagicMock(
        validate_db_urls=True,
        github_token=None,
        url_validation_timeout=5,
    )
    storage = AsyncMock()
    with pytest.patch("purl_resolver.service.validate_url", return_value=UrlValidationResult.INVALID):
        result = await _validate_cached_url(cached, settings_store, "pkg:pypi/requests", storage)
    assert result is None
    storage.delete_purls.assert_called_once_with(["pkg:pypi/requests"])
```

- [ ] **Step 7: Write failing test — TOKEN_INVALID**

In `tests/test_service_validation.py`, add:

```python
@pytest.mark.asyncio
async def test_validate_cached_url_removes_token_on_token_invalid():
    cached = ResolveResponse(
        purl="pkg:pypi/requests",
        repository_url="https://github.com/psf/requests",
        resolved_at="2020-01-01T00:00:00",
    )
    settings_store = MagicMock()
    app_settings = MagicMock(
        validate_db_urls=True,
        github_token="ghp_invalid",
        url_validation_timeout=5,
    )
    settings_store.load.return_value = app_settings
    storage = AsyncMock()
    with pytest.patch("purl_resolver.service.validate_url") as mock_validate:
        mock_validate.side_effect = [UrlValidationResult.TOKEN_INVALID, UrlValidationResult.VALID]
        result = await _validate_cached_url(cached, settings_store, "pkg:pypi/requests", storage)
    assert result == cached
    settings_store.save.assert_called_once()
```

- [ ] **Step 8: Write failing test — NETWORK_ERROR**

In `tests/test_service_validation.py`, add:

```python
@pytest.mark.asyncio
async def test_validate_cached_url_returns_cached_on_network_error():
    cached = ResolveResponse(
        purl="pkg:pypi/requests",
        repository_url="https://github.com/psf/requests",
        resolved_at="2020-01-01T00:00:00",
    )
    settings_store = MagicMock()
    settings_store.load.return_value = MagicMock(
        validate_db_urls=True,
        github_token=None,
        url_validation_timeout=5,
    )
    storage = AsyncMock()
    with pytest.patch("purl_resolver.service.validate_url", return_value=UrlValidationResult.NETWORK_ERROR):
        result = await _validate_cached_url(cached, settings_store, "pkg:pypi/requests", storage)
    assert result == cached
```

- [ ] **Step 9: Run all new tests to verify they fail**

Run: `.venv/bin/pytest tests/test_service_validation.py -v`
Expected: All 7 new tests FAIL with `ImportError`

- [ ] **Step 10: Extract `_validate_cached_url` from `resolve_purl`**

In `src/purl_resolver/service.py`, add the new function before `resolve_purl`:

```python
async def _validate_cached_url(
    cached: ResolveResponse,
    settings_store: SettingsStore | None,
    purl_key: str,
    storage: Storage,
) -> ResolveResponse | None:
    if settings_store is None:
        return cached

    app_settings = settings_store.load()
    if not app_settings.validate_db_urls:
        return cached

    resolved_date = None
    if cached.resolved_at:
        try:
            resolved_date = datetime.fromisoformat(cached.resolved_at).date()
        except (ValueError, TypeError):
            pass

    if resolved_date == datetime.now().date():
        return cached

    github_token = app_settings.github_token
    vresult = await validate_url(
        cached.repository_url,
        app_settings.url_validation_timeout,
        github_token=github_token,
    )

    if vresult == UrlValidationResult.TOKEN_INVALID:
        logger.warning("GitHub token invalid, removing from settings")
        try:
            settings_store.save(app_settings.model_copy(update={"github_token": None}))
        except Exception:
            logger.warning("Failed to persist token removal to settings", exc_info=True)
        vresult = await validate_url(
            cached.repository_url,
            app_settings.url_validation_timeout,
            github_token=None,
        )

    if vresult == UrlValidationResult.VALID:
        try:
            await storage.store(cached)
        except Exception:
            logger.warning("Failed to update resolved_at for %s", purl_key, exc_info=True)
    elif vresult == UrlValidationResult.INVALID:
        try:
            await storage.delete_purls([purl_key])
        except Exception:
            logger.warning("Failed to delete invalid URL for %s", purl_key, exc_info=True)
        return None

    return cached
```

- [ ] **Step 11: Refactor `resolve_purl` to use the extracted function**

In `src/purl_resolver/service.py`, replace lines 36-88 in `resolve_purl`:

```python
    # BEFORE (lines 36-88):
    try:
        cached = await storage.lookup(purl_key)
        if cached is not None:
            logger.info("Cache hit for %s", purl_key)
            # ... 45 lines of URL validation ...
            if cached is not None:
                return ResolveResult.ok(cached)
    except Exception:
        ...

    # AFTER:
    try:
        cached = await storage.lookup(purl_key)
        if cached is not None:
            logger.info("Cache hit for %s", purl_key)
            cached = await _validate_cached_url(cached, settings_store, purl_key, storage)
        if cached is not None:
            return ResolveResult.ok(cached)
    except Exception:
        logger.warning(
            "Cache lookup failed for %s, falling through to resolver",
            purl_key,
            exc_info=True,
        )
```

- [ ] **Step 12: Run all tests**

Run: `.venv/bin/pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 13: Commit P1 changes**

```bash
git add src/purl_resolver/service.py tests/test_service_validation.py
git commit -m "refactor: extract URL validation from resolve_purl into _validate_cached_url"
```

---

## Task 3: P2 — Split router.py into domain-specific sub-routers

**Files:**
- Create: `src/purl_resolver/routes/__init__.py`
- Create: `src/purl_resolver/routes/resolve.py`
- Create: `src/purl_resolver/routes/db_admin.py`
- Create: `src/purl_resolver/routes/settings.py`
- Modify: `src/purl_resolver/router.py`

- [ ] **Step 1: Create routes package**

Create `src/purl_resolver/routes/__init__.py` (empty file).

- [ ] **Step 2: Create routes/resolve.py**

Create `src/purl_resolver/routes/resolve.py`:

```python
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import JSONResponse

from ..config import sbom_settings
from ..schemas import ResolveRequest
from ..service import resolve_purl
from ..sbom_enrichment import SbomEnrichmentPipeline
from ..sbom.parser import SbomParseError

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/api/v1/resolve")
async def resolve_endpoint(body: ResolveRequest, request: Request) -> JSONResponse:
    result = await resolve_purl(
        purl=body.purl,
        storage=request.app.state.storage,
        resolvers=request.app.state.resolvers,
        settings_store=request.app.state.settings_store,
    )

    if result.error_status is not None:
        return JSONResponse(
            status_code=result.error_status, content=result.error_body
        )

    return JSONResponse(status_code=200, content=result.response.model_dump())


@router.post("/api/v1/resolve/sbom")
async def resolve_sbom_endpoint(
    request: Request,
    file: UploadFile = File(...),
    remove_unresolved_no_subcomponents: bool = Form(False),
) -> JSONResponse:
    raw = await file.read()
    if len(raw) > sbom_settings.max_file_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={
                "error": "file_too_large",
                "message": f"File size exceeds maximum of {sbom_settings.max_file_size // (1024*1024)} MB",
            },
        )

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        return JSONResponse(
            status_code=400,
            content={"error": "invalid_json", "message": f"Invalid JSON: {e}"},
        )

    pipeline = SbomEnrichmentPipeline(
        storage=request.app.state.storage,
        resolvers=request.app.state.resolvers,
        settings_store=getattr(request.app.state, "settings_store", None),
    )

    try:
        result = await pipeline.process(data, remove_unresolved_no_subcomponents=remove_unresolved_no_subcomponents)
    except SbomParseError as e:
        return JSONResponse(
            status_code=400,
            content={"error": "invalid_sbom", "message": str(e)},
        )

    return JSONResponse(
        status_code=200,
        content={**result.report, "enriched_sbom": result.enriched_sbom},
    )
```

- [ ] **Step 3: Create routes/db_admin.py**

Create `src/purl_resolver/routes/db_admin.py`:

```python
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, File, Query, Request, UploadFile
from fastapi.responses import JSONResponse, Response

from ..schemas import (
    DeleteResponse,
    ImportErrorItem,
    ImportResponse,
    ImportStrategy,
    PurlDeleteRequest,
    PurlListParams,
    PurlListResponse,
    PurlUpdateRequest,
)
from ..storage.interface import PurlFilters
from ..csv_io import parse_csv_import, render_csv_export

router = APIRouter()


@router.get("/api/v1/db/purls")
async def list_purls_endpoint(request: Request, params: PurlListParams = Query()):
    storage = request.app.state.storage
    filters = PurlFilters(
        search=params.search,
        resolver=params.resolver,
        confidence=params.confidence,
        date_from=params.date_from,
        date_to=params.date_to,
    )
    total = await storage.count_purls(filters)
    offset = (params.page - 1) * params.page_size
    rows = await storage.list_purls(
        offset=offset,
        limit=params.page_size,
        filters=filters,
        sort_by=params.sort_by,
        sort_order=params.sort_order,
    )
    row_responses = [r.to_resolve_response() for r in rows]
    return JSONResponse(
        status_code=200,
        content=PurlListResponse(
            rows=row_responses,
            total=total,
            page=params.page,
            page_size=params.page_size,
        ).model_dump(),
    )


@router.patch("/api/v1/db/purls/{purl:path}")
async def update_purl_endpoint(
    purl: str, body: PurlUpdateRequest, request: Request
):
    new_purl = body.purl if body.purl is not None else purl
    new_repo = body.repository_url if body.repository_url is not None else ""
    storage = request.app.state.storage

    existing = await storage.lookup(purl)
    if new_repo == "" and existing is not None:
        new_repo = existing.repository_url or ""

    if new_repo == "":
        return JSONResponse(
            status_code=400,
            content={"error": "invalid_update", "message": "repository_url is required for new rows"},
        )

    ok = await storage.update_purl(purl, new_purl, new_repo)
    if not ok:
        return JSONResponse(
            status_code=404,
            content={"error": "not_found", "message": "PURL not found"},
        )
    return JSONResponse(status_code=200, content={"ok": True})


@router.delete("/api/v1/db/purls")
async def delete_purls_endpoint(body: PurlDeleteRequest, request: Request):
    storage = request.app.state.storage
    deleted = await storage.delete_purls(body.purls)
    return JSONResponse(status_code=200, content={"deleted": deleted})


@router.post("/api/v1/db/import")
async def import_csv_endpoint(
    request: Request,
    file: UploadFile = File(...),
    strategy: ImportStrategy = Form(...),
):
    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return JSONResponse(
            status_code=400,
            content={"error": "invalid_csv", "message": "File must be UTF-8 encoded"},
        )

    rows, errors = parse_csv_import(text)
    if not rows and errors:
        return JSONResponse(
            status_code=400,
            content={"error": "invalid_csv", "message": errors[0]["error"]},
        )

    storage = request.app.state.storage

    if strategy == ImportStrategy.skip_existing:
        to_insert = []
        skipped = 0
        for row in rows:
            existing = await storage.lookup(row.purl)
            if existing is not None:
                skipped += 1
            else:
                to_insert.append(row)
        upserted, _ = await storage.upsert_many(to_insert)
        return JSONResponse(
            status_code=200,
            content=ImportResponse(
                imported=upserted,
                skipped=skipped,
                errors=[ImportErrorItem(row=e["row"], error=str(e["error"])) for e in errors],
            ).model_dump(),
        )

    upserted, _ = await storage.upsert_many(rows)
    return JSONResponse(
        status_code=200,
        content=ImportResponse(
            imported=upserted,
            skipped=0,
            errors=[ImportErrorItem(row=e["row"], error=str(e["error"])) for e in errors],
        ).model_dump(),
    )


@router.get("/api/v1/db/export")
async def export_csv_endpoint(
    request: Request,
    search: str | None = Query(None),
    resolver: str | None = Query(None),
    confidence: str | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    sort_by: str = Query("resolved_at"),
    sort_order: str = Query("desc"),
):
    storage = request.app.state.storage
    filters = PurlFilters(
        search=search,
        resolver=resolver,
        confidence=confidence,
        date_from=date_from,
        date_to=date_to,
    )
    total = await storage.count_purls(filters)
    rows = await storage.list_purls(
        offset=0,
        limit=max(total, 1),
        filters=filters,
        sort_by=sort_by,
        sort_order=sort_order,
    )

    csv_text = render_csv_export(rows)
    csv_bytes = csv_text.encode("utf-8")
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="resolved_purls_export.csv"'},
    )
```

- [ ] **Step 4: Create routes/settings.py**

Create `src/purl_resolver/routes/settings.py`:

```python
from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..settings_store import SettingsStore
from ..url_validator import validate_github_token

logger = logging.getLogger(__name__)

router = APIRouter()


async def validate_librariesio_key(api_key: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://libraries.io/api/platforms",
                params={"api_key": api_key},
            )
            return response.status_code == 200
    except httpx.HTTPError:
        return True


class SettingsUpdate(BaseModel):
    validate_db_urls: bool | None = None
    url_validation_timeout: int | None = Field(None, ge=1, le=60)
    github_token: str | None = None
    librariesio_enabled: bool | None = None
    librariesio_api_key: str | None = None
    ecosystems_enabled: bool | None = None
    ecosystems_api_key: str | None = None


def _rebuild_resolvers(request: Request) -> None:
    store: SettingsStore = request.app.state.settings_store
    app_settings = store.load()

    from ..config import settings
    from ..resolver.factory import build_resolvers

    request.app.state.resolvers = build_resolvers(settings, app_settings)


@router.get("/api/v1/settings")
async def get_settings(request: Request) -> JSONResponse:
    store: SettingsStore = request.app.state.settings_store
    settings = store.load()
    return JSONResponse(content={
        "validate_db_urls": settings.validate_db_urls,
        "url_validation_timeout": settings.url_validation_timeout,
        "librariesio_enabled": settings.librariesio_enabled,
        "ecosystems_enabled": settings.ecosystems_enabled,
        "token_set": {
            "github_token": settings.github_token is not None,
            "librariesio_api_key": settings.librariesio_api_key is not None,
            "ecosystems_api_key": settings.ecosystems_api_key is not None,
        },
    })


@router.patch("/api/v1/settings")
async def update_settings(body: SettingsUpdate, request: Request) -> JSONResponse:
    store: SettingsStore = request.app.state.settings_store
    current = store.load()
    update_data = body.model_dump(exclude_unset=True)

    if "github_token" in update_data:
        token_value = update_data["github_token"]
        if token_value is None:
            pass
        elif token_value == "":
            del update_data["github_token"]
        else:
            is_valid = await validate_github_token(token_value)
            if not is_valid:
                return JSONResponse(
                    status_code=400,
                    content={"error": "invalid_token", "message": "GitHub token is invalid or expired"},
                )

    if "librariesio_api_key" in update_data:
        key_value = update_data["librariesio_api_key"]
        if key_value is None:
            pass
        elif key_value == "":
            del update_data["librariesio_api_key"]
        else:
            if not await validate_librariesio_key(key_value):
                return JSONResponse(
                    status_code=400,
                    content={"error": "invalid_token", "message": "Libraries.io API key is invalid"},
                )

    if update_data:
        updated = current.model_copy(update=update_data)
        store.save(updated)
    else:
        updated = current

    _rebuild_resolvers(request)

    return JSONResponse(content={
        "validate_db_urls": updated.validate_db_urls,
        "url_validation_timeout": updated.url_validation_timeout,
        "librariesio_enabled": updated.librariesio_enabled,
        "ecosystems_enabled": updated.ecosystems_enabled,
        "token_set": {
            "github_token": updated.github_token is not None,
            "librariesio_api_key": updated.librariesio_api_key is not None,
            "ecosystems_api_key": updated.ecosystems_api_key is not None,
        },
    })
```

- [ ] **Step 5: Simplify router.py**

Replace the entire content of `src/purl_resolver/router.py` with:

```python
from __future__ import annotations

import pathlib

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from .routes.resolve import router as resolve_router
from .routes.db_admin import router as db_admin_router
from .routes.settings import router as settings_router

router = APIRouter()
_templates_dir = (pathlib.Path(__file__).parent / "templates").resolve()
templates = Jinja2Templates(directory=str(_templates_dir))

router.include_router(resolve_router)
router.include_router(db_admin_router)
router.include_router(settings_router)


@router.get("/health")
async def health() -> JSONResponse:
    return JSONResponse(content={"status": "ok"})


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="index.html")


@router.get("/sbom-updater", response_class=HTMLResponse)
async def sbom_updater_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="sbom.html")


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="settings.html")


@router.get("/db-admin", response_class=HTMLResponse)
async def db_admin_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="db-admin.html")
```

- [ ] **Step 6: Run all tests**

Run: `.venv/bin/pytest tests/ -v`
Expected: All tests PASS (root router includes all sub-routers)

- [ ] **Step 7: Commit P2 changes**

```bash
git add src/purl_resolver/routes/ src/purl_resolver/router.py
git commit -m "refactor: split router.py into domain-specific sub-routers"
```

---

## Task 4: Final verification

- [ ] **Step 1: Run full test suite**

Run: `.venv/bin/pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 2: Verify no import cycles**

Run: `.venv/bin/python -c "from purl_resolver.main import app; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Verify line count reduction in router.py**

Run: `wc -l src/purl_resolver/router.py`
Expected: ~30 lines (down from 400)
