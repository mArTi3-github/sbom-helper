# URL Validation Redirect Resolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow non-HTTP/HTTPS VCS URLs (git://, ssh://, svn://) to pass validation by removing the blanket scheme gate and HEAD status-code checks, while preserving redirect resolution and token-invalidity detection for HTTP/HTTPS URLs.

**Architecture:** Three-step `validate_url()` flow: (1) hostname + SSRF pre-check, (2) redirect resolution via lightweight HEAD (HTTP/HTTPS only, 401/403→TOKEN_INVALID), (3) VCS probe via existing `_check_vcs()`. `_RateLimitTracker` and `rate_limit_cooldown` removed entirely.

**Tech Stack:** Python 3.12+ asyncio, httpx, FastAPI, Vue 3 + Pinia, pytest

## Global Constraints

- All repos being validated are **public** — `github_token` is used only for higher rate limits, not for private repo access
- `_git_probe` oauth2:token rewrite for GitHub URLs **must be preserved** (rate limits)
- `_check_vcs` continues to receive `github_token`
- `_head_request()` kept unchanged for `validate_github_token()`
- `rate_limit_cooldown` removed from `AppSettings`, validate_url, API, and frontend
- `_RateLimitTracker`, `_rate_limit_tracker`, `_is_rate_limited` — deleted
- Existing `.json` settings files silently drop unknown fields — removing `rate_limit_cooldown` from pydantic model is safe
- `UrlValidationResult.RATE_LIMITED` kept in enum (not returned anymore, but removal is breaking change)

---

### Task 1: Core url_validator.py changes

**Files:** Modify `src/purl_resolver/url_validator.py`

**Interfaces:**
- Consumes: `_head_request()`, `_check_vcs()`, `_git_probe()`, `_is_private_url()` — all unchanged
- Produces: `_resolve_redirects()` helper, updated `validate_url()`, updated `validate_url_with_retry()`

- [ ] **Step 1.1: Remove `_RateLimitTracker`, `_rate_limit_tracker`, `_is_rate_limited`**

Delete lines 84-124 (the class, singleton, and function):
- `class _RateLimitTracker` and its body (lines 84-113)
- `_rate_limit_tracker = _RateLimitTracker()` (line 114)
- `/^def _is_rate_limited/` through its body (lines 117-124)

- [ ] **Step 1.2: Remove `rate_limit_cooldown` parameter from `validate_url()`**

Change line 377 from:
```python
    rate_limit_cooldown: int | None = None,
```
to (remove the parameter):
```python
```

Remove the `_rate_limit_tracker.is_in_cooldown()` check currently on lines 382-383:
```python
    if await _rate_limit_tracker.is_in_cooldown():
        return UrlValidationOutput(UrlValidationResult.RATE_LIMITED)
```

Remove the `_rate_limit_tracker.record_rate_limit(cooldown=rate_limit_cooldown)` on line 397 (inside the `_is_rate_limited` branch that is already removed).

Remove the `_rate_limit_tracker.reset()` call on line 400.

- [ ] **Step 1.3: Remove the scheme gate at line 379**

Delete this block:
```python
    if not url.startswith(("http://", "https://")):
        return UrlValidationOutput(UrlValidationResult.INVALID)
```

- [ ] **Step 1.4: Add pre-check before HEAD, then rewrite the url resolution flow**

Insert a pre-check block right after the `async def validate_url(...)` signature and before the scheme check. The pre-check rejects URLs with no hostname or that resolve to private networks:

```python
    hostname = urlsplit(url).hostname
    if not hostname:
        return UrlValidationOutput(UrlValidationResult.INVALID)

    if await _is_private_url(url):
        return UrlValidationOutput(UrlValidationResult.INVALID)
```

Then replace the old `try:` block (currently lines 385-410) with:
```python
    try:
        resp = await _head_request(url, timeout, github_token=github_token)
        final_url = str(resp.url)
        ...
        status = resp.status_code
    except httpx.RequestError:
        _rate_limit_tracker.reset()
        return UrlValidationOutput(UrlValidationResult.NETWORK_ERROR)

    if _is_rate_limited(status, headers):
        await _rate_limit_tracker.record_rate_limit(cooldown=rate_limit_cooldown)
        return UrlValidationOutput(UrlValidationResult.RATE_LIMITED, final_url=final_url)

    _rate_limit_tracker.reset()

    if status in (401, 403) and github_token:
        return UrlValidationOutput(UrlValidationResult.TOKEN_INVALID, final_url=final_url)

    if status in (404, 405):
        return UrlValidationOutput(UrlValidationResult.INVALID, final_url=final_url)
    if status == 403:
        return UrlValidationOutput(UrlValidationResult.INVALID, final_url=final_url)
    if status >= 400:
        return UrlValidationOutput(UrlValidationResult.INVALID, final_url=final_url)
```

