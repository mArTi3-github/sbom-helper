# Refactoring Phase 1: Low-Risk Improvements

## Scope

Five isolated, low-risk refactoring changes to improve code quality without altering behavior.

## Changes

### P8: Add Type Hints for `settings_store` Parameters

**Files:** `src/purl_resolver/service.py`, `src/purl_resolver/sbom_enrichment.py`

Add explicit `SettingsStore | None` type annotation to `settings_store` parameters in:
- `resolve_purl()` (service.py:24)
- `resolve_batch()` (service.py:138)
- `SbomEnrichment.__init__()` (sbom_enrichment.py)

No runtime change. Improves IDE support and interface clarity.

---

### P4: Deduplicate Filter Building in `postgres.py`

**Files:** `src/purl_resolver/storage/postgres.py`

Extract shared filter-building logic from `list_purls()` and `count_purls()` into:

```python
def _build_filter_sql(
    filters: PurlFilters,
    start_idx: int = 1,
) -> tuple[str, list[object], int]:
    """Returns (where_clause, params, next_idx)."""
```

Both methods call this function instead of duplicating the 5 `if` clauses. Pure extraction, no behavioral change.

---

### P3: Extract Resolver Factory

**Files:** `src/purl_resolver/resolver/factory.py` (new), `src/purl_resolver/main.py`, `src/purl_resolver/router.py`

Create `build_resolvers(settings, app_settings) -> list[Resolver]` that centralizes resolver initialization. Fixes bug where `main.py` did not add `EcosystemsResolver` while `_rebuild_resolvers()` did.

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

Replace inline logic in `main.py` lifespan and `_rebuild_resolvers()` in `router.py`.

---

### P6: Fix `repository_kind` Inconsistency

**Files:** `src/purl_resolver/resolver/librariesio.py`, `tests/conftest.py`, `src/purl_resolver/schemas.py`

Canonical values: `"vcs"` and `"source-distribution"` (matching `collector.py`).

Changes:
- `librariesio.py:90` — `"source"` → `"vcs"` (returns GitHub repo URLs)
- `conftest.py:19` — `"source_code"` → `"vcs"`
- Add `REPOSITORY_KINDS = frozenset({"vcs", "source-distribution"})` to `schemas.py` as reference constant

---

### P7: Make `validate_librariesio_key` Async

**Files:** `src/purl_resolver/router.py`

Convert `validate_librariesio_key()` from synchronous `httpx.get` to async `httpx.AsyncClient`. Currently blocks the event loop in an async route handler.

```python
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
```

Update caller in `update_settings` to `await validate_librariesio_key(...)`.

---

## Testing Strategy

After each step: `.venv/bin/pytest tests/ -v`

- P8: existing tests pass (type hints only)
- P4: existing tests pass; add one test verifying filter consistency
- P3: existing tests pass; add test for `build_resolvers()` composition
- P6: existing tests pass; verify `conftest.py` fixture updated
- P7: existing tests pass; verify async caller works

## Anti-Patterns Avoided

- Do NOT bypass API Layer
- Do NOT change canonical response format
- Do NOT add unnecessary abstractions
