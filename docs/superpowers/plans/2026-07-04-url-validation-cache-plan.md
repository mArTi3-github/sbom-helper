# URL Validation Cache Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a DiskCache-backed UrlValidationCache to deduplicate URL validation across resolution cache hits, SBOM existing-ref validation, and fresh resolver results.

**Architecture:** A new `UrlValidationCache` class wraps `diskcache.Cache`, storing `url → validated_at` timestamps. `UrlValidationService` accepts the cache as a constructor dependency and checks it before performing full validation via HTTP HEAD + VCS probes. The `validate_existing_refs` per-request flag moves from the SBOM form to a persistent `validate_sbom_refs` setting.

**Tech Stack:** Python 3.11+, diskcache 5.x, existing async httpx/url_validator, DiskCache (SQLite-backed file cache).

## Global Constraints

- `diskcache>=5.0.0` added to `pyproject.toml` dependencies
- `UrlValidationCache` must not import from any `purl_resolver` module
- All existing tests must pass after refactoring; `_is_within_cooldown()` and `_validate_cached_url()` are removed
- `validate_sbom_refs` defaults to `False`
- `found_by = "local_db"` in API responses unchanged
- Docker volume: `./data/url_cache/:/app/data/url_cache/`
- Log messages: "Resolution cache hit" (PostgreSQL), "Validation cache hit/miss" (DiskCache)

---
### Task 1: UrlValidationCache module + dependency + tests

**Files:**
- Create: `src/purl_resolver/url_validation_cache.py`
- Create: `tests/test_url_validation_cache.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Add diskcache to pyproject.toml**

```toml
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.34.0",
    "pydantic-settings>=2.7.0",
    "purl2repo>=2.0.0",
    "asyncpg>=0.30.0",
    "packageurl-python>=0.17.0",
    "python-multipart>=0.0.20",
    "diskcache>=5.0.0",
]
```

- [ ] **Step 2: Install dependency**

```bash
cd /home/administrator/Desktop/projects/sbom-helper && .venv/bin/pip install diskcache
```

- [ ] **Step 3: Create url_validation_cache.py**

`src/purl_resolver/url_validation_cache.py`:
```python
from __future__ import annotations

import time
import logging
from diskcache import Cache

logger = logging.getLogger(__name__)


class UrlValidationCache:
    def __init__(self, cache_dir: str) -> None:
        self._cache = Cache(cache_dir)

    def get(self, url: str, max_age_seconds: int) -> str | None:
        raw = self._cache.get(url, default=None)
        if raw is None:
            return None
        if time.time() - raw > max_age_seconds:
            return None
        return url

    def put(self, url: str) -> None:
        self._cache.set(url, time.time())

    def expire(self, max_age_seconds: int) -> None:
        cutoff = time.time() - max_age_seconds
        for key in list(self._cache):
            val = self._cache.get(key)
            if val is not None and val < cutoff:
                del self._cache[key]

    def clear(self) -> None:
        self._cache.clear()
```

- [ ] **Step 4: Create test_url_validation_cache.py**

```python
from __future__ import annotations

import time
import tempfile
import pytest
from purl_resolver.url_validation_cache import UrlValidationCache


@pytest.fixture
def cache():
    tmpdir = tempfile.mkdtemp()
    c = UrlValidationCache(tmpdir)
    yield c
    c.clear()


