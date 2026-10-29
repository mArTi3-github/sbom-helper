# HTTP Redirect Resolution for URL Validation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** HTTP redirects (3xx) in URL validation pipeline are followed and the final URL is captured, used for `git ls-remote`, stored in cache, returned to users, and written into enriched SBOMs.

**Architecture:** Introduce `UrlValidationOutput` dataclass as return type for `validate_url()` and `validate_url_with_retry()`. Change `_git_ls_remote()` to receive the resolved final URL. Update three consumers in `service.py` and `sbom_enrichment.py` to use the final URL.

**Tech Stack:** Python 3.12+, httpx (with `follow_redirects=True`), asyncio, pytest with `pytest-asyncio`

## Global Constraints

- `validate_url()` and `validate_url_with_retry()` must never raise — always return `UrlValidationOutput`
- `final_url` is `str(resp.url)` from httpx response; equals the input URL when no redirect occurred
- `final_url` is `None` only when HEAD request wasn't executed (scheme error, rate-limit cooldown, connectivity failure, HEAD exception)
- `_git_ls_remote()` receives the resolved final URL, not the original
- Cache entries updated with final URL only on `VALID` result
- SBOM references updated with final URL on any non-INVALID result
- Fresh resolver results use final URL for any non-INVALID result

---

### Task 1: `UrlValidationOutput` dataclass + `validate_url()` changes

**Files:**
- Modify: `src/purl_resolver/url_validator.py:20-196`
- Test: `tests/test_url_validator.py:7-15, 27-125`

**Interfaces:**
- Produces: `UrlValidationOutput(result: UrlValidationResult, final_url: str | None = None)` dataclass
- Produces: `validate_url()` returns `UrlValidationOutput` instead of `UrlValidationResult`
- Consumes: `_head_request()` — httpx response with `.url` attribute
- Consumes: `_git_ls_remote()` — called with `final_url` instead of input `url`

- [ ] **Step 1: Write failing tests for `validate_url()` new return type + redirect capture**

In `test_url_validator.py`:
- Update import to also import `UrlValidationOutput`
- Add `resp.url` attribute to `_mock_response()` helper: `resp.url = "https://github.com/psf/requests"` (the input URL when no redirect)
- Add test for redirect capture:
```python
def test_validate_url_returns_url_validation_output(self):
    assert hasattr(UrlValidationOutput, "result")
    assert hasattr(UrlValidationOutput, "final_url")

@pytest.mark.asyncio
async def test_captures_final_url(self):
    with patch("purl_resolver.url_validator._check_connectivity", new_callable=AsyncMock, return_value=True), \
         patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head, \
         patch("purl_resolver.url_validator._git_ls_remote", new_callable=AsyncMock, return_value=True):
        mock_resp = _mock_head(200)
        mock_resp.url = "https://github.com/psf/requests"
        mock_head.return_value = mock_resp
        output = await validate_url("https://github.com/psf/requests", timeout=5)
        assert output.result == UrlValidationResult.VALID
        assert output.final_url == "https://github.com/psf/requests"

@pytest.mark.asyncio
async def test_captures_redirect_target(self):
    with patch("purl_resolver.url_validator._check_connectivity", new_callable=AsyncMock, return_value=True), \
         patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head, \
         patch("purl_resolver.url_validator._git_ls_remote", new_callable=AsyncMock, return_value=True):
        mock_resp = _mock_head(200)
        mock_resp.url = "https://github.com/psf/requests"
        mock_head.return_value = mock_resp
        with patch("purl_resolver.url_validator._git_ls_remote", new_callable=AsyncMock) as mock_git:
            mock_git.return_value = True
            output = await validate_url("https://old-url.com/psf/requests", timeout=5)
            assert output.result == UrlValidationResult.VALID
            assert output.final_url == "https://github.com/psf/requests"
            mock_git.assert_called_once_with("https://github.com/psf/requests", 5, github_token=None)

@pytest.mark.asyncio
async def test_final_url_none_when_head_not_executed(self):
    result = await validate_url("file:///usr/src/app/ptaf-task-mgr", timeout=5)
    assert result.result == UrlValidationResult.INVALID
    assert result.final_url is None
```

