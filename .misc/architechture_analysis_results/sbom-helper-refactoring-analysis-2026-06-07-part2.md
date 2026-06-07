# Refactoring Plan: sbom-helper (Phase 2 — Future Session)

## Scope

Three medium-effort refactoring changes deferred from Phase 1. Each is independent and can be implemented in any order.

---

## Priority 5: Unify Data Models / Reduce Mapping Boilerplate

**Problem:** `list_purls_endpoint` in `router.py:161-174` manually maps `PurlRow` → `ResolveResponse` field by field. `postgres.py:49-59` maps asyncpg rows → `ResolveResponse` field by field.

**Proposed change:** Add conversion methods to `PurlRow`:
1. `PurlRow.from_response(r: ResolveResponse) -> PurlRow` — class method
2. `PurlRow.to_resolve_response() -> ResolveResponse` — instance method

**Files:** `src/purl_resolver/storage/interface.py`, `src/purl_resolver/router.py`, `src/purl_resolver/storage/postgres.py`

**Steps:**
1. Add conversion methods to `PurlRow` dataclass
2. Refactor `list_purls_endpoint` to use `row.to_resolve_response()`
3. Refactor `PostgresCache.lookup` to use `PurlRow` → `ResolveResponse` conversion

**Risk:** Low — additive changes to existing types.

---

## Priority 1: Extract URL Validation Logic from `resolve_purl`

**Problem:** `resolve_purl()` at `src/purl_resolver/service.py:20-131` is 112 lines with 5 levels of nesting. The URL validation block (lines 39-84) is ~45 lines of conditional logic.

**Proposed change:** Extract into private async function:
```python
async def _validate_cached_url(
    cached: ResolveResponse,
    settings_store: SettingsStore,
    purl_key: str,
    storage: Storage,
) -> ResolveResponse | None:
    """Validate cached URL; returns cached if valid, None if invalid/expired."""
```

**Files:** `src/purl_resolver/service.py`

**Steps:**
1. Extract the URL validation block (lines 39-84) into `_validate_cached_url()`
2. Handle side effects: token removal on `TOKEN_INVALID`, cache deletion on `INVALID`
3. `resolve_purl()` becomes: validate → normalize → cache lookup → validate cached → resolve chain → store
4. Add unit tests for the extracted function

**Risk:** Medium — this is the hot path for every PURL resolution. Careful testing required.

---

## Priority 2: Split `router.py` into Domain-Specific Routers

**Problem:** `router.py` (419 lines) contains 15+ route handlers for PURL resolution, SBOM enrichment, DB admin CRUD, settings management, and page rendering.

**Proposed split:**
| New File | Responsibility |
|----------|---------------|
| `router.py` | Mount sub-routers + page templates only |
| `routes/resolve.py` | `POST /api/v1/resolve`, `POST /api/v1/resolve/sbom` |
| `routes/db_admin.py` | All `/api/v1/db/*` endpoints |
| `routes/settings.py` | `GET/PATCH /api/v1/settings`, `build_resolvers()` |

**Files:** `src/purl_resolver/routes/` (new package), `src/purl_resolver/main.py`, `src/purl_resolver/router.py`

**Steps:**
1. Create `src/purl_resolver/routes/` package with `__init__.py`
2. Move each group of handlers into its own module with its own `APIRouter`
3. Mount all sub-routers in `main.py` via `app.include_router(...)`
4. Move `build_resolvers()` into `routes/settings.py` or keep in `resolver/factory.py`
5. Update tests if they import from `router.py` directly

**Risk:** Low — FastAPI sub-routers are a well-supported pattern.

---

## Implementation Order (for future session)

| Step | Priority | Effort | Risk | Description |
|------|----------|--------|------|-------------|
| 1 | P5 | Medium | Low | Add conversion methods to data models |
| 2 | P1 | Medium | Medium | Extract URL validation from `resolve_purl()` |
| 3 | P2 | Medium | Low | Split router.py into sub-routers |

Total estimated effort: ~2 hours.

## Dependencies

- Phase 1 (P8, P4, P3, P6, P7) must be completed first
- P3 (resolver factory) should be done before P2 (router split), since P2 moves `_rebuild_resolvers()` logic

## Testing Strategy

- After each step, run `.venv/bin/pytest tests/ -v` to verify no regressions
- P1 specifically needs new unit tests for the extracted `_validate_cached_url` function
- P2 may require updating test imports if tests reference `router` directly
