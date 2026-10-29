# High-Criticality Refactoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix three high-criticality architecture issues: `_RateLimitTracker` global state, broad `except Exception`, and duplicated URL validation logic.

**Architecture:** Three independent refactoring tasks applied sequentially. No behavioral changes. Each task preserves existing function signatures and passes existing tests.

**Tech Stack:** Python 3.12+, asyncio, pytest, httpx

## Global Constraints

- No changes to function signatures of exported functions (`validate_url`, `validate_url_with_retry`)
- No changes to storage layer or resolver chain behavior
- No new runtime dependencies
- All existing tests must pass after each task
- Changes to `tests/test_url_validator.py` only where necessary for API compatibility

---

### Task 1: Convert `_RateLimitTracker` from Class State to Instance State

**Files:**
- Modify: `src/purl_resolver/url_validator.py:82-108`
- Modify: `tests/test_url_validator.py:19-25,122-125`

**Interfaces:**
- Consumes: `url_validator.py` — current class-level `_RateLimitTracker`
- Produces: instance-level `_RateLimitTracker` with module-level singleton `_rate_limit_tracker`

- [ ] **Step 1: Rewrite `_RateLimitTracker` class**

Replace class-level `_count`/`_cooldown_until` with instance attributes. Add `asyncio.Lock`. Convert `@classmethod` methods to instance methods.

```python
class _RateLimitTracker:
    def __init__(self) -> None:
        self._count: int = 0
        self._cooldown_until: float = 0.0
        self._lock: asyncio.Lock = asyncio.Lock()

    async def is_in_cooldown(self) -> bool:
        async with self._lock:
            if self._cooldown_until > 0 and time.time() >= self._cooldown_until:
                logger.info("Rate limit cooldown expired")
                self._count = 0
                self._cooldown_until = 0.0
            return self._cooldown_until > 0 and time.time() < self._cooldown_until

    async def record_rate_limit(self) -> None:
        async with self._lock:
            self._count += 1
            if self._count >= _RATE_LIMIT_THRESHOLD:
                self._cooldown_until = time.time() + _RATE_LIMIT_COOLDOWN
                logger.warning(
                    "Rate limit threshold reached (%d consecutive), "
                    "entering %ds cooldown",
                    self._count, _RATE_LIMIT_COOLDOWN,
                )

    def reset(self) -> None:
        self._count = 0
        self._cooldown_until = 0.0

_rate_limit_tracker = _RateLimitTracker()
```

Add `import asyncio` at top of file if not already present (it is — line 3).

- [ ] **Step 2: Update `validate_url()` calls**

In `url_validator.py`, change four references from class-level to instance-level:

```python
# Line 376:
    if await _rate_limit_tracker.is_in_cooldown():
        return UrlValidationOutput(UrlValidationResult.RATE_LIMITED)

# Line 396:
        _rate_limit_tracker.reset()
        return UrlValidationOutput(UrlValidationResult.NETWORK_ERROR)

# Line 400:
        _rate_limit_tracker.record_rate_limit()

# Line 403:
    _rate_limit_tracker.reset()
```

- [ ] **Step 3: Update test fixture**

In `tests/test_url_validator.py`, change the autouse fixture:

```python
@pytest.fixture(autouse=True)
def reset_rate_limit_tracker():
    from purl_resolver.url_validator import _rate_limit_tracker
    _rate_limit_tracker.reset()
    yield
    _rate_limit_tracker.reset()
```

Remove the import of `_RateLimitTracker` from the import block at line 11 since tests no longer reference the class directly.

- [ ] **Step 4: Update cooldown test**

```python
# test_url_validator.py:122-127
async def test_rate_limit_cooldown_skips_validation(self):
    import time
    from purl_resolver.url_validator import _rate_limit_tracker
    _rate_limit_tracker._count = 5
    _rate_limit_tracker._cooldown_until = time.time() + 60
    result = await validate_url("https://github.com/psf/requests", timeout=5)
    assert result.result == UrlValidationResult.RATE_LIMITED
```