class TestUrlValidationCache:
    def test_get_miss_before_put(self, cache):
        assert cache.get("https://example.com", max_age_seconds=3600) is None

    def test_get_hit_within_ttl(self, cache):
        cache.put("https://example.com")
        assert cache.get("https://example.com", max_age_seconds=3600) == "https://example.com"

    def test_get_miss_after_ttl(self, cache):
        cache.put("https://example.com")
        time.sleep(0.01)
        assert cache.get("https://example.com", max_age_seconds=0) is None

    def test_get_miss_different_url(self, cache):
        cache.put("https://example.com")
        assert cache.get("https://other.com", max_age_seconds=3600) is None

    def test_expire_removes_old_entries(self, cache):
        cache.put("https://old.com")
        cache.put("https://new.com")
        time.sleep(0.01)
        cache.expire(max_age_seconds=0.005)
        assert cache.get("https://old.com", max_age_seconds=3600) is None
        assert cache.get("https://new.com", max_age_seconds=3600) == "https://new.com"

    def test_expire_preserves_young_entries(self, cache):
        cache.put("https://example.com")
        cache.expire(max_age_seconds=3600)
        assert cache.get("https://example.com", max_age_seconds=3600) == "https://example.com"

    def test_clear_removes_all_entries(self, cache):
        cache.put("https://a.com")
        cache.put("https://b.com")
        cache.clear()
        assert cache.get("https://a.com", 3600) is None
        assert cache.get("https://b.com", 3600) is None

    def test_put_refreshes_timestamp(self, cache):
        cache.put("https://example.com")
        time.sleep(0.01)
        cache.put("https://example.com")
        assert cache.get("https://example.com", max_age_seconds=0.005) == "https://example.com"

    def test_persistence_across_instances(self, cache):
        cache.put("https://persist.com")
        dirpath = cache._cache.directory
        cache2 = UrlValidationCache(dirpath)
        assert cache2.get("https://persist.com", max_age_seconds=3600) == "https://persist.com"
        cache2.clear()
```

- [ ] **Step 5: Run tests**

```bash
cd /home/administrator/Desktop/projects/sbom-helper && .venv/bin/python -m pytest tests/test_url_validation_cache.py -v
```

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/purl_resolver/url_validation_cache.py tests/test_url_validation_cache.py && git commit -m "feat: add UrlValidationCache with diskcache"
```

---
### Task 2: Backend integration — UrlValidationService, service.py, sbom_enrichment.py, main.py

**Files:**
- Modify: `src/purl_resolver/validation_service.py`
- Modify: `src/purl_resolver/service.py`
- Modify: `src/purl_resolver/sbom_enrichment.py`
- Modify: `src/purl_resolver/routes/resolve.py`
- Modify: `src/purl_resolver/main.py`
- Test: `tests/test_service_validation.py`

- [ ] **Step 1: Update UrlValidationService**

Replace `src/purl_resolver/validation_service.py`:

```python
from __future__ import annotations

import logging

from .settings_store import SettingsStore
from .url_validator import UrlValidationOutput, UrlValidationResult, validate_url_with_retry
from .url_validation_cache import UrlValidationCache

logger = logging.getLogger(__name__)


class UrlValidationService:
    def __init__(self, settings_store: SettingsStore, cache: UrlValidationCache) -> None:
        self._settings_store = settings_store
        self._cache = cache

    async def validate_url(
        self,
        url: str,
        timeout: int,
        github_token: str | None = None,
    ) -> UrlValidationOutput:
        app_settings = self._settings_store.load()
        if app_settings.validate_db_urls:
            max_age = app_settings.revalidation_cooldown_hours * 3600
            cached = self._cache.get(url, max_age)
            if cached is not None:
                logger.debug("Validation cache hit for %s", url)
                return UrlValidationOutput(UrlValidationResult.VALID, final_url=None)

        logger.debug("Validation cache miss for %s, performing full validation", url)
        voutput = await validate_url_with_retry(
            url, timeout,
            github_token=github_token,
            settings_store=self._settings_store,
        )

        if voutput.result == UrlValidationResult.VALID and app_settings.validate_db_urls:
            logger.debug("Cached validation result for %s", url)
            self._cache.put(url)

        return voutput

    def clear_cache(self) -> None:
        self._cache.clear()
```

- [ ] **Step 2: Update service.py — remove cooldown/validate_cached_url, add _validate_stored_url, update resolve_purl**

In `src/purl_resolver/service.py`:

1. Change the import line 13 — remove `validate_url_with_retry`:
```python
from .url_validator import UrlValidationOutput, UrlValidationResult
```

2. Remove line 18 (`TRUSTED_RESOLVERS` constant).

3. Remove methods `_is_within_cooldown()` (lines 44-59) and `_validate_cached_url()` (lines 61-102).

4. Add new method `_validate_stored_url` (insert where `_validate_cached_url` was):