Update existing tests to access `.result` on the output:
```python
# Before: assert result == UrlValidationResult.VALID
# After:
output = await validate_url(...)
assert output.result == UrlValidationResult.VALID
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_url_validator.py -v 2>&1 | head -60`
Expected: FAIL — `UrlValidationOutput` not defined, type mismatch in assertions

- [ ] **Step 3: Add `UrlValidationOutput` dataclass and implement `validate_url()` changes**

In `url_validator.py`:
```python
from dataclasses import dataclass

@dataclass
class UrlValidationOutput:
    result: UrlValidationResult
    final_url: str | None = None
```

Change `validate_url()`:
```python
async def validate_url(
    url: str,
    timeout: int,
    github_token: str | None = None,
    skip_connectivity_check: bool = False,
) -> UrlValidationOutput:
    if not url.startswith(("http://", "https://")):
        return UrlValidationOutput(UrlValidationResult.INVALID)

    if _RateLimitTracker.is_in_cooldown():
        return UrlValidationOutput(UrlValidationResult.RATE_LIMITED)

    if not skip_connectivity_check:
        try:
            github_ok = await _check_connectivity(github_token=github_token)
        except Exception:
            return UrlValidationOutput(UrlValidationResult.NETWORK_ERROR)

        if not github_ok:
            return UrlValidationOutput(UrlValidationResult.NETWORK_ERROR)

    try:
        resp = await _head_request(url, timeout, github_token=github_token)
        final_url = str(resp.url)
        headers = dict(resp.headers)
        status = resp.status_code
    except Exception:
        _RateLimitTracker.reset()
        return UrlValidationOutput(UrlValidationResult.NETWORK_ERROR)

    if _is_rate_limited(status, headers):
        _RateLimitTracker.record_rate_limit()
        return UrlValidationOutput(UrlValidationResult.RATE_LIMITED, final_url=final_url)

    _RateLimitTracker.reset()

    if status in (401, 403) and github_token:
        return UrlValidationOutput(UrlValidationResult.TOKEN_INVALID, final_url=final_url)

    if status in (404, 405):
        return UrlValidationOutput(UrlValidationResult.INVALID, final_url=final_url)
    if status == 403:
        return UrlValidationOutput(UrlValidationResult.INVALID, final_url=final_url)
    if status >= 400:
        return UrlValidationOutput(UrlValidationResult.INVALID, final_url=final_url)

    try:
        git_result = await _git_ls_remote(final_url, timeout, github_token=github_token)
    except Exception:
        return UrlValidationOutput(UrlValidationResult.NETWORK_ERROR, final_url=final_url)
    if git_result is None:
        return UrlValidationOutput(UrlValidationResult.NETWORK_ERROR, final_url=final_url)
    if git_result is False:
        return UrlValidationOutput(UrlValidationResult.INVALID, final_url=final_url)

    return UrlValidationOutput(UrlValidationResult.VALID, final_url=final_url)
```

Add redirect logging:
```python
if final_url != url:
    logger.info("URL redirected: %s -> %s", url, final_url)
```

Place this right after `final_url = str(resp.url)` in the try block.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_url_validator.py -v 2>&1 | head -80`
Expected: All tests PASS (including updated existing tests + new redirect tests)

- [ ] **Step 5: Commit**

```bash
git add src/purl_resolver/url_validator.py tests/test_url_validator.py
git commit -m "feat(url-validator): add UrlValidationOutput with redirect capture"
```

---

### Task 2: `validate_url_with_retry()` return type change

**Files:**
- Modify: `src/purl_resolver/url_validator.py:199-225`
- Test: `tests/test_url_validator.py:264-311`

**Interfaces:**
- Consumes: `UrlValidationOutput` from `validate_url()`
- Produces: `validate_url_with_retry()` returns `UrlValidationOutput` instead of `UrlValidationResult`

- [ ] **Step 1: Write failing tests**

Update `test_url_validator.py` tests to use `output.result`:
```python
@pytest.mark.asyncio
async def test_valid_passes_through(self):
    ...
    output = await validate_url_with_retry("https://github.com/psf/requests", timeout=5)
    assert output.result == UrlValidationResult.VALID

@pytest.mark.asyncio
async def test_token_invalid_retries_without_token(self):
    ...
    output = await validate_url_with_retry(...)
    assert output.result == UrlValidationResult.VALID