- [ ] **Step 5: Run tests**

```bash
.venv/bin/pytest tests/test_url_validator.py -v
```

Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/purl_resolver/url_validator.py tests/test_url_validator.py
git commit -m "fix(url-validator): make _RateLimitTracker instance-based with asyncio.Lock"
```

---

### Task 2: Narrow `except Exception` to Specific Types

**Files:**
- Modify: `src/purl_resolver/url_validator.py`
- Modify: `src/purl_resolver/purl_utils/__init__.py`
- Modify: `tests/test_url_validator.py`

**Interfaces:**
- Consumes: `url_validator.py` functions, `purl_utils/__init__.py` functions
- Produces: same functions with narrowed exception handlers

- [ ] **Step 1: Narrow `except` in `purl_utils/__init__.py:51`**

```python
def safe_normalize(purl: str) -> str:
    try:
        return normalize(validate(purl))
    except (ValueError, PurlValidationError):
        return purl
```

- [ ] **Step 2: Narrow `except` in `url_validator.py` — `_check_connectivity` (line 132)**

```python
    except httpx.RequestError:
        logger.warning("Connectivity probe to %s failed", _CONNECTIVITY_URL)
        return False
```

- [ ] **Step 3: Narrow `except` in VCS probes — `_git_probe` (line 185)**

```python
    except (OSError, asyncio.TimeoutError) as e:
        logger.warning("git ls-remote failed for %s: %s", url, e)
        return None
```

- [ ] **Step 4: Narrow `except` in `_svn_probe` (line 209)**

```python
    except (OSError, asyncio.TimeoutError) as e:
        logger.warning("svn ls failed for %s: %s", url, e)
        return None
```

- [ ] **Step 5: Narrow `except` in `_hg_probe` (line 233)**

```python
    except (OSError, asyncio.TimeoutError) as e:
        logger.warning("hg identify failed for %s: %s", url, e)
        return None
```

- [ ] **Step 6: Narrow `except` in `_fossil_probe_xfer` (line 275)**

Note: line 273 already catches `httpx.RequestError`. Change the outer catch at line 275:

```python
    except httpx.RequestError as e:
        logger.warning("Fossil xfer probe failed for %s: %s", url, e)
        return None
```

- [ ] **Step 7: Narrow `except` in `_fossil_probe_footer` (line 303)**

```python
    except httpx.RequestError as e:
        logger.warning("Fossil footer check failed for %s: %s", url, e)
        return None
```

- [ ] **Step 8: Narrow `except` in `validate_github_token` (line 363)**

```python
    except (httpx.RequestError, ConnectionError):
        return False
```

- [ ] **Step 9: Narrow `except` in `validate_url` — connectivity check (line 382)**

```python
    except (httpx.RequestError, ConnectionError, OSError):
        return UrlValidationOutput(UrlValidationResult.NETWORK_ERROR)
```

- [ ] **Step 10: Narrow `except` in `validate_url` — HEAD request (line 395)**

Keep the `_rate_limit_tracker.reset()`:

```python
    except httpx.RequestError:
        _rate_limit_tracker.reset()
        return UrlValidationOutput(UrlValidationResult.NETWORK_ERROR)
```

- [ ] **Step 11: Keep safety net on `_check_vcs` in `validate_url` (line 417)**

Add logging to the safety net:

```python
    except Exception:
        logger.warning("VCS check failed unexpectedly for %s", final_url, exc_info=True)
        return UrlValidationOutput(UrlValidationResult.NETWORK_ERROR, final_url=final_url)
```

- [ ] **Step 12: Update tests — replace `Exception` with `httpx.RequestError`**

In `tests/test_url_validator.py`, change two `side_effect = Exception(...)` to `side_effect = httpx.RequestError(...)`:

```python
# Line 88 (test_head_connection_error_returns_network_error):
            mock_head.side_effect = httpx.RequestError("Connection refused")

