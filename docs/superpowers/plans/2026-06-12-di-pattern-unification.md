# DI Pattern Unification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert `src/purl_resolver/service.py` from free functions (parameter bag anti-pattern) to `PurlResolutionService` class with constructor injection, unifying the DI pattern across the project.

**Architecture:** New `PurlResolutionService` class encapsulates `storage`, `resolvers`, `settings_store` in `__init__`. Free functions become bridge wrappers during transition. Route handlers and `SbomEnrichmentPipeline` receive the service via `app.state.resolution_service`. Bridge removed after all call sites migrated.

**Tech Stack:** Python 3.12, FastAPI, pytest (asyncio_mode=auto)

---

### Task 1: Create `PurlResolutionService` class with bridge wrappers

**Files:**
- Modify: `src/purl_resolver/service.py`

- [ ] **Step 1: Add `PurlResolutionService` class before the existing free functions**

Insert at line ~17, after `_BATCH_SEMAPHORE_LIMIT` and before `_validate_cached_url`:

```python
class PurlResolutionService:
    def __init__(
        self,
        storage: Storage,
        resolvers: list[Resolver],
        settings_store: SettingsStore | None = None,
    ) -> None:
        self._storage = storage
        self._resolvers = resolvers
        self._settings_store = settings_store

    @staticmethod
    async def _validate_cached_url(
        cached: ResolveResponse,
        settings_store: SettingsStore | None,
        purl_key: str,
        storage: Storage,
    ) -> ResolveResponse | None:
        """Keep existing logic unchanged - accessible via self._validate_cached_url(...)"""
        if settings_store is None:
            return cached

        app_settings = settings_store.load()
        if not app_settings.validate_db_urls:
            return cached

        cooldown_hours = app_settings.revalidation_cooldown_hours
        if cooldown_hours > 0 and cached.resolver in TRUSTED_RESOLVERS and cached.resolved_at:
            try:
                resolved_date = datetime.fromisoformat(cached.resolved_at)
                elapsed = datetime.now() - resolved_date
                if elapsed.total_seconds() < cooldown_hours * 3600:
                    return cached
            except (ValueError, TypeError):
                pass

        github_token = app_settings.github_token
        vresult = await validate_url_with_retry(
            cached.repository_url,
            app_settings.url_validation_timeout,
            github_token=github_token,
            settings_store=settings_store,
            skip_connectivity_check=True,
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

    async def resolve_purl(
        self,
        purl: str,
        resolver: str = "",
    ) -> ResolveResult:
        try:
            components = validate(purl)
        except Exception as e:
            return ResolveResult.err(400, "invalid_purl", str(e))

        purl_key = normalize(components)

        try:
            cached = await self._storage.lookup(purl_key)
            if cached is not None:
                logger.info("Cache hit for %s", purl_key)
                cached = await self._validate_cached_url(cached, self._settings_store, purl_key, self._storage)
            if cached is not None:
                cached.found_by = "local_db"
                return ResolveResult.ok(cached)
        except Exception:
            logger.warning(
                "Cache lookup failed for %s, falling through to resolver",
                purl_key,
                exc_info=True,
            )

        for r in self._resolvers:
            try:
                resolution = await r.resolve(purl)
            except InvalidPurlError as e:
                return ResolveResult.err(400, "invalid_purl", str(e))
            except UpstreamError as e:
                return ResolveResult.err(502, "upstream_error", str(e))

            if resolution.repository_url is None:
                continue

            repo_url = resolution.repository_url

            if self._settings_store is not None:
                app_settings = self._settings_store.load()
                if app_settings.validate_db_urls:
                    vresult = await validate_url_with_retry(
                        repo_url,
                        app_settings.url_validation_timeout,
                        github_token=app_settings.github_token,
                        settings_store=self._settings_store,
                        skip_connectivity_check=True,
                    )
                    if vresult == UrlValidationResult.INVALID:
                        logger.warning(
                            "Resolver %s returned invalid URL %s for %s, skipping",
                            r.name, repo_url, purl,
                        )
                        continue
                    if vresult in (UrlValidationResult.NETWORK_ERROR, UrlValidationResult.RATE_LIMITED):
                        logger.warning(
                            "URL validation inconclusive for %s (resolver=%s, result=%s), accepting anyway",
                            repo_url, r.name, vresult,
                        )

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

            try:
                await self._storage.store(response)
                logger.info("Stored result for %s", purl_key)
            except Exception:
                logger.warning("Failed to store result for %s", purl_key, exc_info=True)

            return ResolveResult.ok(response)

        return ResolveResult.ok(
            ResolveResponse(
                purl=purl_key,
                warnings=["No resolver found a repository URL"],
            )
        )

    async def resolve_batch(
        self,
        purls: list[str],
        resolver: str = "",
    ) -> dict[str, ResolveResponse]:
        semaphore = asyncio.Semaphore(_BATCH_SEMAPHORE_LIMIT)

        async def _resolve_one(original: str) -> tuple[str, ResolveResponse | None]:
            async with semaphore:
                result = await self.resolve_purl(original, resolver=resolver)
                key = safe_normalize(original)
                if result.response and result.response.repository_url:
                    return (key, result.response)
                return (key, None)

        tasks = [_resolve_one(p) for p in purls]
        results = await asyncio.gather(*tasks)
        return {k: v for k, v in results if v is not None}

    async def store_preexisting_references(
        self,
        components: list[SbomComponent],
        resolver: str = "",
    ) -> None:
        for comp in components:
            if comp.needs_enrichment:
                continue
            for ref in comp.existing_references:
                if ref.get("type") == "vcs" and ref.get("url"):
                    purl_key = safe_normalize(comp.purl)
                    try:
                        existing = await self._storage.lookup(purl_key)
                    except Exception:
                        existing = None
                    if existing is None:
                        await self._storage.store(ResolveResponse(
                            purl=purl_key,
                            repository_url=ref["url"],
                            evidence=["from SBOM externalReferences"],
                            resolver=resolver,
                        ))
                    break
```