Replace with:
```python
    final_url = url
    if url.startswith(("http://", "https://")):
        try:
            resp = await _head_request(url, timeout, github_token=github_token)
            if resp.status_code in (401, 403) and github_token:
                return UrlValidationOutput(
                    UrlValidationResult.TOKEN_INVALID,
                    final_url=str(resp.url),
                )
            final_url = str(resp.url)
        except (httpx.RequestError, ConnectionError):
            pass  # graceful degradation — keep original url

    try:
        git_result = await _check_vcs(final_url, timeout, github_token=github_token)
    except Exception:
        logger.warning("VCS check failed unexpectedly for %s", final_url, exc_info=True)
        return UrlValidationOutput(UrlValidationResult.NETWORK_ERROR, final_url=final_url)
    if git_result is None:
        return UrlValidationOutput(UrlValidationResult.NETWORK_ERROR, final_url=final_url)
    if git_result is False:
        return UrlValidationOutput(UrlValidationResult.INVALID, final_url=final_url)

    return UrlValidationOutput(UrlValidationResult.VALID, final_url=final_url)
```

- [ ] **Step 1.5: Update `validate_url_with_retry()` — remove `rate_limit_cooldown` param**

Change line 430 from:
```python
    rate_limit_cooldown: int | None = None,
```
to (remove):
```python
```

Remove `rate_limit_cooldown=rate_limit_cooldown` from both calls to `validate_url()` inside `validate_url_with_retry()` (lines 435 and 448).

- [ ] **Step 1.6: Verify the file compiles and imports**

```bash
cd /home/administrator/Desktop/projects/sbom-helper
python -c "from purl_resolver.url_validator import validate_url, validate_url_with_retry, UrlValidationResult; print('OK')"
```
Expected: `OK`

- [ ] **Step 1.7: Run existing non-rate-limit tests to verify basic flow still works**

```bash
cd /home/administrator/Desktop/projects/sbom-helper
.venv/bin/python -m pytest tests/test_vcs_check.py -v 2>&1 | tail -30
```
Expected: All existing VCS probe tests pass (git, svn, hg, fossil probes)

---

### Task 2: Update url_validator tests

**Files:**
- Modify: `tests/test_url_validator.py`
- Modify: `tests/test_settings_store.py`

**Interfaces:**
- Consumes: `validate_url()`, `validate_url_with_retry()` — updated signatures (no `rate_limit_cooldown`)
- Consumes: `UrlValidationResult` — same enum

- [ ] **Step 2.1: Remove rate-limit tracker fixture**

In `tests/test_url_validator.py`, remove the `reset_rate_limit_tracker` fixture (lines 19-24):
```python
@pytest.fixture(autouse=True)
def reset_rate_limit_tracker():
    from purl_resolver.url_validator import _rate_limit_tracker
    _rate_limit_tracker.reset()
    yield
    _rate_limit_tracker.reset()
```

- [ ] **Step 2.2: Update `_mock_head` to return mocked httpx response with async context**

The tests currently mock `_head_request` which returns an `AsyncMock`. The new code calls `_head_request` and checks `resp.status_code` and `resp.url`. Keep `_mock_head` and `_mock_response` helpers — they already expose `.status_code` and `.url`.

- [ ] **Step 2.3: Update `test_valid_url` test**

Change `test_valid_url` to mock `_head_request` for redirect resolution:
```python
    async def test_valid_url(self):
        with patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head, \
             patch("purl_resolver.url_validator._check_vcs", new_callable=AsyncMock, return_value=True):
            mock_head.return_value = _mock_head(200)
            result = await validate_url("https://github.com/psf/requests", timeout=5)
            assert result.result == UrlValidationResult.VALID
```

- [ ] **Step 2.4: Update `test_head_404_returns_invalid`**

HEAD 404 should no longer cause INVALID. Change test to verify 404 is ignored and validation proceeds to `_check_vcs`:
```python
    async def test_head_404_ignored_validation_proceeds(self):
        with patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head, \
             patch("purl_resolver.url_validator._check_vcs", new_callable=AsyncMock, return_value=True):
            mock_head.return_value = _mock_head(404)
            result = await validate_url("https://github.com/deleted/repo", timeout=5)
            assert result.result == UrlValidationResult.VALID
```

- [ ] **Step 2.5: Update `test_head_403_without_rate_limit_headers_returns_invalid`**