# Line 235 (test_network_error_returns_false):
            mock_head.side_effect = httpx.RequestError("Connection refused")
```

Add `import httpx` at the top of the test file.

- [ ] **Step 13: Run tests**

```bash
.venv/bin/pytest tests/ -v
```

Expected: All tests pass.

- [ ] **Step 14: Commit**

```bash
git add src/purl_resolver/url_validator.py src/purl_resolver/purl_utils/__init__.py tests/test_url_validator.py
git commit -m "fix: narrow except Exception to specific types in url_validator and purl_utils"
```

---

### Task 3: Extract `UrlValidationService` and Integrate

**Files:**
- Create: `src/purl_resolver/validation_service.py`
- Modify: `src/purl_resolver/service.py`
- Modify: `src/purl_resolver/sbom_enrichment.py`
- Modify: `src/purl_resolver/main.py`
- Modify: `tests/test_service_validation.py`
- Modify: `tests/test_sbom_integration.py`

**Interfaces:**
- Consumes: `validate_url_with_retry` from `url_validator.py`, `SettingsStore` from `settings_store.py`
- Produces: `UrlValidationService` class with single `async def validate_url(...)` method

- [ ] **Step 1: Create `src/purl_resolver/validation_service.py`**

```python
from __future__ import annotations

from .settings_store import SettingsStore
from .url_validator import validate_url_with_retry


class UrlValidationService:
    """Wraps validate_url_with_retry, injecting settings from SettingsStore."""

    def __init__(self, settings_store: SettingsStore) -> None:
        self._settings_store = settings_store

    async def validate_url(
        self,
        url: str,
        timeout: int,
        github_token: str | None = None,
        skip_connectivity_check: bool = False,
    ) -> UrlValidationOutput:
        return await validate_url_with_retry(
            url, timeout,
            github_token=github_token,
            settings_store=self._settings_store,
            skip_connectivity_check=skip_connectivity_check,
        )
```

Need to import `UrlValidationOutput`:
```python
from .url_validator import UrlValidationOutput, validate_url_with_retry
```

- [ ] **Step 2: Update `PurlResolutionService` in `service.py`**

Add `import` for `UrlValidationService`:
```python
from .validation_service import UrlValidationService
```

Change constructor to accept `validation_service` and remove `settings_store`:
```python
class PurlResolutionService:
    def __init__(
        self,
        storage: Storage,
        resolvers: list[Resolver],
        settings_store: SettingsStore | None = None,
        validation_service: UrlValidationService | None = None,
    ) -> None:
        self._storage = storage
        self._resolvers = resolvers
        self._settings_store = settings_store
        self._validation_service = validation_service
```

Note: keep `settings_store` parameter for backward compatibility with existing callers that pass it positionally. `validation_service` is optional — if None, the service falls back to direct function call (or we can construct from settings_store).

Extract `_is_within_cooldown`:
```python
def _is_within_cooldown(self, cached: ResolveResponse) -> bool:
    if self._settings_store is None:
        return True
    app_settings = self._settings_store.load()
    if not app_settings.validate_db_urls:
        return True
    cooldown_hours = app_settings.revalidation_cooldown_hours
    if cooldown_hours > 0 and cached.resolver in TRUSTED_RESOLVERS and cached.resolved_at:
        try:
            resolved_date = datetime.fromisoformat(cached.resolved_at)
            elapsed = datetime.now() - resolved_date
            if elapsed.total_seconds() < cooldown_hours * 3600:
                return True
        except (ValueError, TypeError):
            pass
    return False