```python
async def _validate_stored_url(
    self,
    cached: ResolveResponse,
    purl_key: str,
) -> ResolveResponse | None:
    if self._validation_service is None:
        return cached
    app_settings = self._settings_store.load()
    if not app_settings.validate_db_urls:
        return cached

    voutput = await self._validation_service.validate_url(
        cached.repository_url,
        app_settings.url_validation_timeout,
        github_token=app_settings.github_token,
    )

    if voutput.result == UrlValidationResult.VALID:
        new_url = voutput.final_url or cached.repository_url
        if new_url != cached.repository_url:
            logger.info("Updated repository URL for %s: %s -> %s", purl_key, cached.repository_url, new_url)
            cached.repository_url = new_url
        try:
            await self._storage.store(cached)
        except Exception:
            logger.warning("Failed to update stored URL for %s", purl_key, exc_info=True)
        return cached

    if voutput.result == UrlValidationResult.INVALID:
        logger.warning("Cached URL %s is invalid for %s, deleting", cached.repository_url, purl_key)
        try:
            await self._storage.delete_purls([purl_key])
        except Exception:
            logger.warning("Failed to delete invalid cached URL for %s", purl_key, exc_info=True)
        return None

    return cached  # NETWORK_ERROR / RATE_LIMITED — keep
```

5. Update the cache-hit section in `resolve_purl()` (lines 117-123):
```python
try:
    cached = await self._storage.lookup(purl_key)
    if cached is not None:
        logger.info("Resolution cache hit for %s", purl_key)
        validated = await self._validate_stored_url(cached, purl_key)
        if validated is not None:
            validated.found_by = "local_db"
            return ResolveResult.ok(validated)
except Exception:
    logger.warning(
        "Resolution cache lookup failed for %s, falling through to resolver",
        purl_key,
        exc_info=True,
    )
```

6. Update the fresh resolver URL validation block (lines 144-171):
```python
if self._validation_service is not None:
    app_settings = self._settings_store.load()
    if app_settings.validate_db_urls:
        voutput = await self._validation_service.validate_url(
            repo_url,
            app_settings.url_validation_timeout,
            github_token=app_settings.github_token,
        )
        if voutput.result == UrlValidationResult.INVALID:
            logger.warning(
                "URL %s from resolver %s is invalid, skipping",
                repo_url, r.name,
            )
            continue
        if voutput.result in (UrlValidationResult.NETWORK_ERROR, UrlValidationResult.RATE_LIMITED):
            logger.warning(
                "URL validation inconclusive for %s (resolver=%s, result=%s), accepting anyway",
                repo_url, r.name, voutput.result.value,
            )
        repo_url = voutput.final_url or repo_url
```

- [ ] **Step 3: Update sbom_enrichment.py**

Remove `validate_existing_refs` parameter from `SbomEnrichmentPipeline.process()`. Read `validate_sbom_refs` from settings instead:

Change method signature (lines 56-61):
```python
async def process(
    self,
    sbom_data: dict,
    remove_unresolved_no_subcomponents: bool = False,
    ignore_patterns: list[dict[str, str]] | None = None,
) -> SbomEnrichmentResult:
```

Replace `if validate_existing_refs:` block (lines 67-94):
```python
settings = self._resolution_service.settings_store
if settings and settings.load().validate_sbom_refs:
    app_settings = settings.load()
    val_timeout = app_settings.url_validation_timeout
    val_token = app_settings.github_token
    for comp in components:
        if comp.needs_enrichment:
            continue
        for ref in comp.existing_references:
            if ref.get("type") in SOURCE_REF_TYPES and ref.get("url"):
                vs = self._resolution_service.validation_service
                if vs is not None:
                    voutput = await vs.validate_url(ref["url"], timeout=val_timeout, github_token=val_token)
                else:
                    voutput = await validate_url_with_retry(
                        ref["url"], timeout=val_timeout, github_token=val_token,
                    )
                if voutput.result == UrlValidationResult.INVALID:
                    comp.needs_enrichment = True
                    comp.existing_references = []
                elif voutput.final_url and voutput.final_url != ref["url"]:
                    ref["url"] = voutput.final_url
                break
```

- [ ] **Step 4: Update routes/resolve.py**

Remove `validate_existing_refs: bool = Form(False)` from `resolve_sbom_endpoint()` parameters (line 48). Update the pipeline call (line 99):