@pytest.mark.asyncio
async def test_token_invalid_without_settings_store_does_not_retry(self):
    ...
    output = await validate_url_with_retry(...)
    assert output.result == UrlValidationResult.TOKEN_INVALID
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_url_validator.py::TestValidateUrlWithRetry -v`
Expected: FAIL — `output.result` attribute not present (still `UrlValidationResult` enum)

- [ ] **Step 3: Implement `validate_url_with_retry()` return type change**

```python
async def validate_url_with_retry(
    url: str,
    timeout: int,
    github_token: str | None = None,
    settings_store: SettingsStore | None = None,
    skip_connectivity_check: bool = False,
) -> UrlValidationOutput:
    voutput = await validate_url(
        url, timeout,
        github_token=github_token,
        skip_connectivity_check=skip_connectivity_check,
    )

    if voutput.result == UrlValidationResult.TOKEN_INVALID and settings_store is not None:
        logger.warning("GitHub token invalid, removing from settings")
        try:
            app_settings = settings_store.load()
            settings_store.save(app_settings.model_copy(update={"github_token": None}))
        except Exception:
            logger.warning("Failed to persist token removal to settings", exc_info=True)
        voutput = await validate_url(
            url, timeout,
            github_token=None,
            skip_connectivity_check=skip_connectivity_check,
        )

    return voutput
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_url_validator.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/purl_resolver/url_validator.py tests/test_url_validator.py
git commit -m "feat(url-validator): propagate UrlValidationOutput through validate_url_with_retry"
```

---

### Task 3: `service.py` consumers — `_validate_cached_url()` and `resolve_purl()`

**Files:**
- Modify: `src/purl_resolver/service.py:13-163`
- Test: `tests/test_service_validation.py:1-655`

**Interfaces:**
- Consumes: `validate_url_with_retry()` returns `UrlValidationOutput` (from Task 2)
- Modifies: `_validate_cached_url()` — updates `cached.repository_url` on VALID with redirect
- Modifies: `resolve_purl()` — uses `output.final_url` for `ResolveResponse.repository_url`

- [ ] **Step 1: Write failing tests**

Update import in `test_service_validation.py`:
```python
from purl_resolver.url_validator import UrlValidationOutput, UrlValidationResult
```

Create helper for mock return values (at module level):
```python
def _url_output(result: UrlValidationResult, final_url: str | None = None) -> UrlValidationOutput:
    return UrlValidationOutput(result=result, final_url=final_url)
```

Update `TestValidationIntegration` and `TestValidateCachedUrl` mock return values:
```python
# Before: return_value=UrlValidationResult.VALID
# After:   return_value=_url_output(UrlValidationResult.VALID)
# Same for INVALID, NETWORK_ERROR, RATE_LIMITED
```

Add new tests for redirect behavior:

In `TestValidateCachedUrl`:
```python
@pytest.mark.asyncio
async def test_updates_repository_url_on_redirect(self):
    cached = ResolveResponse(
        purl="pkg:pypi/requests",
        repository_url="https://old-url.com/psf/requests",
        resolved_at="2020-01-01T00:00:00",
    )
    settings_store = MagicMock()
    settings_store.load.return_value = MagicMock(
        validate_db_urls=True,
        github_token=None,
        url_validation_timeout=5,
        revalidation_cooldown_hours=24,
    )
    storage = AsyncMock()
    with patch(
        "purl_resolver.service.validate_url_with_retry",
        new_callable=AsyncMock,
        return_value=_url_output(UrlValidationResult.VALID, final_url="https://github.com/psf/requests"),
    ):
        result = await PurlResolutionService._validate_cached_url(
            cached, settings_store, "pkg:pypi/requests", storage,
        )
    assert result is not None
    assert result.repository_url == "https://github.com/psf/requests"
    storage.store.assert_called_once_with(result)

@pytest.mark.asyncio
async def test_preserves_url_when_no_redirect(self):
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
        revalidation_cooldown_hours=24,
    )
    storage = AsyncMock()
    with patch(
        "purl_resolver.service.validate_url_with_retry",
        new_callable=AsyncMock,
        return_value=_url_output(UrlValidationResult.VALID, final_url="https://github.com/psf/requests"),
    ):
        result = await PurlResolutionService._validate_cached_url(
            cached, settings_store, "pkg:pypi/requests", storage,
        )
    assert result is not None
    assert result.repository_url == "https://github.com/psf/requests"
    storage.store.assert_called_once_with(result)
