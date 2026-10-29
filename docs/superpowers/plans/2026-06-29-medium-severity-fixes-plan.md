# Medium-Severity Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 4 medium-severity architectural issues: SettingsStore I/O, SbomEnrichmentPipeline dead deps, circular import smell, InMemoryCache missing date filters.

**Architecture:** Each fix is independent and testable. Task order: isolated changes first (cache, imports, date filters), then coordinated change (pipeline consolidation).

**Tech Stack:** Python 3.12+, fastapi, pydantic

## Global Constraints

- All changes must preserve existing public API signatures (no breaking changes)
- Existing tests must pass without modification
- Follow project naming conventions (private methods use `_` prefix, async for I/O)

---

### Task 1: Add instance cache to SettingsStore

**Files:**
- Modify: `src/purl_resolver/settings_store.py`
- Test: `tests/test_settings_store.py`

**Interfaces:**
- Consumes: `SettingsStore` (existing class)
- Produces: `SettingsStore.load()` caches result, `SettingsStore.save()` invalidates cache

- [ ] **Step 1: Write the failing test**

Add to `tests/test_settings_store.py`, at the end of the file:

```python
class TestSettingsStoreCache:

    def test_load_returns_cached_value_after_first_read(self, store: SettingsStore, tmp_settings_file: Path):
        import json
        tmp_settings_file.write_text(json.dumps({"validate_db_urls": True}))
        first = store.load()
        assert first.validate_db_urls is True

        tmp_settings_file.write_text(json.dumps({"validate_db_urls": False}))
        second = store.load()
        assert second.validate_db_urls is True, "Should return cached value, not re-read file"

    def test_save_invalidates_cache(self, store: SettingsStore, tmp_settings_file: Path):
        import json
        tmp_settings_file.write_text(json.dumps({"validate_db_urls": True}))
        first = store.load()
        assert first.validate_db_urls is True

        store.save(AppSettings(validate_db_urls=False))
        second = store.load()
        assert second.validate_db_urls is False, "Should re-read file after save"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
source .venv/bin/activate && python -m pytest tests/test_settings_store.py::TestSettingsStoreCache -v
```
Expected: Both tests fail — first test incorrectly re-reads file, second test doesn't invalidate.

- [ ] **Step 3: Implement cache in SettingsStore**

Edit `src/purl_resolver/settings_store.py`:

```python
class SettingsStore:

    def __init__(self, path: str | Path | None = None) -> None:
        if path is None:
            path = os.environ.get("SETTINGS_FILE", "./data/settings.json")
        self._path = Path(path)
        self._cached: AppSettings | None = None

    def load(self) -> AppSettings:
        if self._cached is not None:
            return self._cached
        if not self._path.exists():
            self._ensure_parent()
            defaults = AppSettings()
            self._write(defaults)
            self._cached = defaults
            return defaults

        try:
            raw = self._path.read_text(encoding="utf-8")
            data = json.loads(raw)
            self._cached = AppSettings(**data)
            return self._cached
        except json.JSONDecodeError as exc:
            logger.warning("Corrupt settings file at %s, using defaults: %s", self._path, exc)
            self._cached = AppSettings()
            return self._cached

    def save(self, settings: AppSettings) -> None:
        self._cached = None
        self._ensure_parent()
        self._write(settings)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
source .venv/bin/activate && python -m pytest tests/test_settings_store.py -v
```
Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/purl_resolver/settings_store.py tests/test_settings_store.py
git commit -m "fix: add instance cache to SettingsStore to avoid redundant file I/O"
```

---

### Task 2: Remove late imports in `_rebuild_resolvers`

**Files:**
- Modify: `src/purl_resolver/routes/settings.py`

**Interfaces:**
- Consumes: `_rebuild_resolvers` function (existing)
- Produces: Same function with top-level imports

- [ ] **Step 1: Verify the import chain has no cycle**

```bash
source .venv/bin/activate && python -c "from purl_resolver.config import settings; from purl_resolver.resolver.factory import build_resolvers; print('OK')"
```
Expected: Prints "OK"

- [ ] **Step 2: Move imports to top level in settings.py**

Edit `src/purl_resolver/routes/settings.py`. Add these two imports to the existing top-level imports block:

```python
from ..config import settings
from ..resolver.factory import build_resolvers
```

Then remove the two late imports from the function body in `_rebuild_resolvers()`:

```python
def _rebuild_resolvers(request: Request) -> None:
    store: SettingsStore = request.app.state.settings_store
    app_settings = store.load()
    request.app.state.resolvers = build_resolvers(settings, app_settings)
```

- [ ] **Step 3: Verify imports work at module load time**

```bash
source .venv/bin/activate && python -c "from purl_resolver.routes.settings import _rebuild_resolvers; print('OK')"
```
Expected: Prints "OK" (no ImportError)

- [ ] **Step 4: Run existing tests to verify no regression**

```bash
source .venv/bin/activate && python -m pytest tests/test_api.py -v
```
Expected: Tests involving settings endpoint (`/api/v1/settings`) pass.

- [ ] **Step 5: Commit**

```bash
git add src/purl_resolver/routes/settings.py
git commit -m "fix: remove late imports from _rebuild_resolvers (no circular dep exists)"
```

---

### Task 3: Add date filter support to InMemoryCache

**Files:**
- Modify: `src/purl_resolver/storage/inmemory.py`

**Interfaces:**
- Consumes: `PurlFilters.date_from`, `PurlFilters.date_to` (already defined in `storage/interface.py`)
- Produces: `InMemoryCache._matches_filters()` now respects `date_from`/`date_to`

- [ ] **Step 1: Add `date` import and extend filter logic**

Edit `src/purl_resolver/storage/inmemory.py`:

Add import at the top:
```python
from datetime import date
```

Replace `_matches_filters` method:

```python
def _matches_filters(
    self, r: ResolveResponse, filters: PurlFilters
) -> bool:
    if filters.search and filters.search.lower() not in r.purl.lower():
        return False
    if filters.resolver and filters.resolver != (r.resolver or ""):
        return False
    if filters.confidence and filters.confidence != r.confidence:
        return False
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
    return True