```python
result = await pipeline.process(
    data,
    remove_unresolved_no_subcomponents=remove_unresolved_no_subcomponents,
    ignore_patterns=parsed_patterns,
)
```

- [ ] **Step 5: Update main.py — create cache, inject, background task**

Add import at the top:
```python
from .url_validation_cache import UrlValidationCache
```

Replace the wiring section (lines 51-64) and add background task inside `lifespan()`:

```python
app.state.settings_store = SettingsStore()
app.state.ignore_patterns_store = IgnorePatternsStore()

app_settings = app.state.settings_store.load()
logging.basicConfig(level=app_settings.log_level_as_int(), force=True)

VALIDATION_CACHE_DIR = "/app/data/url_cache"
validation_cache = UrlValidationCache(VALIDATION_CACHE_DIR)
app.state.validation_cache = validation_cache

app.state.resolvers = build_resolvers(settings, app_settings)
app.state.db_admin_service = DbAdminService(app.state.storage)
app.state.validation_service = UrlValidationService(app.state.settings_store, validation_cache)
app.state.resolution_service = PurlResolutionService(
    storage=app.state.storage,
    resolvers=app.state.resolvers,
    settings_store=app.state.settings_store,
    validation_service=app.state.validation_service,
)

spa_dir = pathlib.Path("/app/frontend/dist")
if spa_dir.is_dir():
    app.mount("/", SPAStaticFiles(directory=str(spa_dir), html=True), name="spa")
    logger.info("Serving SPA from %s", spa_dir)
else:
    logger.warning("No SPA directory found — frontend will not be served")

logger.info("Configured %d resolver(s)", len(app.state.resolvers))

async def _expire_url_cache():
    while True:
        await asyncio.sleep(86400)
        current_settings = app.state.settings_store.load()
        max_age = current_settings.revalidation_cooldown_hours * 3600
        app.state.validation_cache.expire(max_age)

expire_task = asyncio.create_task(_expire_url_cache())

try:
    yield
finally:
    expire_task.cancel()
    if pool is not None:
        await pool.close()
```

- [ ] **Step 6: Update tests/test_service_validation.py**

Add import:
```python
from purl_resolver.validation_service import UrlValidationService
```

Add fixture `mock_validation_service` (after `mock_settings_store`):
```python
@pytest.fixture
def mock_validation_service(mock_settings_store):
    vs = AsyncMock(spec=UrlValidationService)
    vs.validate_url.return_value = _url_output(UrlValidationResult.VALID)
    return vs
```

Update `mock_settings_store` fixture — add `validate_sbom_refs`:
```python
settings = MagicMock(
    validate_db_urls=True, validate_sbom_refs=False,
    url_validation_timeout=5, revalidation_cooldown_hours=24,
)
```

Update `TestFoundBy.test_found_by_local_db_when_cached` — patch `_validate_stored_url` instead of `_validate_cached_url`:
```python
async def test_found_by_local_db_when_cached(self, mock_storage, mock_settings_store, resolver):
    from datetime import datetime
    cached = ResolveResponse(
        purl="pkg:pypi/requests",
        repository_url="https://github.com/psf/requests",
        resolver="purl2repo",
        resolved_at=datetime.now().isoformat(),
    )
    mock_storage.lookup = AsyncMock(return_value=cached)
    with patch.object(PurlResolutionService, "_validate_stored_url", new_callable=AsyncMock, return_value=cached):
        result = await PurlResolutionService(mock_storage, [resolver], mock_settings_store).resolve_purl(
            "pkg:pypi/requests@2.31.0"
        )
    assert result.response is not None
    assert result.response.found_by == "local_db"
    assert result.response.resolver == "purl2repo"
```

Update `TestValidationIntegration` — all tests need `validation_service=mock_validation_service` and patch `UrlValidationService.validate_url` instead of `validate_url_with_retry`. Key examples:

```python
class TestValidationIntegration:
    @pytest.mark.asyncio
    async def test_valid_url_updates_resolved_at(self, mock_storage, mock_settings_store, mock_validation_service):
        mock_storage.lookup.return_value = _cached_response(days_ago=3)
        mock_validation_service.validate_url.return_value = _url_output(UrlValidationResult.VALID)
        result = await PurlResolutionService(
            mock_storage, [],
            settings_store=mock_settings_store,
            validation_service=mock_validation_service,
        ).resolve_purl("pkg:pypi/requests")
        assert result.response is not None
        mock_storage.store.assert_called_once()
        mock_storage.delete_purls.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_url_deletes_and_falls_through(self, mock_storage, mock_settings_store, mock_validation_service, resolver):
        mock_storage.lookup.return_value = _cached_response(days_ago=3)
        mock_validation_service.validate_url.return_value = _url_output(UrlValidationResult.INVALID)
        await PurlResolutionService(
            mock_storage, [resolver],
            settings_store=mock_settings_store,
            validation_service=mock_validation_service,
        ).resolve_purl("pkg:pypi/requests")
        mock_storage.delete_purls.assert_called_once_with(["pkg:pypi/requests"])
        resolver.resolve.assert_called_once()

    @pytest.mark.asyncio
    async def test_network_error_returns_cached(self, mock_storage, mock_settings_store, mock_validation_service):
        mock_storage.lookup.return_value = _cached_response(days_ago=3)
        mock_validation_service.validate_url.return_value = _url_output(UrlValidationResult.NETWORK_ERROR)
        result = await PurlResolutionService(
            mock_storage, [],
            settings_store=mock_settings_store,
            validation_service=mock_validation_service,
        ).resolve_purl("pkg:pypi/requests")
        assert result.response is not None
        mock_storage.store.assert_not_called()
        mock_storage.delete_purls.assert_not_called()

    @pytest.mark.asyncio
    async def test_rate_limited_returns_cached(self, mock_storage, mock_settings_store, mock_validation_service):
        mock_storage.lookup.return_value = _cached_response(days_ago=3)
        mock_validation_service.validate_url.return_value = _url_output(UrlValidationResult.RATE_LIMITED)
        result = await PurlResolutionService(
            mock_storage, [],
            settings_store=mock_settings_store,
            validation_service=mock_validation_service,
        ).resolve_purl("pkg:pypi/requests")
        assert result.response is not None
        mock_storage.store.assert_not_called()

    @pytest.mark.asyncio
    async def test_validate_db_urls_false_skips_validation(self, mock_storage):
        mock_storage.lookup.return_value = _cached_response(days_ago=3)
        settings_store = MagicMock()
        settings_store.load = MagicMock(return_value=MagicMock(validate_db_urls=False))
        result = await PurlResolutionService(
            mock_storage, [],
            settings_store=settings_store,
            validation_service=None,
        ).resolve_purl("pkg:pypi/requests")
        assert result.response is not None
```

Remove tests that reference `_is_within_cooldown()`:
- `test_trusted_resolver_within_cooldown_integration` (lines 166-184)
- Entire `class TestCachedUrlValidation` and its nested `class TestCooldownBasedRevalidation` (lines 424-541)

Replace with new `TestValidateStoredUrl`:

```python
class TestValidateStoredUrl:
    """Tests for _validate_stored_url — replaces old _validate_cached_url + cooldown tests."""

    @pytest.mark.asyncio
    async def test_valid_url_returns_cached(self):
        cached = _cached_response(days_ago=3)
        service = PurlResolutionService(
            storage=AsyncMock(), resolvers=[],
            settings_store=MagicMock(),
            validation_service=AsyncMock(spec=UrlValidationService),
        )
        service._validation_service.validate_url.return_value = _url_output(UrlValidationResult.VALID)
        result = await service._validate_stored_url(cached, "pkg:pypi/requests")
        assert result is cached

    @pytest.mark.asyncio
    async def test_invalid_url_deletes_cached(self):
        cached = _cached_response(days_ago=3)
        storage = AsyncMock()
        storage.delete_purls = AsyncMock(return_value=1)
        service = PurlResolutionService(
            storage=storage, resolvers=[],
            settings_store=MagicMock(),
            validation_service=AsyncMock(spec=UrlValidationService),
        )
        service._validation_service.validate_url.return_value = _url_output(UrlValidationResult.INVALID)
        result = await service._validate_stored_url(cached, "pkg:pypi/requests")
        assert result is None
        storage.delete_purls.assert_called_once_with(["pkg:pypi/requests"])

    @pytest.mark.asyncio
    async def test_network_error_keeps_cached(self):
        cached = _cached_response(days_ago=3)
        storage = AsyncMock()
        service = PurlResolutionService(
            storage=storage, resolvers=[],
            settings_store=MagicMock(),
            validation_service=AsyncMock(spec=UrlValidationService),
        )
        service._validation_service.validate_url.return_value = _url_output(UrlValidationResult.NETWORK_ERROR)
        result = await service._validate_stored_url(cached, "pkg:pypi/requests")
        assert result is cached
        storage.delete_purls.assert_not_called()

    @pytest.mark.asyncio
    async def test_validate_db_urls_false_returns_cached_immediately(self):
        cached = _cached_response(days_ago=3)
        settings_store = MagicMock()
        settings_store.load = MagicMock(return_value=MagicMock(validate_db_urls=False))
        service = PurlResolutionService(
            storage=AsyncMock(), resolvers=[],
            settings_store=settings_store,
            validation_service=AsyncMock(spec=UrlValidationService),
        )
        result = await service._validate_stored_url(cached, "pkg:pypi/requests")
        assert result is cached
        service._validation_service.validate_url.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_validation_service_returns_cached(self):
        cached = _cached_response(days_ago=3)
        service = PurlResolutionService(
            storage=AsyncMock(), resolvers=[],
            settings_store=MagicMock(),
            validation_service=None,
        )
        result = await service._validate_stored_url(cached, "pkg:pypi/requests")
        assert result is cached

    @pytest.mark.asyncio
    async def test_redirect_updates_repository_url_and_stores(self):
        cached = _cached_response(days_ago=3)
        cached.repository_url = "https://old-url.com/repo"
        storage = AsyncMock()
        service = PurlResolutionService(
            storage=storage, resolvers=[],
            settings_store=MagicMock(),
            validation_service=AsyncMock(spec=UrlValidationService),
        )
        service._validation_service.validate_url.return_value = _url_output(
            UrlValidationResult.VALID, final_url="https://new-url.com/repo"
        )
        result = await service._validate_stored_url(cached, "pkg:pypi/requests")
        assert result is cached
        assert cached.repository_url == "https://new-url.com/repo"
        storage.store.assert_called_once()
```

Update remaining tests: replace any remaining patches of `"purl_resolver.service.validate_url_with_retry"` with `"purl_resolver.validation_service.UrlValidationService.validate_url"`.

Run tests after changes:
```bash
cd /home/administrator/Desktop/projects/sbom-helper && .venv/bin/python -m pytest tests/test_service_validation.py -v
```

- [ ] **Step 7: Commit**

```bash
git add src/purl_resolver/validation_service.py src/purl_resolver/service.py src/purl_resolver/sbom_enrichment.py src/purl_resolver/routes/resolve.py src/purl_resolver/main.py tests/test_service_validation.py && git commit -m "feat: integrate UrlValidationCache into backend"
```

---
### Task 3: Settings backend — AppSettings, routes/settings.py, Docker volume

**Files:**
- Modify: `src/purl_resolver/settings_store.py`
- Modify: `src/purl_resolver/routes/settings.py`
- Modify: `docker-compose.yml`

- [ ] **Step 1: Add validate_sbom_refs to AppSettings**

In `src/purl_resolver/settings_store.py`, add after `validate_db_urls`:
```python
validate_db_urls: bool = False
validate_sbom_refs: bool = False
url_validation_timeout: int = Field(default=5, ge=1, le=60)
```

- [ ] **Step 2: Update SettingsUpdate in routes/settings.py**

Add after `validate_db_urls`:
```python
validate_db_urls: bool | None = None
validate_sbom_refs: bool | None = None
url_validation_timeout: int | None = Field(None, ge=1, le=60)
```

- [ ] **Step 3: Update GET /api/v1/settings response**

Add `"validate_sbom_refs"` to the response dict (around line 68):
```python
"validate_sbom_refs": app_settings.validate_sbom_refs,
```

- [ ] **Step 4: Update PATCH /api/v1/settings response**

Add `"validate_sbom_refs"` to the response dict (around line 133):
```python
"validate_sbom_refs": updated.validate_sbom_refs,
```

