# Remove Dead `skip_connectivity_check` Parameter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the dead `skip_connectivity_check` parameter and the associated connectivity-check code block from `validate_url`, `validate_url_with_retry`, and `UrlValidationService.validate_url`. Inline `_check_connectivity()` into `ensure_connectivity()` and delete `_check_connectivity()`.

**Architecture:** Connectivity checking becomes solely the gatekeeper's responsibility (`ensure_connectivity()` at route level). `validate_url()` relies on `_head_request()` catching `httpx.RequestError` for mid-request network failures. One public function (`ensure_connectivity`) replaces two (private `_check_connectivity` + public wrapper).

**Tech Stack:** Python 3.12, FastAPI, pytest, unittest.mock

## Global Constraints

- No `_check_connectivity` function may exist after this change — it is inlined into `ensure_connectivity`
- No `skip_connectivity_check` parameter may exist on `validate_url`, `validate_url_with_retry`, or `UrlValidationService.validate_url`
- No `connectivity_url` or `connectivity_timeout` parameters may exist on `validate_url` or `validate_url_with_retry`
- `ensure_connectivity` must remain importable from `purl_resolver.url_validator` with the same public signature plus `url`/`timeout`
- All tests must pass after changes

---
### Task 1: Core changes — `url_validator.py`

**Files:**
- Modify: `src/purl_resolver/url_validator.py:151-161` — inline `_check_connectivity` into `ensure_connectivity` and remove `_check_connectivity`
- Modify: `src/purl_resolver/url_validator.py:383-405` — remove `skip_connectivity_check`, `connectivity_url`, `connectivity_timeout` params and the `if not skip_connectivity_check:` block
- Modify: `src/purl_resolver/url_validator.py:447-480` — remove `skip_connectivity_check`, `connectivity_url`, `connectivity_timeout` params from `validate_url_with_retry` and stop passing them to `validate_url`

**Interfaces:**
- Produces: `ensure_connectivity(github_token=None, url=None, timeout=None)` — sole connectivity check function; calls `_is_private_url`, `urlsplit`, `httpx.AsyncClient.head` inlined; raises `ConnectionError` on failure
- Produces: `validate_url(url, timeout, github_token=None, rate_limit_cooldown=None)` — no more connectivity check params
- Produces: `validate_url_with_retry(url, timeout, github_token=None, settings_store=None, rate_limit_cooldown=None)` — no more connectivity check params

- [ ] **Step 1: Rewrite `ensure_connectivity` to inline `_check_connectivity` body, remove `_check_connectivity`**

```python
_CONNECTIVITY_URL = "https://github.com"
_CONNECTIVITY_TIMEOUT = 2

async def ensure_connectivity(
    github_token: str | None = None,
    url: str | None = None,
    timeout: int | None = None,
) -> bool:
    if url is not None and url == "":
        return True
    probe_url = url or _CONNECTIVITY_URL
    probe_timeout = timeout or _CONNECTIVITY_TIMEOUT
    if await _is_private_url(probe_url):
        raise ConnectionError(f"Probe URL resolves to a private address: {probe_url}")
    try:
        headers = {}
        hostname = urlsplit(probe_url).hostname
        if github_token and hostname and (hostname == "github.com" or hostname.endswith(".github.com")):
            headers["Authorization"] = f"Bearer {github_token}"
        async with httpx.AsyncClient(timeout=probe_timeout) as client:
            resp = await client.head(probe_url, headers=headers)
            ok = resp.status_code < 500
    except httpx.RequestError:
        logger.warning("Connectivity probe to %s failed", probe_url)
        ok = False
    if not ok:
        raise ConnectionError(f"Cannot reach {probe_url}")
    return True
```

Delete the `_check_connectivity` function entirely (lines 127-148 old, which was the inner implementation that returned `bool`).

- [ ] **Step 2: Remove params and dead block from `validate_url`**

Replace:
```python
async def validate_url(
    url: str,
    timeout: int,
    github_token: str | None = None,
    skip_connectivity_check: bool = False,
    connectivity_url: str | None = None,
    connectivity_timeout: int | None = None,
    rate_limit_cooldown: int | None = None,
) -> UrlValidationOutput:
    if not url.startswith(("http://", "https://")):
        return UrlValidationOutput(UrlValidationResult.INVALID)

    if await _rate_limit_tracker.is_in_cooldown():
        return UrlValidationOutput(UrlValidationResult.RATE_LIMITED)

    if not skip_connectivity_check:
        try:
            github_ok = await _check_connectivity(github_token=github_token, url=connectivity_url, timeout=connectivity_timeout)
        except (httpx.RequestError, ConnectionError, OSError):
            return UrlValidationOutput(UrlValidationResult.NETWORK_ERROR)

        if not github_ok:
            return UrlValidationOutput(UrlValidationResult.NETWORK_ERROR)
```