```

In `TestFreshResolverValidation`:
```python
@pytest.mark.asyncio
async def test_uses_final_url_on_redirect(self, mock_storage, mock_settings_store):
    mock_storage.lookup = AsyncMock(return_value=None)
    resolver = AsyncMock()
    resolver.name = "test_resolver"
    resolver.resolve = AsyncMock(return_value=AsyncMock(
        repository_url="https://old-url.com/repo",
        repository_type="git",
        repository_kind="vcs",
        confidence="high",
        evidence=["test"],
        warnings=[],
        version_reference=None,
    ))

    with patch(
        "purl_resolver.service.validate_url_with_retry",
        new_callable=AsyncMock,
        return_value=_url_output(UrlValidationResult.VALID, final_url="https://github.com/new/repo"),
    ):
        result = await PurlResolutionService(mock_storage, [resolver], mock_settings_store).resolve_purl(
            "pkg:npm/archy@1.0.0"
        )

    assert result.response is not None
    assert result.response.repository_url == "https://github.com/new/repo"
    mock_storage.store.assert_called_once()
    assert mock_storage.store.call_args[0][0].repository_url == "https://github.com/new/repo"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_service_validation.py -v 2>&1 | head -40`
Expected: FAIL — mock return values are `UrlValidationResult` enum, code now expects `UrlValidationOutput`

- [ ] **Step 3: Implement changes in `service.py`**

Update import:
```python
from .url_validator import UrlValidationOutput, UrlValidationResult, validate_url_with_retry
```

`_validate_cached_url()`:
```python
@staticmethod
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
    voutput = await validate_url_with_retry(
        cached.repository_url,
        app_settings.url_validation_timeout,
        github_token=github_token,
        settings_store=settings_store,
        skip_connectivity_check=True,
    )

    if voutput.result == UrlValidationResult.VALID:
        new_url = voutput.final_url or cached.repository_url
        if new_url != cached.repository_url:
            logger.info("Updated repository URL for %s: %s -> %s", purl_key, cached.repository_url, new_url)
            cached.repository_url = new_url
        try:
            await storage.store(cached)
        except Exception:
            logger.warning("Failed to update resolved_at for %s", purl_key, exc_info=True)
    elif voutput.result == UrlValidationResult.INVALID:
        try:
            await storage.delete_purls([purl_key])
        except Exception:
            logger.warning("Failed to delete invalid URL for %s", purl_key, exc_info=True)
        return None

    return cached
```

`resolve_purl()` stale/fresh URL validation section:
```python
if self._settings_store is not None:
    app_settings = self._settings_store.load()
    if app_settings.validate_db_urls:
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

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_service_validation.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/purl_resolver/service.py tests/test_service_validation.py
git commit -m "feat(service): use final URL from UrlValidationOutput in cache and fresh resolution"
```

---

### Task 4: `sbom_enrichment.py` consumer — existing refs validation

**Files:**
- Modify: `src/purl_resolver/sbom_enrichment.py:17, 85-95`
- Test: `tests/test_sbom_integration.py:242-392`

**Interfaces:**
- Consumes: `validate_url_with_retry()` returns `UrlValidationOutput` (from Task 2)
- Modifies: `SbomEnrichmentPipeline.process()` — updates `ref["url"]` on redirect

- [ ] **Step 1: Write failing tests**

Update import in `test_sbom_integration.py`:
```python
from purl_resolver.url_validator import UrlValidationOutput, UrlValidationResult
```

Helper (at top of file or in `TestValidateExistingRefs`):
```python
def _url_output(result: UrlValidationResult, final_url: str | None = None) -> UrlValidationOutput:
    return UrlValidationOutput(result=result, final_url=final_url)
