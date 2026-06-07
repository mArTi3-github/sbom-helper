# Refactoring Plan: sbom-helper

## Executive Summary

The codebase is well-structured with clear layer separation and good architectural decisions (ADR-0001 through ADR-0005). The main issues are:
- A bloated `router.py` (419 lines) that mixes HTTP concerns with business logic
- A monolithic `resolve_purl()` function (110+ lines) with deeply nested URL validation
- Duplicated filter-building SQL in `postgres.py`
- Duplicated resolver initialization logic between `main.py` and `router.py`
- Business logic validation (token/key) living in the API layer
- Significant data model overlap (`ResolveResponse`, `PurlRow`, `UpsertRow`, `Resolution`)

---

## Priority 1: Extract URL Validation Logic from `resolve_purl` (service.py)

**Problem:** `resolve_purl()` at `src/purl_resolver/service.py:20-131` is 112 lines with 5 levels of nesting. The URL validation block (lines 39-84) is ~45 lines of conditional logic that obscures the core resolution flow.

**Risk:** Medium — this is the hot path for every PURL resolution.

**Proposed change:**
```python
async def _validate_cached_url(
    cached: ResolveResponse,
    settings_store: SettingsStore,
    purl_key: str,
    storage: Storage,
) -> ResolveResponse | None:
    """Validate cached URL; returns cached if valid, None if invalid/expired."""
```

**Steps:**
1. Extract the URL validation block (lines 39-84) into a private async function `_validate_cached_url()`.
2. The function returns the (possibly updated) `cached` response, or `None` if the cache entry should be discarded.
3. `resolve_purl()` becomes: validate → normalize → cache lookup → validate cached → resolve chain → store.
4. Add unit tests specifically for the extracted function.

**Expected impact:** `resolve_purl` drops from ~112 lines to ~50 lines. Each path becomes independently testable.

---

## Priority 2: Split `router.py` into Domain-Specific Routers

**Problem:** `router.py` (419 lines) contains 15+ route handlers plus helper functions for:
- PURL resolution (`/api/v1/resolve`)
- SBOM enrichment (`/api/v1/resolve/sbom`)
- DB admin CRUD (`/api/v1/db/purls`, `/api/v1/db/import`, `/api/v1/db/export`)
- Settings management (`/api/v1/settings`)
- Page rendering (`/`, `/sbom-updater`, `/db-admin`, `/settings`)
- `_rebuild_resolvers()` helper (duplicates `main.py` logic)
- `validate_librariesio_key()` (synchronous HTTP call in async context)

**Proposed split:**
| New File | Responsibility |
|----------|---------------|
| `router.py` | Mount sub-routers + page templates only |
| `routes/resolve.py` | `POST /api/v1/resolve`, `POST /api/v1/resolve/sbom` |
| `routes/db_admin.py` | All `/api/v1/db/*` endpoints |
| `routes/settings.py` | `GET/PATCH /api/v1/settings`, `_rebuild_resolvers()` |

**Risk:** Low — FastAPI sub-routers are a well-supported pattern; tests import `app` not `router`.

**Steps:**
1. Create `src/purl_resolver/routes/` package.
2. Move each group of handlers into its own module with its own `APIRouter`.
3. Mount all sub-routers in `main.py` via `app.include_router(...)`.
4. Move `_rebuild_resolvers()` into `routes/settings.py` or a new `resolver_factory.py` module.
5. Move `validate_librariesio_key()` into a utility or the settings route module.
6. Update tests if they import from `router.py` directly.

---

## Priority 3: Extract Resolver Factory from `main.py` / `router.py`

**Problem:** Resolver initialization logic is duplicated:
- `main.py:35-49` creates `Purl2RepoResolver` + conditionally `LibrariesIoResolver`
- `router.py:322-348` (`_rebuild_resolvers`) creates `Purl2RepoResolver` + conditionally `EcosystemsResolver` + conditionally `LibrariesIoResolver`

These are not in sync — `main.py` doesn't add `EcosystemsResolver`, while `_rebuild_resolvers` does.

**Proposed change:** Create `src/purl_resolver/resolver/factory.py`:
```python
def build_resolvers(
    settings: Settings,
    app_settings: AppSettings,
) -> list[Resolver]:
    resolvers = [Purl2RepoResolver(...)]
    if app_settings.ecosystems_enabled:
        resolvers.append(EcosystemsResolver(...))
    if app_settings.librariesio_enabled and app_settings.librariesio_api_key:
        resolvers.append(LibrariesIoResolver(...))
    return resolvers
```

**Risk:** Low — centralizes a single responsibility; both callers become trivial.

**Steps:**
1. Create `resolver/factory.py` with `build_resolvers()`.
2. Replace the inline logic in `main.py` lifespan and `_rebuild_resolvers()` in `router.py`.
3. Tests can now test resolver composition in isolation.

---

## Priority 4: Deduplicate Filter Building in `postgres.py`

**Problem:** `list_purls()` (lines 100-162) and `count_purls()` (lines 164-195) have nearly identical filter-building code — the same 5 `if` clauses and parameter index management. Changing the filter schema requires editing both methods.