With:
```python
async def validate_url(
    url: str,
    timeout: int,
    github_token: str | None = None,
    rate_limit_cooldown: int | None = None,
) -> UrlValidationOutput:
    if not url.startswith(("http://", "https://")):
        return UrlValidationOutput(UrlValidationResult.INVALID)

    if await _rate_limit_tracker.is_in_cooldown():
        return UrlValidationOutput(UrlValidationResult.RATE_LIMITED)
```

- [ ] **Step 3: Remove params from `validate_url_with_retry`**

Replace:
```python
async def validate_url_with_retry(
    url: str,
    timeout: int,
    github_token: str | None = None,
    settings_store: SettingsStore | None = None,
    skip_connectivity_check: bool = False,
    connectivity_url: str | None = None,
    connectivity_timeout: int | None = None,
    rate_limit_cooldown: int | None = None,
) -> UrlValidationOutput:
    voutput = await validate_url(
        url, timeout,
        github_token=github_token,
        skip_connectivity_check=skip_connectivity_check,
        connectivity_url=connectivity_url,
        connectivity_timeout=connectivity_timeout,
        rate_limit_cooldown=rate_limit_cooldown,
    )
```

With:
```python
async def validate_url_with_retry(
    url: str,
    timeout: int,
    github_token: str | None = None,
    settings_store: SettingsStore | None = None,
    rate_limit_cooldown: int | None = None,
) -> UrlValidationOutput:
    voutput = await validate_url(
        url, timeout,
        github_token=github_token,
        rate_limit_cooldown=rate_limit_cooldown,
    )
```

Also update the retry call on lines ~468-478 (old) — remove `skip_connectivity_check` and `connectivity_url`/`connectivity_timeout` from the retry `validate_url` call.

- [ ] **Step 4: Run tests to check Task 1 changes**

Run: `python -m pytest tests/test_url_validator.py -v`
Expected: Failures in `TestEnsureConnectivity` (patch target removed) and multiple tests that patch `_check_connectivity`

---
### Task 2: Update wrappers and callers

**Files:**
- Modify: `src/purl_resolver/validation_service.py:18` — remove `skip_connectivity_check` param
- Modify: `src/purl_resolver/validation_service.py:24` — stop passing `skip_connectivity_check`
- Modify: `src/purl_resolver/service.py:73-85` — remove `skip_connectivity_check=True` from both branches of `_validate_cached_url`
- Modify: `src/purl_resolver/service.py:150-162` — remove `skip_connectivity_check=True` from both branches of `resolve_purl`
- Modify: `src/purl_resolver/sbom_enrichment.py:77-89` — remove `skip_connectivity_check=True` from both branches

- [ ] **Step 1: Update `UrlValidationService`**

Replace in `validation_service.py`:
```python
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

With:
```python
async def validate_url(
    self,
    url: str,
    timeout: int,
    github_token: str | None = None,
) -> UrlValidationOutput:
    return await validate_url_with_retry(
        url, timeout,
        github_token=github_token,
        settings_store=self._settings_store,
    )