HEAD 403 without token should be ignored (not INVALID). Change to:
```python
    async def test_head_403_without_token_ignored(self):
        with patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head, \
             patch("purl_resolver.url_validator._check_vcs", new_callable=AsyncMock, return_value=True):
            mock_head.return_value = _mock_head(403, {"x-github-media-type": "v3"})
            result = await validate_url("https://github.com/private/repo", timeout=5)
            assert result.result == UrlValidationResult.VALID
```

- [ ] **Step 2.6: Remove rate-limit tests**

Delete `test_head_403_with_rate_limit_remaining_zero_returns_rate_limited`, `test_head_429_returns_rate_limited`, and `test_rate_limit_cooldown_skips_validation`.

- [ ] **Step 2.7: Update `test_head_connection_error_returns_network_error`**

When HEAD fails with RequestError, the new code falls back to original URL and proceeds to VCS probe. If VCS probe returns True, result is VALID:
```python
    async def test_head_connection_error_falls_back_and_vcs_probes(self):
        with patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head, \
             patch("purl_resolver.url_validator._check_vcs", new_callable=AsyncMock, return_value=True):
            mock_head.side_effect = httpx.RequestError("Connection refused")
            result = await validate_url("https://example.com/repo", timeout=5)
            assert result.result == UrlValidationResult.VALID
```

- [ ] **Step 2.8: Update `test_file_url_returns_invalid`**

File URLs now go through pre-check: hostname check fails (no hostname in `file:///...`), so they still return INVALID. Update comment:
```python
    async def test_file_url_returns_invalid(self):
        result = await validate_url("file:///usr/src/app/ptaf-task-mgr", timeout=5)
        assert result.result == UrlValidationResult.INVALID
```
No code change needed — keeps same behavior via hostname check.

- [ ] **Step 2.9: Add tests for non-HTTP VCS URLs**

```python
    @pytest.mark.asyncio
    async def test_git_url_valid(self):
        with patch("purl_resolver.url_validator._check_vcs", new_callable=AsyncMock, return_value=True):
            result = await validate_url("git://github.com/user/repo.git", timeout=5)
            assert result.result == UrlValidationResult.VALID

    @pytest.mark.asyncio
    async def test_ssh_url_valid(self):
        with patch("purl_resolver.url_validator._check_vcs", new_callable=AsyncMock, return_value=True):
            result = await validate_url("ssh://git@github.com/user/repo.git", timeout=5)
            assert result.result == UrlValidationResult.VALID

    @pytest.mark.asyncio
    async def test_svn_url_valid(self):
        with patch("purl_resolver.url_validator._check_vcs", new_callable=AsyncMock, return_value=True):
            result = await validate_url("svn://svn.example.com/repo", timeout=5)
            assert result.result == UrlValidationResult.VALID
```

- [ ] **Step 2.10: Add test for private network non-HTTP URL**

```python
    @pytest.mark.asyncio
    async def test_ssh_url_private_network_returns_invalid(self):
        with patch("purl_resolver.url_validator._is_private_url", new_callable=AsyncMock, return_value=True):
            result = await validate_url("ssh://10.0.0.1/repo", timeout=5)
            assert result.result == UrlValidationResult.INVALID
```

- [ ] **Step 2.11: Remove `test_rate_limit_cooldown_default` from `test_settings_store.py`**

Delete the test method `test_rate_limit_cooldown_default` (lines 39-41):
```python
    def test_rate_limit_cooldown_default(self):
        s = AppSettings()
        assert s.rate_limit_cooldown == 60
```

- [ ] **Step 2.12: Run all relevant tests**

```bash
cd /home/administrator/Desktop/projects/sbom-helper
.venv/bin/python -m pytest tests/test_url_validator.py tests/test_vcs_check.py tests/test_settings_store.py -v 2>&1 | tail -40
```
Expected: All tests pass

---

### Task 3: Remove `rate_limit_cooldown` from backend settings

**Files:**
- Modify: `src/purl_resolver/settings_store.py:32`
- Modify: `src/purl_resolver/routes/settings.py:50,84,150`

**Interfaces:**
- Consumes: `AppSettings` pydantic model — remove `rate_limit_cooldown` field
- Consumes: `SettingsUpdate` pydantic model — remove `rate_limit_cooldown` field
- Both serialization points in GET and PATCH responses — remove the key

- [ ] **Step 3.1: Remove `rate_limit_cooldown` from `AppSettings` in `settings_store.py`**

Delete line 32:
```python
    rate_limit_cooldown: int = Field(default=60, ge=1, le=600)
```

- [ ] **Step 3.2: Remove `rate_limit_cooldown` from `SettingsUpdate` in `routes/settings.py`**