**Proposed change:**
```python
def _build_filter_sql(
    filters: PurlFilters,
    start_idx: int = 1,
) -> tuple[str, list[object], int]:
    """Returns (where_clause, params, next_idx)."""
    clauses, params, idx = [], [], start_idx
    if filters.search is not None:
        clauses.append(f"purl ILIKE ${idx}")
        params.append(f"%{filters.search}%")
        idx += 1
    # ... etc
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params, idx
```

**Risk:** Very low — pure extraction with no behavioral change.

**Steps:**
1. Extract `_build_filter_sql()`.
2. Simplify both `list_purls` and `count_purls` to call it.
3. Add a test that exercises both methods with the same filters to verify consistency.

---

## Priority 5: Unify Data Models / Reduce Mapping Boilerplate

**Problem:** There are 4 overlapping data types:
- `Resolution` (resolver layer — frozen dataclass)
- `ResolveResponse` (schemas — Pydantic BaseModel)
- `PurlRow` (storage — dataclass)
- `UpsertRow` (storage — dataclass)

The `list_purls_endpoint` in `router.py:161-174` manually maps `PurlRow` → `ResolveResponse` field by field. `postgres.py:148-162` maps asyncpg rows → `PurlRow` field by field.

**Proposed approach:** Don't merge them all — that would violate the layer boundary principle. Instead:
1. Add a `PurlRow.from_response(r: ResolveResponse) -> PurlRow` class method.
2. Add a `PurlRow.to_resolve_response() -> ResolveResponse` class method.
3. This centralizes the mapping logic and eliminates the field-by-field boilerplate in `router.py` and `postgres.py`.

**Risk:** Low — additive changes to existing types.

**Steps:**
1. Add conversion methods to `PurlRow`.
2. Refactor `list_purls_endpoint` to use `row.to_resolve_response()`.
3. Refactor `PostgresCache.list_purls` to use `PurlRow.from_dict(row)`.

---

## Priority 6: Fix `repository_kind` Inconsistency

**Problem:** The `repository_kind` field uses inconsistent values:
- `librariesio.py:90` → `"source"`
- `ecosystems.py:85` → `"vcs"`
- `test fixtures/conftest.py:19` → `"source_code"`
- `collector.py:5` defines `_SOURCE_REF_TYPES = {"vcs", "source-distribution"}`

Per the project plan, the two valid values should be `"vcs"` and `"source_distribution"`.

**Proposed change:**
1. Fix `librariesio.py` to return `"vcs"` (it returns GitHub repo URLs) or a more appropriate kind.
2. Standardize on `"vcs"` and `"source_distribution"` as the only valid values.
3. Consider adding a `RepositoryKind` enum in `schemas.py`.

**Risk:** Low — affects only display and filtering, no core logic depends on exact string values.

---

## Priority 7: Move Token Validation Out of Router

**Problem:** `validate_librariesio_key()` (router.py:39-48) and `validate_github_token()` calls (router.py:381) are synchronous HTTP calls made in async route handlers. `validate_librariesio_key` uses `httpx.get` (synchronous) which blocks the event loop.

**Proposed change:**
1. Make `validate_librariesio_key()` async using `httpx.AsyncClient`.
2. Move key validation into a settings service module or keep in the settings route but ensure all HTTP calls are async.
3. Alternatively, create a `services/token_validator.py` that both the settings route and the service layer can use.

**Risk:** Low — straightforward async conversion.

---

## Priority 8: Add Type Hints for `settings_store` Parameters

**Problem:** `resolve_purl()` and `resolve_batch()` accept `settings_store=None` without a type hint, making the interface unclear. The `SbomEnrichmentPipeline.__init__` also takes `settings_store=None`.

**Proposed change:** Add explicit type annotation:
```python
from .settings_store import SettingsStore | None

async def resolve_purl(
    purl: str,
    storage: Storage,
    resolvers: list[Resolver],
    settings_store: SettingsStore | None = None,
    resolver: str = "",
) -> ResolveResult:
```

**Risk:** Very low — type annotation only, no runtime change.

---

## Implementation Order

| Step | Priority | Effort | Risk | Description |
|------|----------|--------|------|-------------|
| 1 | P8 | Small | Very Low | Add type hints for `settings_store` |
| 2 | P4 | Small | Very Low | Extract `_build_filter_sql()` in postgres.py |
| 3 | P3 | Small | Low | Extract resolver factory |
| 4 | P6 | Small | Low | Fix `repository_kind` inconsistency |
| 5 | P5 | Medium | Low | Add conversion methods to data models |
| 6 | P1 | Medium | Medium | Extract URL validation from `resolve_purl()` |
| 7 | P2 | Medium | Low | Split router.py into sub-routers |
| 8 | P7 | Small | Low | Make `validate_librariesio_key` async |

Total estimated effort: ~3-4 hours of focused refactoring.

## Testing Strategy

- After each step, run `.venv/bin/pytest tests/ -v` to verify no regressions.
- Steps P1 and P3 specifically need new unit tests for the extracted functions.
- Steps P4, P5, P6, P7 are safe refactors where existing tests should pass without modification.
- Step P2 (router split) may require updating test imports if tests reference `router` directly.

## Anti-Patterns to Avoid

Per `specs/architecture/layers.md`:
- Do NOT bypass the API Layer — keep all external access through router endpoints
- Do NOT put SBOM orchestration logic in `router.py`
- Do NOT store state in the API Layer
- Do NOT change canonical response format without updating `contracts/api-contract.md`