```

Convert `_validate_cached_url` from `@staticmethod` to instance method:
```python
async def _validate_cached_url(
    self,
    cached: ResolveResponse,
    purl_key: str,
) -> ResolveResponse | None:
    if self._is_within_cooldown(cached):
        return cached

    app_settings = self._settings_store.load()
    github_token = app_settings.github_token

    if self._validation_service is not None:
        voutput = await self._validation_service.validate_url(
            cached.repository_url,
            app_settings.url_validation_timeout,
            github_token=github_token,
            skip_connectivity_check=True,
        )
    else:
        voutput = await validate_url_with_retry(
            cached.repository_url,
            app_settings.url_validation_timeout,
            github_token=github_token,
            settings_store=self._settings_store,
            skip_connectivity_check=True,
        )

    if voutput.result == UrlValidationResult.VALID:
        new_url = voutput.final_url or cached.repository_url
        if new_url != cached.repository_url:
            logger.info("Updated repository URL for %s: %s -> %s", purl_key, cached.repository_url, new_url)
            cached.repository_url = new_url
        try:
            await self._storage.store(cached)
        except Exception:
            logger.warning("Failed to update resolved_at for %s", purl_key, exc_info=True)
    elif voutput.result == UrlValidationResult.INVALID:
        try:
            await self._storage.delete_purls([purl_key])
        except Exception:
            logger.warning("Failed to delete invalid URL for %s", purl_key, exc_info=True)
        return None

    return cached
```

Change caller in `resolve_purl()`:
```python
# line 100-103:
                if self._is_within_cooldown(cached):
                    pass  # skip validation
                else:
                    cached = await self._validate_cached_url(cached, purl_key)
```

Wait, this is too verbose. Let me keep it clean. The original code:
```python
                cached = await self._validate_cached_url(
                    cached, self._settings_store, purl_key, self._storage,
                )
```

After the change:
```python
                cached = await self._validate_cached_url(cached, purl_key)
```

Update `resolve_purl()` inline validation (lines 126-147):
```python
            if self._settings_store is not None:
                app_settings = self._settings_store.load()
                if app_settings.validate_db_urls:
                    if self._validation_service is not None:
                        voutput = await self._validation_service.validate_url(
                            repo_url,
                            app_settings.url_validation_timeout,
                            github_token=app_settings.github_token,
                            skip_connectivity_check=True,
                        )
                    else:
                        voutput = await validate_url_with_retry(
                            repo_url,
                            app_settings.url_validation_timeout,
                            github_token=app_settings.github_token,
                            settings_store=self._settings_store,
                            skip_connectivity_check=True,
                        )
                    if voutput.result == UrlValidationResult.INVALID:
                        logger.warning(
                            "Resolver %s returned invalid URL %s for %s, skipping",
                            r.name, repo_url, purl,
                        )
                        continue
                    if voutput.result in (UrlValidationResult.NETWORK_ERROR, UrlValidationResult.RATE_LIMITED):
                        logger.warning(
                            "URL validation inconclusive for %s (resolver=%s, result=%s), accepting anyway",
                            repo_url, r.name, voutput.result.value,
                        )
                    repo_url = voutput.final_url or repo_url
```

- [ ] **Step 3: Update `SbomEnrichmentPipeline` in `sbom_enrichment.py`**

Add import:
```python
from .validation_service import UrlValidationService
```

Update constructor — accept optional `validation_service`:
```python
class SbomEnrichmentPipeline:
    def __init__(
        self,
        storage: Storage,
        resolvers: list[Resolver],
        resolution_service: PurlResolutionService,
        settings_store: SettingsStore | None = None,
        validation_service: UrlValidationService | None = None,
    ) -> None:
        self._storage = storage
        self._resolvers = resolvers
        self._settings_store = settings_store
        self._resolution_service = resolution_service
        self._validation_service = validation_service
```

Update the `validate_existing_refs` block in `process()` (lines 76-97):
```python
        if validate_existing_refs:
            app_settings = self._settings_store.load() if self._settings_store else None
            val_timeout = app_settings.url_validation_timeout if app_settings else 5
            val_token = app_settings.github_token if app_settings else None
            for comp in components:
                if comp.needs_enrichment:
                    continue
                for ref in comp.existing_references:
                    if ref.get("type") in SOURCE_REF_TYPES and ref.get("url"):
                        if self._validation_service is not None:
                            voutput = await self._validation_service.validate_url(
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
                                settings_store=self._settings_store,
                                skip_connectivity_check=True,
                            )
                        if voutput.result == UrlValidationResult.INVALID:
                            comp.needs_enrichment = True
                            comp.existing_references = []
                        elif voutput.final_url and voutput.final_url != ref["url"]:
                            ref["url"] = voutput.final_url
                        break
