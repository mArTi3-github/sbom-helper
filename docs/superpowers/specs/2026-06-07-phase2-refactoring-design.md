# Phase 2 Refactoring Design

## Overview

Three independent refactoring changes to improve code quality and maintainability of the sbom-helper project. Based on architecture analysis results from `sbom-helper-refactoring-analysis-2026-06-07-part2.md`.

## Scope

| Change | Problem | Risk | Effort |
|--------|---------|------|--------|
| P5: Unify Data Models | Manual field-by-field mapping between `PurlRow` and `ResolveResponse` in 2 locations | Low | ~30 min |
| P1: Extract URL Validation | `resolve_purl()` is 112 lines with 5 nesting levels; URL validation block is ~45 lines | Medium | ~45-60 min |
| P2: Split router.py | `router.py` (400 lines) contains 15+ handlers for 5 different domains | Low | ~60-90 min |

## Implementation Order

P5 → P1 → P2. Each step followed by `.venv/bin/pytest tests/ -v` to verify no regressions.

---

## P5: Unify Data Models / Reduce Mapping Boilerplate

### Problem

Two locations manually map fields between `PurlRow` and `ResolveResponse`:
- `router.py:161-174` — `PurlRow → ResolveResponse`
- `postgres.py:49-59` — asyncpg row → `ResolveResponse`

### Solution

Add two methods to `PurlRow` dataclass in `src/purl_resolver/storage/interface.py`:

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

### Call site changes

- `router.py:161-174`: replace manual mapping with `[r.to_resolve_response() for r in rows]`
- `postgres.py:49-59`: keep `PurlRow(...)` constructor, add `.to_resolve_response()` for final conversion

### Files modified

- `src/purl_resolver/storage/interface.py` — add methods to `PurlRow`
- `src/purl_resolver/router.py` — simplify `list_purls_endpoint`
- `src/purl_resolver/storage/postgres.py` — simplify `lookup()`

---

## P1: Extract URL Validation Logic from `resolve_purl`

### Problem

`resolve_purl()` in `service.py` is 112 lines with 5 levels of nesting. The URL validation block (lines 39-84) is ~45 lines of conditional logic embedded in the cache hit path.

### Solution

Extract into a private async function:

```python
async def _validate_cached_url(
    cached: ResolveResponse,
    settings_store: SettingsStore,
    purl_key: str,
    storage: Storage,
) -> ResolveResponse | None:
```

### Logic branches

1. `settings_store is None` or `validate_db_urls is False` → return `cached`
2. Resolution date matches today → return `cached`
3. Call `validate_url()` with token
4. `TOKEN_INVALID` → remove token from settings, retry without token
5. `VALID` → update `resolved_at` in storage, return `cached`
6. `INVALID` → delete from cache, return `None`
7. `NETWORK_ERROR` / `RATE_LIMITED` → return `cached` as-is

### New `resolve_purl()` structure

```python
async def resolve_purl(...):
    try:
        components = validate(purl)
    except Exception as e:
        return ResolveResult.err(400, "invalid_purl", str(e))

    purl_key = normalize(components)

    try:
        cached = await storage.lookup(purl_key)
        if cached is not None:
            logger.info("Cache hit for %s", purl_key)
            cached = await _validate_cached_url(cached, settings_store, purl_key, storage)
        if cached is not None:
            return ResolveResult.ok(cached)
    except Exception:
        logger.warning("Cache lookup failed for %s, falling through to resolver", purl_key, exc_info=True)

    # resolve chain (unchanged)
```

### New tests

Unit tests for `_validate_cached_url()` covering all 7 branches:
- `settings_store is None` → returns cached
- `validate_db_urls is False` → returns cached
- Date matches today → returns cached
- `TOKEN_INVALID` → removes token, retries
- `VALID` → updates `resolved_at`
- `INVALID` → deletes from cache, returns None
- `NETWORK_ERROR` → returns cached

### Files modified

- `src/purl_resolver/service.py` — extract function, simplify `resolve_purl()`
- `tests/test_service_validation.py` — add unit tests for `_validate_cached_url()`

---

## P2: Split router.py into Domain-Specific Routers

### Problem

`router.py` (400 lines) contains 15+ route handlers for PURL resolution, SBOM enrichment, DB admin CRUD, settings management, and page rendering.

### Solution

Create `src/purl_resolver/routes/` package:

```
src/purl_resolver/routes/
├── __init__.py
├── resolve.py      — POST /api/v1/resolve, POST /api/v1/resolve/sbom
├── db_admin.py     — all /api/v1/db/* endpoints
└── settings.py     — GET/PATCH /api/v1/settings, _rebuild_resolvers()
```

Each module contains its own `APIRouter`:

```python
# routes/resolve.py
router = APIRouter()

@router.post("/api/v1/resolve")
async def resolve_endpoint(...): ...

@router.post("/api/v1/resolve/sbom")
async def resolve_sbom_endpoint(...): ...
```

### Main router.py (simplified)

Retains:
- `health` endpoint
- HTML page routes (index, sbom-updater, settings, db-admin)
- Template setup

Mounts sub-routers:

```python
from .routes.resolve import router as resolve_router
from .routes.db_admin import router as db_admin_router
from .routes.settings import router as settings_router

router.include_router(resolve_router)
router.include_router(db_admin_router)
router.include_router(settings_router)
```

### Test compatibility

Tests importing `from purl_resolver.router import router` continue to work because the root router includes all sub-routers via `include_router()`.

### Files modified

- `src/purl_resolver/routes/__init__.py` — new (empty)
- `src/purl_resolver/routes/resolve.py` — new (resolve + SBOM endpoints)
- `src/purl_resolver/routes/db_admin.py` — new (DB admin CRUD + import/export)
- `src/purl_resolver/routes/settings.py` — new (settings + resolver rebuild)
- `src/purl_resolver/router.py` — simplified (pages + health + include_router)
- `src/purl_resolver/main.py` — no changes needed (already uses root router)

---

## Testing Strategy

After each step: `.venv/bin/pytest tests/ -v`

- **P5**: existing tests pass without changes (additive methods)
- **P1**: new unit tests for `_validate_cached_url()` + existing tests verify `resolve_purl()` still works
- **P2**: existing tests pass via root router (no import changes needed)

## Risk Assessment

| Change | Risk | Mitigation |
|--------|------|------------|
| P5 | Low | Purely additive; existing tests verify behavior unchanged |
| P1 | Medium | Hot path for every PURL resolution; thorough unit tests for all branches |
| P2 | Low | Well-supported FastAPI pattern; tests import root router |