- [ ] **Step 5: Add clear-validation-cache endpoint**

Add to `src/purl_resolver/routes/settings.py`:
```python
@router.post("/api/v1/settings/clear-validation-cache")
async def clear_validation_cache(request: Request) -> JSONResponse:
    from ..validation_service import UrlValidationService
    vs: UrlValidationService = request.app.state.validation_service
    vs.clear_cache()
    return JSONResponse(status_code=200, content={"status": "ok"})
```

- [ ] **Step 6: Update docker-compose.yml**

Add the volume mount:
```yaml
volumes:
  - ./data/postgres/:/var/lib/postgresql/data/
  - ./data/url_cache/:/app/data/url_cache/
  - ./data/settings.json:/app/data/settings.json
```

- [ ] **Step 7: Run tests to verify no regressions**

```bash
cd /home/administrator/Desktop/projects/sbom-helper && .venv/bin/python -m pytest tests/ -v --ignore=tests/test_url_validation_cache.py
```

- [ ] **Step 8: Commit**

```bash
git add src/purl_resolver/settings_store.py src/purl_resolver/routes/settings.py docker-compose.yml && git commit -m "feat: add validate_sbom_refs setting and clear-validation-cache endpoint"
```

---
### Task 4: Frontend — Settings.vue, SbomUpdater.vue, API types

**Files:**
- Modify: `frontend/src/views/Settings.vue`
- Modify: `frontend/src/views/SbomUpdater.vue`
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/api/settings.ts`

- [ ] **Step 1: Update API types**

Add `validate_sbom_refs: boolean` to both `SettingsResponse` and `SettingsUpdate` interfaces in `frontend/src/types/api.ts`.

- [ ] **Step 2: Update API module**

Add to `frontend/src/api/settings.ts`:
```typescript
export function clearValidationCache(): Promise<{ status: string }> {
  return apiFetch('/api/v1/settings/clear-validation-cache', { method: 'POST' })
}
```

- [ ] **Step 3: Update Settings.vue**

In the "URL Validation" card, after the `validate_db_urls` toggle, add:

```html
<div class="setting-row">
  <div>
    <div class="setting-label">Validate pre-existing URLs from SBOM</div>
    <div class="setting-desc">
      When enabled, existing VCS and source-distribution URLs found in SBOM
      files are verified before enrichment. Invalid URLs trigger re-resolution
      of the component.
    </div>
  </div>
  <label class="toggle">
    <input type="checkbox" v-model="validateSbomRefs" @change="debouncedAutoSave({ validate_sbom_refs: validateSbomRefs })">
    <span class="toggle-slider"></span>
  </label>
</div>
```

After the `revalidation_cooldown_hours` row, add:

```html
<div class="setting-row info-row">
  <div class="setting-desc">
    URLs returned by resolvers are always validated before being returned.
    Validation results are cached and reused across all contexts
    (local database, SBOM enrichment) within the configured cooldown period.
  </div>
</div>
<div class="setting-row">
  <div>
    <div class="setting-label">Clear validation cache</div>
    <div class="setting-desc">
      Remove all cached URL validation results. The next validation for each
      URL will perform a full check.
    </div>
  </div>
  <button class="btn-secondary" @click="onClearValidationCache">Clear cache</button>
</div>
```

In the `<script>` section:
- Add `const validateSbomRefs = ref(false)` to the refs declaration
- Add `async function onClearValidationCache() { ... }` that calls `clearValidationCache()` API
- Map `settings.validate_sbom_refs` to `validateSbomRefs.value` in the settings fetch logic

- [ ] **Step 4: Update SbomUpdater.vue**

Remove lines 13-16 (the `validateRefs` checkbox):
```html
<label class="checkbox-row">
  <input type="checkbox" v-model="validateRefs" />
  <span>Проверять существующие VCS-ссылки в SBOM</span>
</label>
```

Remove the `validateRefs` ref and its usage in the `resolveSbom()` call parameters.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/Settings.vue frontend/src/views/SbomUpdater.vue frontend/src/types/api.ts frontend/src/api/settings.ts && git commit -m "feat: update frontend for validation cache settings"
```