- [ ] **Step 2: Replace existing free functions with bridge wrappers**

Replace the existing `_validate_cached_url` function body with delegation to the static method (it stays as a module-level alias for backward compatibility):

```python
async def _validate_cached_url(
    cached: ResolveResponse,
    settings_store: SettingsStore | None,
    purl_key: str,
    storage: Storage,
) -> ResolveResponse | None:
    return await PurlResolutionService._validate_cached_url(cached, settings_store, purl_key, storage)
```

Replace the existing `resolve_purl` function body with:

```python
async def resolve_purl(
    purl: str,
    storage: Storage,
    resolvers: list[Resolver],
    settings_store: SettingsStore | None = None,
    resolver: str = "",
) -> ResolveResult:
    svc = PurlResolutionService(storage, resolvers, settings_store)
    return await svc.resolve_purl(purl, resolver=resolver)
```

Replace the existing `resolve_batch` function body with:

```python
async def resolve_batch(
    purls: list[str],
    storage: Storage,
    resolvers: list[Resolver],
    settings_store: SettingsStore | None = None,
    resolver: str = "",
) -> dict[str, ResolveResponse]:
    svc = PurlResolutionService(storage, resolvers, settings_store)
    return await svc.resolve_batch(purls, resolver=resolver)
```

Replace the existing `store_preexisting_references` function body with:

```python
async def store_preexisting_references(
    components: list[SbomComponent],
    storage: Storage,
    resolver: str = "",
) -> None:
    svc = PurlResolutionService(storage, [], None)
    return await svc.store_preexisting_references(components, resolver=resolver)
```

- [ ] **Step 3: Verify tests still pass via bridge**

Run: `.venv/bin/pytest tests/ -x --tb=short`
Expected: All tests PASS (bridge functions delegate to the class)

- [ ] **Step 4: Commit**