```

- [ ] **Step 2: Update `service.py`**

In `_validate_cached_url` (lines ~72-86), remove `skip_connectivity_check=True` from both calls.

In `resolve_purl` (lines ~150-162), remove `skip_connectivity_check=True` from both calls.

- [ ] **Step 3: Update `sbom_enrichment.py`**

Remove `skip_connectivity_check=True` from both calls (lines ~77-89).

- [ ] **Step 4: Run tests to check Task 2 changes**

Run: `python -m pytest tests/test_service_validation.py tests/test_sbom_integration.py -v`
Expected: Failures still from test_url_validator.py and from assertion checks that verify `skip_connectivity_check=True` in call args

---
### Task 3: Update tests

**Files:**
- Modify: `tests/test_url_validator.py` — remove `_check_connectivity` patches, rewrite `TestEnsureConnectivity`, delete `TestValidateUrlSkipConnectivity`
- Modify: `tests/test_service_validation.py` — remove `skip_connectivity_check=True` from 3 assertion blocks
- Modify: `tests/test_sbom_integration.py` — remove `skip_connectivity_check=True` from 1 assertion block

- [ ] **Step 1: Update `test_url_validator.py` — remove `_check_connectivity` patches from all test methods in `TestValidateUrl`**

For every test in `TestValidateUrl`, `TestValidateUrlRedirectCapture`, `TestValidateUrlWithToken`, `TestValidateUrlWithRetry` that has:
```python
patch("purl_resolver.url_validator._check_connectivity", new_callable=AsyncMock, return_value=True)
```
Remove that patch from the `with` statement and reflow the remaining patches.

- [ ] **Step 2: Update `test_url_validator.py` — delete `test_connectivity_probe_fails_returns_network_error`**

Remove the method `test_connectivity_probe_fails_returns_network_error` (lines ~97-100). This test verified the connectivity check inside `validate_url`, which no longer exists.

- [ ] **Step 3: Update `test_url_validator.py` — delete `TestValidateUrlSkipConnectivity`**

Remove the entire class (lines ~260-279). Both tests (`test_skip_connectivity_check_skips_probe` and `test_default_still_checks_connectivity`) test the removed parameter behavior.

- [ ] **Step 4: Update `test_url_validator.py` — rewrite `TestEnsureConnectivity`**

Replace `TestEnsureConnectivity` tests that mock `_check_connectivity` with tests that mock `httpx.AsyncClient`:

```python
class TestEnsureConnectivity:
    @pytest.mark.asyncio
    async def test_success_returns_true(self):
        with patch("purl_resolver.url_validator.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.head.return_value.status_code = 200
            result = await ensure_connectivity()
            assert result is True

    @pytest.mark.asyncio
    async def test_failure_raises_connection_error(self):
        with patch("purl_resolver.url_validator.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.head.side_effect = httpx.RequestError("fail")
            with pytest.raises(ConnectionError, match="Cannot reach https://github.com"):
                await ensure_connectivity()

    @pytest.mark.asyncio
    async def test_success_with_custom_url_and_timeout(self):
        with patch("purl_resolver.url_validator.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.head.return_value.status_code = 200
            result = await ensure_connectivity(url="https://gitlab.com", timeout=5)
            assert result is True
            mock_client.assert_called_once_with(timeout=5)
            call_url = mock_client.return_value.__aenter__.return_value.head.call_args[0][0]
            assert call_url == "https://gitlab.com"

    @pytest.mark.asyncio
    async def test_empty_url_returns_true(self):
        result = await ensure_connectivity(url="")
        assert result is True

    @pytest.mark.asyncio
    async def test_private_url_raises_error(self):
        with patch("purl_resolver.url_validator._is_private_url", new_callable=AsyncMock, return_value=True):
            with pytest.raises(ConnectionError, match="private address"):
                await ensure_connectivity()
```

- [ ] **Step 5: Update `test_service_validation.py`**

Remove `skip_connectivity_check=True` from 3 assertion blocks (lines ~322, ~753, ~785).

For each, change:
```python
            skip_connectivity_check=True,
```
to nothing (remove the line and trailing comma from the previous arg).

- [ ] **Step 6: Update `test_sbom_integration.py`**

Remove `skip_connectivity_check=True` from 1 assertion block (line ~477).

- [ ] **Step 7: Run full test suite**

Run: `python -m pytest -v`
Expected: All 440+ tests pass

---
### Task 4: Update spec document

**Files:**
- Modify: `specs/domains/purl-resolution.md:159-160,162,179`

- [ ] **Step 1: Update `validate_url` signature in spec**

Change line 159:
```markdown
- `validate_url(url, timeout, github_token=None) → UrlValidationOutput` — performs HEAD (with `follow_redirects=True`), captures the final URL after all 3xx redirects via `str(resp.url)`, then runs `_check_vcs()` against the final URL; returns `UrlValidationOutput(result, final_url)`
```

- [ ] **Step 2: Update `validate_url_with_retry` signature in spec**

Change line 160:
```markdown
- `validate_url_with_retry(url, timeout, github_token=None, settings_store=None) → UrlValidationOutput` — wraps `validate_url()` with `TOKEN_INVALID` retry: clears the GitHub token from `AppSettings` and re-validates without authentication
```

- [ ] **Step 3: Update `ensure_connectivity` description in spec**

Change line 162:
```markdown
- `ensure_connectivity(github_token=None, url=None, timeout=None) → bool` — connectivity probe against configurable URL (default `https://github.com`); raises `ConnectionError` on failure
```

- [ ] **Step 4: Update `UrlValidationService.validate_url` signature in spec**

Change line 179:
```markdown
- `UrlValidationService.validate_url(url, timeout, github_token=None) → UrlValidationOutput` — delegates to `validate_url_with_retry()` with the injected `settings_store`
```