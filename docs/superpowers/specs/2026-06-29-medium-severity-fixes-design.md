# Medium-Severity Architecture Fixes — Design Document

**Date:** 2026-06-29
**Source:** `sbom-helper-refactoring-analysis-2026-06-27.md` (items 4–8)

## Overview

This document covers four medium-severity architectural issues identified in the sbom-helper refactoring analysis, their agreed solutions, and scope boundaries.

---

## Fix #1: SettingsStore caching

### Problem
`SettingsStore.load()` reads a JSON file from disk on every invocation. In a batch PURL resolution (100–300 PURLs), `load()` is called 3–5 times per request — once in `_is_within_cooldown()`, once in `_validate_cached_url()`, once in the resolver loop, and once in `SbomEnrichmentPipeline.process()`. This results in 100–300+ redundant I/O operations per batch.

### Solution
Add instance-level caching to `SettingsStore`:

```python
class SettingsStore:
    _cached: AppSettings | None = None

    def load(self) -> AppSettings:
        if self._cached is not None:
            return self._cached
        # read file, parse, cache
        self._cached = result
        return result

    def save(self, settings: AppSettings) -> None:
        self._cached = None   # invalidate
        self._write(settings)
```

No TTL is needed — `save()` invalidates the cache immediately. The only scenario where the cache becomes stale (external file edit) is not a supported workflow.

### Files affected
- `src/purl_resolver/settings_store.py` — modify `load()` and `save()`

### Testing
- Existing tests in `test_settings_store.py` remain passing
- Add one test: after `save()`, next `load()` re-reads from file

---

## Fix #2: SbomEnrichmentPipeline dependency consolidation

### Problem
`SbomEnrichmentPipeline.__init__` accepts `storage`, `resolvers`, `settings_store`, `validation_service` in addition to `resolution_service` — even though `storage` and `resolvers` are never used in `process()` (dead code), and `settings_store`/`validation_service` are already owned by `PurlResolutionService`.

### Solution
1. Remove `storage` and `resolvers` from `SbomEnrichmentPipeline.__init__`
2. Add read-only `settings_store` and `validation_service` properties to `PurlResolutionService`
3. Use these properties in `SbomEnrichmentPipeline.process()`

### Files affected
- `src/purl_resolver/sbom_enrichment.py` — remove `storage`, `resolvers` from `__init__`; obtain `settings_store` via `resolution_service`
- `src/purl_resolver/service.py` — add `@property settings_store` and `@property validation_service`
- `src/purl_resolver/routes/resolve.py` — simplify pipeline construction

### Testing
- Existing tests in `test_sbom_enricher.py`, `test_storage.py`, `test_resolve_batch.py` remain passing
- Quick check: no test directly constructs `SbomEnrichmentPipeline`

---

## Fix #3: Remove late imports in `_rebuild_resolvers`

### Problem
`routes/settings.py:_rebuild_resolvers()` uses late imports (`from ..config import settings`, `from ..resolver.factory import build_resolvers`) to avoid a circular dependency that does not actually exist. This is misleading and considered a code smell.

### Solution
Move both imports to the top level:
```python
from ..config import settings
from ..resolver.factory import build_resolvers
```
Verified import chain: `routes/settings.py` → `resolver/factory.py` → `config.py` (no project imports) — no cycle exists.

### Files affected
- `src/purl_resolver/routes/settings.py` — move two imports from function body to module level

### Testing
- Import test: `python -c "from purl_resolver.routes.settings import _rebuild_resolvers"`
- Existing tests in `test_api.py` exercise the settings routes

---

## Fix #4: InMemoryCache date filter support

### Problem
`InMemoryCache._matches_filters()` does not check `date_from`/`date_to` fields from `PurlFilters`, while `PostgresCache._build_filter_sql()` does. This violates the `Storage` interface contract.

Although `InMemoryCache` is only used as a fallback when PostgreSQL is unavailable (making date filtering practically irrelevant), the fix ensures interface compliance.

### Solution
Add `date_from` and `date_to` checks to `_matches_filters()`:
```python
if filters.date_from and r.resolved_at:
    try:
        if date.fromisoformat(r.resolved_at[:10]) < filters.date_from:
            return False
    except (ValueError, TypeError):
        pass
if filters.date_to and r.resolved_at:
    try:
        if date.fromisoformat(r.resolved_at[:10]) >= filters.date_to:
            return False
    except (ValueError, TypeError):
        pass
```

### Files affected
- `src/purl_resolver/storage/inmemory.py` — add `from datetime import date`, extend `_matches_filters()`

### Testing
- Existing tests in `test_storage.py` remain passing
- No new test needed (date filter bug was silent; existing postgres tests cover the feature)

---

## Scope boundaries

- **Not included:** Full SRP refactoring of `PurlResolutionService` (high-severity issue #2) — deferred to separate session
- **Not included:** Broad `except Exception` cleanup (high-severity issue #3) — already fixed in previous session
- **Cancelled:** File size validation deduplication (issue #6) — 8-line duplication, insufficient value
- **Deferred to separate session:** All low-severity issues (#9–#13)

## Implementation order

1. SettingsStore cache — isolated change, trivially testable
2. Remove late imports — minimal change
3. InMemoryCache date filters — self-contained
4. SbomEnrichmentPipeline dependency consolidation — requires properties on `PurlResolutionService`, more coordination