```bash
git add src/purl_resolver/service.py
git commit -m "refactor: add PurlResolutionService class with bridge wrappers for backward compat"
```

---

### Task 2: Composition Root (main.py)

**Files:**
- Modify: `src/purl_resolver/main.py`

- [ ] **Step 1: Import and instantiate `PurlResolutionService`**

Add import after `from .router import router` (line 15):

```python
from .service import PurlResolutionService
```

After `app.state.db_admin_service = DbAdminService(app.state.storage)` (line 40), add:

```python
    app.state.resolution_service = PurlResolutionService(
        storage=app.state.storage,
        resolvers=app.state.resolvers,
        settings_store=app.state.settings_store,
    )
```

- [ ] **Step 2: Run tests to verify no breakage**

Run: `.venv/bin/pytest tests/ -x --tb=short`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add src/purl_resolver/main.py
git commit -m "refactor: add PurlResolutionService to composition root in lifespan"
```

---

### Task 3: Route handlers (routes/resolve.py)

**Files:**
- Modify: `src/purl_resolver/routes/resolve.py`

- [ ] **Step 1: Update imports**

Remove `from ..service import resolve_purl` (line 12).

- [ ] **Step 2: Update `resolve_endpoint` to use `resolution_service`**

Replace lines 28-33:

```python
    result = await resolve_purl(
        purl=body.purl,
        storage=request.app.state.storage,
        resolvers=request.app.state.resolvers,
        settings_store=request.app.state.settings_store,
    )
```

With:

```python
    result = await request.app.state.resolution_service.resolve_purl(purl=body.purl)
```

- [ ] **Step 3: Pass `resolution_service` to `SbomEnrichmentPipeline`**

Replace the `pipeline = SbomEnrichmentPipeline(...)` block (lines 86-90):

```python
    pipeline = SbomEnrichmentPipeline(
        storage=request.app.state.storage,
        resolvers=request.app.state.resolvers,
        settings_store=getattr(request.app.state, "settings_store", None),
        resolution_service=request.app.state.resolution_service,
    )
```

- [ ] **Step 4: Run tests to verify no breakage**

Run: `.venv/bin/pytest tests/ -x --tb=short`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/purl_resolver/routes/resolve.py
git commit -m "refactor: use PurlResolutionService in route handlers"
```

---

### Task 4: SbomEnrichmentPipeline (sbom_enrichment.py)

**Files:**
- Modify: `src/purl_resolver/sbom_enrichment.py`

- [ ] **Step 1: Update imports**

Replace:

```python
from .service import resolve_batch, store_preexisting_references
```

With:

```python
from .service import PurlResolutionService
```

- [ ] **Step 2: Add `resolution_service` to `SbomEnrichmentPipeline.__init__`**

Change `__init__` signature (lines 52-60):

```python
    def __init__(
        self,
        storage: Storage,
        resolvers: list[Resolver],
        settings_store: SettingsStore | None = None,
        resolution_service: PurlResolutionService | None = None,
    ) -> None:
        self._storage = storage
        self._resolvers = resolvers
        self._settings_store = settings_store
        self._resolution_service = resolution_service
```

- [ ] **Step 3: Replace calls in `process()` method**

Replace lines 119-128:

```python
        resolved = await resolve_batch(
            unique_purls,
            self._storage,
            self._resolvers,
            settings_store=self._settings_store,
            resolver="import-sbom",
        )
        await store_preexisting_references(
            components, self._storage, resolver="import-sbom"
        )
```

With:

```python
        if self._resolution_service is not None:
            resolved = await self._resolution_service.resolve_batch(
                unique_purls,
                resolver="import-sbom",
            )
            await self._resolution_service.store_preexisting_references(
                components, resolver="import-sbom"
            )
        else:
            from .service import resolve_batch, store_preexisting_references
            resolved = await resolve_batch(
                unique_purls,
                self._storage,
                self._resolvers,
                settings_store=self._settings_store,
                resolver="import-sbom",
            )
            await store_preexisting_references(
                components, self._storage, resolver="import-sbom"
            )
```