```

Update existing test return values in `TestValidateExistingRefs`:
```python
# Before: return_value=UrlValidationResult.INVALID
# After:   return_value=_url_output(UrlValidationResult.INVALID)
# Same for VALID, NETWORK_ERROR
```

Add new tests for redirect behavior:
```python
@pytest.mark.asyncio
async def test_redirect_updates_ref_url(self, fake_resolvers):
    sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "components": [
            {
                "type": "library",
                "name": "requests",
                "version": "2.31.0",
                "purl": "pkg:pypi/requests@2.31.0",
                "externalReferences": [
                    {"type": "vcs", "url": "https://old-url.com/psf/requests"},
                ],
            }
        ],
    }
    storage = InMemoryCache()
    pipeline = SbomEnrichmentPipeline(
        storage=storage,
        resolvers=fake_resolvers,
        settings_store=None,
        resolution_service=PurlResolutionService(storage, fake_resolvers),
    )
    with patch(
        "purl_resolver.sbom_enrichment.validate_url_with_retry",
        new_callable=AsyncMock,
        return_value=_url_output(UrlValidationResult.VALID, final_url="https://github.com/psf/requests"),
    ):
        await pipeline.process(sbom, validate_existing_refs=True)
    enriched_refs = sbom["components"][0].get("externalReferences", [])
    assert len(enriched_refs) == 1
    assert enriched_refs[0]["url"] == "https://github.com/psf/requests"

@pytest.mark.asyncio
async def test_rate_limited_with_redirect_updates_ref_url(self, fake_resolvers):
    sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "components": [
            {
                "type": "library",
                "name": "requests",
                "version": "2.31.0",
                "purl": "pkg:pypi/requests@2.31.0",
                "externalReferences": [
                    {"type": "vcs", "url": "https://old-url.com/psf/requests"},
                ],
            }
        ],
    }
    storage = InMemoryCache()
    pipeline = SbomEnrichmentPipeline(
        storage=storage,
        resolvers=fake_resolvers,
        settings_store=None,
        resolution_service=PurlResolutionService(storage, fake_resolvers),
    )
    with patch(
        "purl_resolver.sbom_enrichment.validate_url_with_retry",
        new_callable=AsyncMock,
        return_value=_url_output(UrlValidationResult.RATE_LIMITED, final_url="https://github.com/psf/requests"),
    ):
        await pipeline.process(sbom, validate_existing_refs=True)
    enriched_refs = sbom["components"][0].get("externalReferences", [])
    assert enriched_refs[0]["url"] == "https://github.com/psf/requests"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_sbom_integration.py::TestValidateExistingRefs -v`
Expected: FAIL — mock return value type mismatch

- [ ] **Step 3: Implement changes in `sbom_enrichment.py`**

Update import:
```python
from .url_validator import UrlValidationOutput, UrlValidationResult, validate_url_with_retry
```

Update the existing-refs validation loop in `process()`:
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

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_sbom_integration.py::TestValidateExistingRefs -v`
Expected: All tests PASS

Run: `python -m pytest tests/test_sbom_integration.py -v`
Expected: All tests PASS (including other test classes)

- [ ] **Step 5: Commit**

```bash
git add src/purl_resolver/sbom_enrichment.py tests/test_sbom_integration.py
git commit -m "feat(sbom): update ref URL on redirect during existing-refs validation"
```

---

### Task 5: Update spec document invariants

**Files:**
- Modify: `specs/domains/purl-resolution.md`

- [ ] **Step 1: Add new invariants for redirect resolution**

Add to the invariants list in `specs/domains/purl-resolution.md`:

```markdown
- **URL redirects are resolved on validation**: `validate_url()` and `validate_url_with_retry()` return `UrlValidationOutput` containing the final URL after all 3xx redirects; `final_url` is `str(resp.url)` from httpx with `follow_redirects=True`
- **`git ls-remote` uses the resolved final URL**: `_git_ls_remote()` receives the final redirect target, not the original URL
- **Cache entries updated with final URL on VALID**: `_validate_cached_url()` updates `cached.repository_url` when `final_url` differs from the stored URL on `VALID` result only
- **Fresh resolver results use final URL**: `resolve_purl()` stores and returns the resolved final URL for any non-INVALID validation result (including `NETWORK_ERROR`/`RATE_LIMITED`)
- **SBOM refs updated on any non-INVALID result**: `sbom_enrichment.py` updates `ref["url"]` with `final_url` when the ref redirected, regardless of whether validation result was `VALID`, `NETWORK_ERROR`, or `RATE_LIMITED`
```

- [ ] **Step 2: Commit**

```bash
git add specs/domains/purl-resolution.md
git commit -m "docs: add redirect resolution invariants to purl-resolution spec"
```