```

- [ ] **Step 4: Update `main.py` lifespan**

```python
from .validation_service import UrlValidationService

# Inside lifespan:
    app.state.validation_service = UrlValidationService(app.state.settings_store)
    app.state.resolution_service = PurlResolutionService(
        storage=app.state.storage,
        resolvers=app.state.resolvers,
        settings_store=app.state.settings_store,
        validation_service=app.state.validation_service,
    )
```

- [ ] **Step 5: Update tests in `test_service_validation.py`**

The test class `TestValidateCachedUrl` and `TestResolverBasedCooldown` currently call `PurlResolutionService._validate_cached_url` as a static method. Since it's now an instance method, update the calls to use an instance:

```python
class TestValidateCachedUrl:
    @pytest.mark.asyncio
    async def test_returns_cached_when_no_settings_store(self):
        cached = ResolveResponse(
            purl="pkg:pypi/requests",
            repository_url="https://github.com/psf/requests",
        )
        service = PurlResolutionService(AsyncMock(), [])
        result = await service._validate_cached_url(cached, "pkg:pypi/requests")
        assert result == cached

    @pytest.mark.asyncio
    async def test_returns_cached_when_validation_disabled(self):
        cached = ResolveResponse(
            purl="pkg:pypi/requests",
            repository_url="https://github.com/psf/requests",
        )
        settings_store = MagicMock()
        settings_store.load.return_value = MagicMock(validate_db_urls=False)
        service = PurlResolutionService(AsyncMock(), [], settings_store=settings_store)
        result = await service._validate_cached_url(cached, "pkg:pypi/requests")
        assert result == cached
```

Apply the same pattern to all 10+ tests in `TestValidateCachedUrl` and `TestResolverBasedCooldown`:
- Create `PurlResolutionService(AsyncMock(), [], settings_store=settings_store)` or similar
- Call `await service._validate_cached_url(cached, purl_key)` instead of `PurlResolutionService._validate_cached_url(cached, settings_store, purl_key, storage)`
- Remove `storage` parameter from test assertions (storage is now `self._storage` from the service)

The `TestResolverBasedCooldown` class tests remain the same pattern but create `PurlResolutionService` with a real `AsyncMock()` storage internally.

- [ ] **Step 6: Update tests in `test_sbom_integration.py`**

In the `client` fixture (line 29-32), pass `validation_service` to `PurlResolutionService`:

```python
    test_app.state.validation_service = UrlValidationService(None)  # will be set properly
    test_app.state.resolution_service = PurlResolutionService(
        storage=test_app.state.storage,
        resolvers=test_app.state.resolvers,
        validation_service=test_app.state.validation_service,
    )
```

Wait, `UrlValidationService.__init__` requires `settings_store`. In the `client` fixture, there's no `settings_store`... Let me check. The current fixture creates `PurlResolutionService(storage=..., resolvers=...)` without `settings_store`. So `validation_service` should be optional — if not provided, fall back to direct `validate_url_with_retry` call. That's already handled in the design above by checking `self._validation_service is not None`.

So in the `client` fixture, we just don't pass `validation_service` — same as before. No change needed to `test_sbom_integration.py`.

- [ ] **Step 7: Run all tests**

```bash
.venv/bin/pytest tests/ -v
```

Expected: All tests pass.

- [ ] **Step 8: Commit**

```bash
git add src/purl_resolver/validation_service.py src/purl_resolver/service.py src/purl_resolver/sbom_enrichment.py src/purl_resolver/main.py tests/test_service_validation.py tests/test_sbom_integration.py
git commit -m "feat: extract UrlValidationService, integrate into PurlResolutionService and SbomEnrichmentPipeline"
```