- [ ] **Step 4: Run tests to verify no breakage**

Run: `.venv/bin/pytest tests/ -x --tb=short`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/purl_resolver/sbom_enrichment.py
git commit -m "refactor: add PurlResolutionService DI to SbomEnrichmentPipeline"
```

---

### Task 5: Update tests — source files that now pass resolution_service

**Files:**
- Modify: `tests/test_sbom_integration.py`

- [ ] **Step 1: Update `client()` fixture and relevant test to use `resolution_service`**

In `tests/test_sbom_integration.py`, after the existing `client()` fixture (line 20-27), `resolution_service` is already set because `main.py` creates it. But `test_sbom_integration.py` creates its own `FastAPI` with `test_app`, bypassing `main.py`. The fixture already calls `test_app.state.storage = InMemoryCache()` and `test_app.state.resolvers = [Purl2RepoResolver()]`.

Add `resolution_service` to the `client()` fixture, after `test_app.state.resolvers = [Purl2RepoResolver()]`:

```python
    from purl_resolver.service import PurlResolutionService
    test_app.state.resolution_service = PurlResolutionService(
        storage=test_app.state.storage,
        resolvers=test_app.state.resolvers,
    )
```

- [ ] **Step 2: Update the existing test that directly imports `resolve_batch`**

Replace `from purl_resolver.service import resolve_batch` with:

```python
from purl_resolver.service import PurlResolutionService, resolve_batch
```

In `test_resolve_batch_deletes_file_url_entry` (line 401), update the import — `resolve_batch` is still available via bridge, so this test continues to work. No change needed for this test.

For `test_sbom_pipeline_deletes_file_url_entry` (line 435), update pipeline creation to pass `resolution_service`:

```python
        pipeline = SbomEnrichmentPipeline(
            storage=storage_with_file_url,
            resolvers=fake_empty_resolvers,
            settings_store=settings_store_with_validation,
            resolution_service=PurlResolutionService(storage_with_file_url, fake_empty_resolvers, settings_store_with_validation),
        )
```
Note: After Task 7, `resolution_service` becomes a required parameter. This update ensures the test continues to work.

- [ ] **Step 3: Run tests**

Run: `.venv/bin/pytest tests/ -x --tb=short`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_sbom_integration.py
git commit -m "test: update sbom_integration tests for PurlResolutionService"
```

---

### Task 6: Update all remaining test call sites to use `PurlResolutionService`

**Files:**
- Modify: `tests/test_storage.py`
- Modify: `tests/test_service_validation.py`
- Modify: `tests/test_resolve_batch.py`
- Modify: `tests/test_db_admin.py`
- Modify: `tests/test_librariesio_integration.py`

- [ ] **Step 1: Update `test_storage.py` — replace bridge calls**

Change import (line 7):

```python
from purl_resolver.service import PurlResolutionService, resolve_purl
```

Replace every `resolve_purl(purl, storage, resolvers)` call with `PurlResolutionService(storage, resolvers).resolve_purl(purl)`:

Line 77-78:
```python
        result = await resolve_purl(
            "pkg:pypi/requests@2.31.0", storage, [resolver]
        )
```
→
```python
        result = await PurlResolutionService(storage, [resolver]).resolve_purl(
            "pkg:pypi/requests@2.31.0"
        )
```

Same pattern for lines 97-98, 119-121, 153-155, 181-183, 198-199, 212-213, 225-226, 242-244, 264-266.

After all changes, `resolve_purl` import can be removed:

```python
from purl_resolver.service import PurlResolutionService
```

- [ ] **Step 2: Update `test_resolve_batch.py` — replace bridge calls**

Change import (line 6):

```python
from purl_resolver.service import PurlResolutionService, resolve_batch
```

Replace every `resolve_batch(purls, storage, resolvers)` call with `PurlResolutionService(storage, resolvers).resolve_batch(purls)`:

Lines 34:
```python
        result = await resolve_batch(purls, storage, [resolver])
```
→
```python
        result = await PurlResolutionService(storage, [resolver]).resolve_batch(purls)
```

Same pattern for lines 48, 60, 67, 80, 95.

After all changes, remove `resolve_batch` import if no longer needed:

```python
from purl_resolver.service import PurlResolutionService
```

- [ ] **Step 3: Update `test_service_validation.py` — replace bridge calls**

Change import (line 9) to use `PurlResolutionService._validate_cached_url` directly:

```python
from purl_resolver.service import PurlResolutionService
```

Note: `resolve_purl` import is removed — all resolve_purl calls use `PurlResolutionService(...).resolve_purl(...)`. `_validate_cached_url` is accessed via `PurlResolutionService._validate_cached_url(...)` (Python allows access to `@staticmethod` with single underscore).

Replace every `_validate_cached_url(...)` call with `PurlResolutionService._validate_cached_url(...)`:

Lines 25:
```python
        with patch("purl_resolver.service._validate_cached_url", new_callable=AsyncMock, return_value=cached):
```
→
```python
        with patch.object(PurlResolutionService, "_validate_cached_url", new_callable=AsyncMock, return_value=cached):
```

Line 198 and every subsequent `await _validate_cached_url(...)`:
```python
        result = await _validate_cached_url(cached, None, "pkg:pypi/requests", AsyncMock())
```
→
```python
        result = await PurlResolutionService._validate_cached_url(cached, None, "pkg:pypi/requests", AsyncMock())
```

Same pattern for all `_validate_cached_url` call sites in this file.

Replace every `resolve_purl(...)` call with `PurlResolutionService(...).resolve_purl(...)`:

Lines 26-28 (and all others following same pattern):
```python
            result = await resolve_purl(
                "pkg:pypi/requests@2.31.0", mock_storage, [resolver], mock_settings_store
            )
```
→
```python
            result = await PurlResolutionService(mock_storage, [resolver], mock_settings_store).resolve_purl(
                "pkg:pypi/requests@2.31.0"
            )
```

Same pattern for lines 37-39, 91, 103-104, 114-115, 126-127, 139, 154, 164, 180, 498, 525, 549, 575, 601.

`_validate_cached_url` module-level alias is NOT kept — tests use `PurlResolutionService._validate_cached_url(...)` directly.

- [ ] **Step 4: Update `test_db_admin.py` — replace bridge calls**

Lines 355-369 — replace:

```python
        from purl_resolver.service import resolve_batch, store_preexisting_references
        ...
        await resolve_batch(purls_to_resolve, storage, [resolver])
        await store_preexisting_references(components, storage)
```

With:

```python
        from purl_resolver.service import PurlResolutionService
        svc = PurlResolutionService(storage, [resolver])
        ...
        await svc.resolve_batch(purls_to_resolve)
        await svc.store_preexisting_references(components)
```

- [ ] **Step 5: Update `test_librariesio_integration.py` — replace bridge calls**

Change import (line 11):

```python
from purl_resolver.service import PurlResolutionService, resolve_purl
```

Replace every `resolve_purl(purl, storage, resolvers)` with `PurlResolutionService(storage, resolvers).resolve_purl(purl)`:

Lines 42-46:
```python
        result = await resolve_purl(
            "pkg:pypi/requests@2.31.0",
            storage,
            resolvers,
        )
```
→
```python
        result = await PurlResolutionService(storage, resolvers).resolve_purl(
            "pkg:pypi/requests@2.31.0",
        )
```

Same pattern for lines 71-75 and 100-104.

After all changes, resolve:
```python
from purl_resolver.service import PurlResolutionService
```

- [ ] **Step 6: Run full test suite**