```

- [ ] **Step 2: Run existing tests to verify no regression**

```bash
source .venv/bin/activate && python -m pytest tests/test_storage.py -v
```
Expected: All tests pass.

- [ ] **Step 3: Commit**

```bash
git add src/purl_resolver/storage/inmemory.py
git commit -m "fix: add date_from/date_to filtering to InMemoryCache._matches_filters"
```

---

### Task 4: Consolidate SbomEnrichmentPipeline dependencies

**Files:**
- Modify: `src/purl_resolver/service.py`
- Modify: `src/purl_resolver/sbom_enrichment.py`
- Modify: `src/purl_resolver/routes/resolve.py`

**Interfaces:**
- Consumes: `PurlResolutionService` (existing class), `SbomEnrichmentPipeline` (existing class)
- Produces: `PurlResolutionService.settings_store` property, `PurlResolutionService.validation_service` property; `SbomEnrichmentPipeline` with simplified constructor

- [ ] **Step 1: Add read-only properties to PurlResolutionService**

Edit `src/purl_resolver/service.py`. Add these properties after `__init__`:

```python
@property
def settings_store(self) -> SettingsStore | None:
    return self._settings_store

@property
def validation_service(self) -> UrlValidationService | None:
    return self._validation_service
```

- [ ] **Step 2: Simplify SbomEnrichmentPipeline constructor**

Edit `src/purl_resolver/sbom_enrichment.py`. Change constructor:

```python
class SbomEnrichmentPipeline:
    """Orchestrates the full CycloneDX SBOM enrichment workflow."""

    def __init__(
        self,
        resolution_service: PurlResolutionService,
    ) -> None:
        self._resolution_service = resolution_service

    async def process(
        self,
        sbom_data: dict,
        remove_unresolved_no_subcomponents: bool = False,
        validate_existing_refs: bool = False,
        ignore_patterns: list[dict[str, str]] | None = None,
    ) -> SbomEnrichmentResult:
        """Parse, collect, deduplicate, resolve, enrich, and report."""
        CycloneDXParser.parse(sbom_data)

        components = collect_components(sbom_data)

        if validate_existing_refs:
            app_settings = self._resolution_service.settings_store.load() if self._resolution_service.settings_store else None
            val_timeout = app_settings.url_validation_timeout if app_settings else 5
            val_token = app_settings.github_token if app_settings else None
            for comp in components:
                if comp.needs_enrichment:
                    continue
                for ref in comp.existing_references:
                    if ref.get("type") in SOURCE_REF_TYPES and ref.get("url"):
                        if self._resolution_service.validation_service is not None:
                            voutput = await self._resolution_service.validation_service.validate_url(
                                ref["url"],
                                timeout=val_timeout,
                                github_token=val_token,
                                skip_connectivity_check=True,
                            )
                        else:
                            voutput = await validate_url_with_retry(
                                ref["url"],
                                timeout=val_timeout,
                                github_token=val_token,
                                settings_store=self._resolution_service.settings_store,
                                skip_connectivity_check=True,
                            )
                        if voutput.result == UrlValidationResult.INVALID:
                            comp.needs_enrichment = True
                            comp.existing_references = []
                        elif voutput.final_url and voutput.final_url != ref["url"]:
                            ref["url"] = voutput.final_url
                        break

        # --- remainder of process() stays identical ---
```

The rest of `process()` method (lines 110-153) stays unchanged.

Now remove unused imports from `sbom_enrichment.py`:
- Remove: `from .resolver.interface import Resolver`
- Remove: `from .storage.interface import Storage`
- Remove: `from .settings_store import SettingsStore`
- Remove: `from .validation_service import UrlValidationService`

- [ ] **Step 3: Update pipeline construction in routes/resolve.py**

Edit `src/purl_resolver/routes/resolve.py`, replace lines 80-85:

Before:
```python
    pipeline = SbomEnrichmentPipeline(
        storage=request.app.state.storage,
        resolvers=request.app.state.resolvers,
        settings_store=getattr(request.app.state, "settings_store", None),
        resolution_service=request.app.state.resolution_service,
    )
```

After:
```python
    pipeline = SbomEnrichmentPipeline(
        resolution_service=request.app.state.resolution_service,
    )
```

- [ ] **Step 4: Run tests**

```bash
source .venv/bin/activate && python -m pytest tests/ -v
```
Expected: All existing tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/purl_resolver/service.py src/purl_resolver/sbom_enrichment.py src/purl_resolver/routes/resolve.py
git commit -m "refactor: consolidate SbomEnrichmentPipeline deps, remove dead params"
```