Delete line 50:
```python
    rate_limit_cooldown: int | None = Field(None, ge=1, le=600)
```

- [ ] **Step 3.3: Remove `rate_limit_cooldown` from GET response in `routes/settings.py:84`**

Delete line 84:
```python
        "rate_limit_cooldown": app_settings.rate_limit_cooldown,
```

- [ ] **Step 3.4: Remove `rate_limit_cooldown` from PATCH response in `routes/settings.py:150`**

Delete line 150:
```python
        "rate_limit_cooldown": updated.rate_limit_cooldown,
```

- [ ] **Step 3.5: Verify backend compiles**

```bash
cd /home/administrator/Desktop/projects/sbom-helper
.venv/bin/python -c "from purl_resolver.settings_store import AppSettings; s = AppSettings(); print('rate_limit_cooldown' not in s.model_dump())"
```
Expected: `True`

- [ ] **Step 3.6: Run settings store tests**

```bash
cd /home/administrator/Desktop/projects/sbom-helper
.venv/bin/python -m pytest tests/test_settings_store.py -v 2>&1 | tail -20
```
Expected: All pass

---

### Task 4: Remove `rate_limit_cooldown` from frontend

**Files:**
- Modify: `frontend/src/types/api.ts:44,66`
- Modify: `frontend/src/stores/useSettingsStore.ts:20,48,72`
- Modify: `frontend/src/views/Settings.vue:240-248`
- Modify: `frontend/src/views/Settings.test.ts:21`

**Interfaces:**
- Consumes: `SettingsResponse` TypeScript interface — remove `rate_limit_cooldown`
- Consumes: `SettingsUpdate` TypeScript interface — remove `rate_limit_cooldown?`
- Consumes: Pinia store — remove `rateLimitCooldown` ref and all references

- [ ] **Step 4.1: Remove `rate_limit_cooldown` from `frontend/src/types/api.ts`**

From `SettingsResponse` (line 44):
```typescript
  rate_limit_cooldown: number
```

From `SettingsUpdate` (line 66):
```typescript
  rate_limit_cooldown?: number
```

- [ ] **Step 4.2: Remove `rateLimitCooldown` from `frontend/src/stores/useSettingsStore.ts`**

Delete line 20:
```typescript
  const rateLimitCooldown = ref(60)
```

Delete line 48:
```typescript
      rateLimitCooldown.value = data.rate_limit_cooldown
```

Remove `rateLimitCooldown` from the returned refs on line 72:
```typescript
    batchSemaphoreLimit, connectivityUrl, connectivityTimeout, rateLimitCooldown, jsonIndent,
```

- [ ] **Step 4.3: Remove the "Rate-limit cooldown" UI card from `frontend/src/views/Settings.vue`**

Delete lines 240-248:
```html
        <div class="setting-row">
          <div>
            <div class="setting-label">Rate-limit cooldown (seconds)</div>
            <div class="setting-desc">
              How long to pause URL validation after consecutive rate-limited responses (1–600 seconds). Default: 60.
            </div>
          </div>
          <input type="number" v-model.number="rateLimitCooldown" min="1" max="600" @change="debouncedAutoSave({ rate_limit_cooldown: rateLimitCooldown })" class="num-input">
        </div>
```

Also remove `rateLimitCooldown` from the `storeToRefs` destructuring on line 307:
```typescript
  batchSemaphoreLimit, connectivityUrl, connectivityTimeout, rateLimitCooldown,
```

- [ ] **Step 4.4: Remove `rate_limit_cooldown` from `frontend/src/views/Settings.test.ts`**

Delete line 21 from the `defaultSettings` object:
```typescript
  rate_limit_cooldown: 60,
```

- [ ] **Step 4.5: Run frontend type check**

```bash
cd /home/administrator/Desktop/projects/sbom-helper/frontend
npx tsc --noEmit 2>&1
```
Expected: No type errors

---

### Task 5: Update domain specification document

**Files:** Modify `specs/domains/purl-resolution.md`

- [ ] **Step 5.1: Replace the invariant on line 208**

Current:
```
- **Non-http/https URLs are invalid immediately**: `validate_url()` returns `UrlValidationOutput(INVALID)` for any URL that does not start with `http://` or `https://` without making any network request
```

Replace with:
```
- **Non-HTTP/HTTPS URLs skip redirect resolution**: URLs are validated by syntax (non-empty hostname) and SSRF guard (non-private IP) before VCS probes. HTTP/HTTPS URLs additionally undergo HEAD redirect resolution and token-invalidity detection (401/403). Non-HTTP/HTTPS URLs skip redirect resolution and go directly to VCS probes.
```