Run: `.venv/bin/pytest tests/ -x --tb=short`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add tests/test_storage.py tests/test_service_validation.py tests/test_resolve_batch.py tests/test_db_admin.py tests/test_librariesio_integration.py
git commit -m "test: update test call sites to use PurlResolutionService directly"
```

---

### Task 7: Remove bridge functions and cleanup fallbacks

**Files:**
- Modify: `src/purl_resolver/service.py`
- Modify: `src/purl_resolver/sbom_enrichment.py`

- [ ] **Step 1: Remove bridge wrappers from `service.py`**

Remove these functions (now unused):
- `resolve_purl(purl, storage, resolvers, settings_store, resolver)` — bridge body
- `resolve_batch(purls, storage, resolvers, settings_store, resolver)` — bridge body
- `store_preexisting_references(components, storage, resolver)` — bridge body
- `_validate_cached_url(...)` — module-level alias

The file now exports only `PurlResolutionService` class and module-level constants (`TRUSTED_RESOLVERS`, `_BATCH_SEMAPHORE_LIMIT`).

- [ ] **Step 2: Remove `resolution_service` fallback from `sbom_enrichment.py`**

In `SbomEnrichmentPipeline.__init__`, make `resolution_service` required (remove `None` default):

```python
        resolution_service: PurlResolutionService,
```

In `process()`, remove the `if self._resolution_service is not None:` conditional and the `else` fallback. Keep only the `if` branch body without the condition:

```python
        resolved = await self._resolution_service.resolve_batch(
            unique_purls,
            resolver="import-sbom",
        )
        await self._resolution_service.store_preexisting_references(
            components, resolver="import-sbom"
        )
```

- [ ] **Step 3: Run full test suite**

Run: `.venv/bin/pytest tests/ -x --tb=short`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add src/purl_resolver/service.py src/purl_resolver/sbom_enrichment.py
git commit -m "refactor: remove bridge functions and sbom_enrichment fallback"
```
```

---

### Task 8: Update specs

**Files:**
- Modify: `specs/architecture/layers.md`
- Modify: `specs/domains/purl-resolution.md`

- [ ] **Step 1: Update `layers.md` Service Layer section**

In the Layer Diagram, update Service Layer block to show `PurlResolutionService` class:

```
|  |  Service Layer              |                   |
|  |  src/purl_resolver/service  |                   |
|  |                             |                   |
|  |  PurlResolutionService      |                   |
|  |    .resolve_purl()          |                   |
|  |    .resolve_batch()         |                   |
|  |    .store_preexisting_refs()|                   |
```

In Import Rules, update line 177:
```
- **Service Layer** imports **PURL Utils Layer** (`purl_utils/`), **Storage Layer** (`storage/interface.py`), **Resolver Layer** (`resolver/interface.py`), **URL Validator** (`url_validator.py`), and **SBOM Module** (`sbom/`); exports `PurlResolutionService` class with constructor injection; dependencies (`storage`, `resolvers`, `settings_store`) are declared once in `__init__` instead of passed to every method
```

In Layer Responsibilities, update `service.py` section (line 203):
```
### Service Layer (`service.py`)
- `PurlResolutionService` class with constructor injection (`storage`, `resolvers`, `settings_store`)
- Orchestrate single resolution flow (`resolve_purl`): ...
- Batch resolution (`resolve_batch`): ...
- Store pre-existing references (`store_preexisting_references`): ...
```

- [ ] **Step 2: Update `purl-resolution.md`**

Update references to service layer functions to use class-based notation.

- [ ] **Step 3: Commit**

```bash
git add specs/architecture/layers.md specs/domains/purl-resolution.md
git commit -m "docs: update specs with PurlResolutionService class"
```

---

### Task 9: Full test suite and lint

- [ ] **Step 1: Run all tests**

Run: `.venv/bin/pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 2: Run lint**

Run: `.venv/bin/ruff check src/ tests/`
Expected: No errors

- [ ] **Step 3: Final commit if any fixes needed**

```bash
git add -A
git commit -m "chore: post-implementation fixes after full test suite run"
```