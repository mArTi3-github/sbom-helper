# HTTP Resolver Retry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add configurable retry logic with linear backoff to `EcosystemsResolver` and `LibrariesIoResolver` for HTTP 429, timeout, and 5xx errors.

**Architecture:** New `RetryHelper` class in `resolver/retry.py` encapsulates retry loop logic. Each HTTP resolver accepts an optional `RetryConfig` and wraps its `httpx.AsyncClient.get()` call via `RetryHelper.execute()`. Two new universal settings (`retry_max_attempts`, `retry_base_cooldown_seconds`) in `AppSettings`. `Purl2RepoResolver` unchanged.

**Tech Stack:** Python 3.12, httpx, asyncio, pytest (asyncio_mode=auto)

---

### Task 1: Create `RetryHelper` module

**Files:**
- Create: `src/purl_resolver/resolver/retry.py`

- [ ] **Step 1: Write `retry.py`**

```python
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)


@dataclass
class RetryConfig:
    max_attempts: int = 3
    base_cooldown_seconds: float = 5.0


class RetryableErrorPolicy:
    @staticmethod
    def is_retryable(exc: Exception) -> bool:
        if isinstance(exc, httpx.TimeoutException):
            return True
        if isinstance(exc, httpx.HTTPStatusError):
            return exc.response.status_code in (429, *range(500, 600))
        if isinstance(exc, httpx.HTTPError):
            return True
        return False


class RetryHelper:

    def __init__(self, config: RetryConfig) -> None:
        self._config = config

    async def execute[T](
        self,
        coroutine_factory: Callable[[], Awaitable[T]],
    ) -> T:
        max_attempts = self._config.max_attempts
        cooldown = self._config.base_cooldown_seconds
        last_exc: Exception | None = None

        for attempt in range(1, max_attempts + 1):
            try:
                return await coroutine_factory()
            except Exception as exc:
                last_exc = exc
                if not RetryableErrorPolicy.is_retryable(exc):
                    raise
                if attempt < max_attempts:
                    wait = cooldown * attempt
                    logger.warning(
                        "Request failed (attempt %d/%d), retrying in %.1fs: %s",
                        attempt, max_attempts, wait, exc,
                    )
                    await asyncio.sleep(wait)

        logger.warning(
            "Request failed after %d attempts: %s",
            max_attempts, last_exc,
        )
        raise last_exc
```

- [ ] **Step 2: Create initial test file to verify it imports and basic structure**

Run: `python -c "from purl_resolver.resolver.retry import RetryConfig, RetryHelper, RetryableErrorPolicy; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/purl_resolver/resolver/retry.py
git commit -m "feat: add RetryHelper module with RetryConfig, RetryableErrorPolicy, RetryHelper"
```

---

### Task 2: Unit tests for `RetryHelper`

**Files:**
- Create: `tests/test_retry_helper.py`

- [ ] **Step 1: Write the failing test file**

```python
from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from purl_resolver.resolver.retry import RetryConfig, RetryHelper, RetryableErrorPolicy


class TestRetryableErrorPolicy:

    def test_timeout_is_retryable(self) -> None:
        assert RetryableErrorPolicy.is_retryable(httpx.TimeoutException("timeout"))

    def test_429_is_retryable(self) -> None:
        response = httpx.Response(429)
        exc = httpx.HTTPStatusError("rate limit", request=httpx.Request("GET", "/"), response=response)
        assert RetryableErrorPolicy.is_retryable(exc)

    def test_500_is_retryable(self) -> None:
        response = httpx.Response(500)
        exc = httpx.HTTPStatusError("error", request=httpx.Request("GET", "/"), response=response)
        assert RetryableErrorPolicy.is_retryable(exc)

    def test_503_is_retryable(self) -> None:
        response = httpx.Response(503)
        exc = httpx.HTTPStatusError("unavailable", request=httpx.Request("GET", "/"), response=response)
        assert RetryableErrorPolicy.is_retryable(exc)

    def test_404_is_not_retryable(self) -> None:
        response = httpx.Response(404)
        exc = httpx.HTTPStatusError("not found", request=httpx.Request("GET", "/"), response=response)
        assert not RetryableErrorPolicy.is_retryable(exc)

    def test_400_is_not_retryable(self) -> None:
        response = httpx.Response(400)
        exc = httpx.HTTPStatusError("bad request", request=httpx.Request("GET", "/"), response=response)
        assert not RetryableErrorPolicy.is_retryable(exc)

    def test_network_error_is_retryable(self) -> None:
        assert RetryableErrorPolicy.is_retryable(httpx.ConnectError("connection refused"))

    def test_unrelated_exception_is_not_retryable(self) -> None:
        assert not RetryableErrorPolicy.is_retryable(ValueError("whatever"))


class TestRetryHelper:

    @pytest.mark.asyncio
    async def test_success_on_first_attempt(self) -> None:
        helper = RetryHelper(RetryConfig(max_attempts=3, base_cooldown_seconds=0.01))
        mock = AsyncMock()
        mock.side_effect = ["ok"]
        result = await helper.execute(lambda: mock())
        assert result == "ok"
        assert mock.call_count == 1

    @pytest.mark.asyncio
    async def test_retry_then_success(self) -> None:
        helper = RetryHelper(RetryConfig(max_attempts=3, base_cooldown_seconds=0.01))
        response = httpx.Response(429)
        mock = AsyncMock()
        mock.side_effect = [
            httpx.HTTPStatusError("rate limit", request=httpx.Request("GET", "/"), response=response),
            httpx.HTTPStatusError("rate limit", request=httpx.Request("GET", "/"), response=response),
            "ok",
        ]
        result = await helper.execute(lambda: mock())
        assert result == "ok"
        assert mock.call_count == 3

    @pytest.mark.asyncio
    async def test_all_attempts_fail(self) -> None:
        helper = RetryHelper(RetryConfig(max_attempts=2, base_cooldown_seconds=0.01))
        response = httpx.Response(503)
        exc = httpx.HTTPStatusError("unavailable", request=httpx.Request("GET", "/"), response=response)
        mock = AsyncMock()
        mock.side_effect = [exc, exc]
        with pytest.raises(httpx.HTTPStatusError):
            await helper.execute(lambda: mock())
        assert mock.call_count == 2

    @pytest.mark.asyncio
    async def test_non_retryable_raises_immediately(self) -> None:
        helper = RetryHelper(RetryConfig(max_attempts=3, base_cooldown_seconds=0.01))
        response = httpx.Response(404)
        exc = httpx.HTTPStatusError("not found", request=httpx.Request("GET", "/"), response=response)
        mock = AsyncMock()
        mock.side_effect = [exc]
        with pytest.raises(httpx.HTTPStatusError):
            await helper.execute(lambda: mock())
        assert mock.call_count == 1

    @pytest.mark.asyncio
    async def test_cooldown_respects_linear_backoff(self) -> None:
        helper = RetryHelper(RetryConfig(max_attempts=3, base_cooldown_seconds=0.1))
        response = httpx.Response(429)
        exc = httpx.HTTPStatusError("rate limit", request=httpx.Request("GET", "/"), response=response)
        mock = AsyncMock()
        mock.side_effect = [exc, exc, "ok"]
        import time
        t0 = time.monotonic()
        await helper.execute(lambda: mock())
        elapsed = time.monotonic() - t0
        # attempt 1: fail, wait 0.1*1 = 0.1s
        # attempt 2: fail, wait 0.1*2 = 0.2s
        # attempt 3: success
        assert elapsed >= 0.3
```

- [ ] **Step 2: Run to verify it fails (no module yet)**

Run: `python -m pytest tests/test_retry_helper.py -v`
Expected: All 8 tests pass (since module exists from Task 1)

- [ ] **Step 3: Commit**

```bash
git add tests/test_retry_helper.py
git commit -m "test: add unit tests for RetryHelper and RetryableErrorPolicy"
```

---

### Task 3: Add retry settings to `AppSettings`

**Files:**
- Modify: `src/purl_resolver/settings_store.py`

- [ ] **Step 1: Add two new fields to `AppSettings`**

Edit `src/purl_resolver/settings_store.py`. Add after `revalidation_cooldown_hours`:

```python
    retry_max_attempts: int = Field(default=3, ge=1, le=10)
    retry_base_cooldown_seconds: float = Field(default=5.0, ge=0.5, le=120.0)
```

- [ ] **Step 2: Run existing tests to verify no breakage**

Run: `python -m pytest tests/test_settings_store.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add src/purl_resolver/settings_store.py
git commit -m "feat: add retry_max_attempts and retry_base_cooldown_seconds to AppSettings"
```

---

### Task 4: Expose retry settings via API

**Files:**
- Modify: `src/purl_resolver/routes/settings.py`

- [ ] **Step 1: Add fields to `SettingsUpdate`**

After `revalidation_cooldown_hours` line:

```python
    retry_max_attempts: int | None = Field(None, ge=1, le=10)
    retry_base_cooldown_seconds: float | None = Field(None, ge=0.5, le=120.0)
```

- [ ] **Step 2: Include new fields in GET response**

In `get_settings()` response dict, add after `"revalidation_cooldown_hours"`:

```python
        "retry_max_attempts": settings.retry_max_attempts,
        "retry_base_cooldown_seconds": settings.retry_base_cooldown_seconds,
```

- [ ] **Step 3: Run existing tests**

Run: `python -m pytest tests/test_api.py tests/test_settings_store.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/purl_resolver/routes/settings.py
git commit -m "feat: expose retry_max_attempts and retry_base_cooldown_seconds via API"
```

---

### Task 5: Update `EcosystemsResolver` with retry support

**Files:**
- Modify: `src/purl_resolver/resolver/ecosystems.py`

- [ ] **Step 1: Add import and constructor parameter**

Add import at top:
```python
from .retry import RetryConfig, RetryHelper
```

Change `__init__` signature:
```python
    def __init__(
        self,
        api_key: str | None = None,
        timeout: float = 15.0,
        max_requests_per_second: float = 2.0,
        retry_config: RetryConfig | None = None,
    ) -> None:
```

Add after `self._last_request_time = 0.0`:
```python
        self._retry = RetryHelper(retry_config or RetryConfig())
```

- [ ] **Step 2: Wrap HTTP call in `resolve()`**

Replace:
```python
        try:
            response = await self._client.get(_API_URL, params=params)
            response.raise_for_status()
```

With:
```python
        try:
            response = await self._retry.execute(lambda: self._client.get(_API_URL, params=params))
            response.raise_for_status()
            logger.info("ecosyste.ms resolved %s successfully", purl)
```

- [ ] **Step 3: Run existing ecosystems tests**

Run: `python -m pytest tests/test_ecosystems_resolver.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/purl_resolver/resolver/ecosystems.py
git commit -m "feat: add retry support to EcosystemsResolver"
```

---

### Task 6: Update `LibrariesIoResolver` with retry support

**Files:**
- Modify: `src/purl_resolver/resolver/librariesio.py`

- [ ] **Step 1: Add import and constructor parameter**

Add import at top:
```python
from .retry import RetryConfig, RetryHelper
```

Change `__init__` signature:
```python
    def __init__(self, api_key: str, timeout: float = 15.0, retry_config: RetryConfig | None = None) -> None:
```

Add after `self._last_request_time = 0.0`:
```python
        self._retry = RetryHelper(retry_config or RetryConfig())
```

- [ ] **Step 2: Wrap HTTP call in `resolve()`**

Replace:
```python
        try:
            response = await self._client.get(url, params={"api_key": self._api_key})
            response.raise_for_status()
```

With:
```python
        try:
            response = await self._retry.execute(lambda: self._client.get(url, params={"api_key": self._api_key}))
            response.raise_for_status()
            logger.info("libraries.io resolved %s/%s successfully", platform, name)
```

- [ ] **Step 3: Run existing libraries.io tests**

Run: `python -m pytest tests/test_librariesio_resolver.py -v`
Expected: PASS

Note: the error tests (`test_timeout_returns_warning`, `test_429_returns_warning`, `test_5xx_returns_warning`, `test_network_error_returns_warning`) will still pass because after `max_attempts=3` the exception is re-raised and caught by the same `except` block. Retry config uses defaults, and the mock `side_effect` will raise the exception on every call, exhausting retries.

- [ ] **Step 4: Commit**

```bash
git add src/purl_resolver/resolver/librariesio.py
git commit -m "feat: add retry support to LibrariesIoResolver"
```

---

### Task 7: Wire `RetryConfig` in factory

**Files:**
- Modify: `src/purl_resolver/resolver/factory.py`

- [ ] **Step 1: Build `RetryConfig` and pass to HTTP resolvers**

Add import at top:
```python
from .retry import RetryConfig
```

After `resolvers: list[Resolver] = [Purl2RepoResolver(...)]`, add:
```python
    retry_config = RetryConfig(
        max_attempts=app_settings.retry_max_attempts,
        base_cooldown_seconds=app_settings.retry_base_cooldown_seconds,
    )
```

Pass to `EcosystemsResolver`:
```python
            EcosystemsResolver(
                api_key=app_settings.ecosystems_api_key,
                max_requests_per_second=app_settings.ecosystems_max_requests_per_second,
                retry_config=retry_config,
            )
```

Pass to `LibrariesIoResolver`:
```python
            LibrariesIoResolver(
                api_key=app_settings.librariesio_api_key,
                retry_config=retry_config,
            )
```

- [ ] **Step 2: Run existing tests that use factory**

Run: `python -m pytest tests/test_api.py tests/test_resolver_interface.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add src/purl_resolver/resolver/factory.py
git commit -m "feat: wire RetryConfig into resolver factory from AppSettings"
```

---

### Task 8: Add retry settings UI

**Files:**
- Modify: `src/purl_resolver/templates/settings.html`

- [ ] **Step 1: Add HTML inputs after ecosyste.ms card, before Save button**

Add before `<button id="save-btn">`:

```html
        <div class="card" style="margin-top:1rem;">
            <div class="card-title">Resolver Behaviour</div>
            <div class="setting-row">
                <div>
                    <div class="setting-label">Max retry attempts</div>
                    <div class="setting-desc">
                        Maximum HTTP request attempts per resolver (including the first).
                        Applied to ecosyste.ms and libraries.io on timeout, rate limit (429), and server errors (5xx).
                        Default: 3. Range: 1–10.
                    </div>
                </div>
                <input type="number" id="retry-attempts-input" min="1" max="10" value="3">
            </div>
            <div class="setting-row">
                <div>
                    <div class="setting-label">Retry cooldown (seconds)</div>
                    <div class="setting-desc">
                        Base wait time between retries. Actual wait = cooldown × (attempt − 1).
                        Example: cooldown=5 → waits 5s before 2nd attempt, 10s before 3rd.
                        Range: 0.5–120 seconds.
                    </div>
                </div>
                <input type="number" id="retry-cooldown-input" min="0.5" max="120" step="0.5" value="5.0">
            </div>
        </div>
```

- [ ] **Step 2: Add JS references in the script tag**

Add after `const ecoRateInput = document.getElementById("ecosystems-rate-input");`:
```javascript
        const retryAttemptsInput = document.getElementById("retry-attempts-input");
        const retryCooldownInput = document.getElementById("retry-cooldown-input");
```

- [ ] **Step 3: Add load logic in `loadSettings()`**

Add after `ecoRateInput.value = data.ecosystems_max_requests_per_second;`:
```javascript
                retryAttemptsInput.value = data.retry_max_attempts;
                retryCooldownInput.value = data.retry_base_cooldown_seconds;
```

- [ ] **Step 4: Add save logic in `saveSettings()`**

Add before `const res = await fetch(...)`:
```javascript
                body.retry_max_attempts = parseInt(retryAttemptsInput.value, 10);
                body.retry_base_cooldown_seconds = parseFloat(retryCooldownInput.value);
```

- [ ] **Step 5: Commit**

```bash
git add src/purl_resolver/templates/settings.html
git commit -m "feat: add retry settings UI to Settings page"
```

---

### Task 9: Update specs

**Files:**
- Modify: `specs/domains/purl-resolution.md`
- Modify: `specs/architecture/layers.md`

- [ ] **Step 1: Update `purl-resolution.md` Configuration table**

Add two rows to the JSON Settings table:

```markdown
| `retry_max_attempts` | `3` | Maximum HTTP request attempts per resolver (1–10). Applied to ecosyste.ms and libraries.io on timeout, 429, and 5xx errors. |
| `retry_base_cooldown_seconds` | `5.0` | Base wait time between retries; actual wait = cooldown × (attempt − 1). Range: 0.5–120. |
```

- [ ] **Step 2: Update `layers.md` Resolver Layer section**

Append to `librariesio.py` description:
```markdown
now with configurable retry (HTTP 429, timeout, 5xx) via RetryHelper
```

Append to `ecosystems.py` description:
```markdown
now with configurable retry (HTTP 429, timeout, 5xx) via RetryHelper
```

Add to Resolver Layer responsibilities list:
```markdown
- **retry.py** — `RetryConfig` dataclass, `RetryableErrorPolicy` (retryable error classification), `RetryHelper` (async retry loop with linear backoff)
```

- [ ] **Step 3: Commit**

```bash
git add specs/domains/purl-resolution.md specs/architecture/layers.md
git commit -m "docs: update specs with retry configuration and RetryHelper module"
```

---

### Task 10: Run full test suite and lint

- [ ] **Step 1: Run all tests**

Run: `python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 2: Run lint**

Run: `python -m ruff check src/ tests/`
Expected: No errors (ruff line-length=100)

- [ ] **Step 3: Commit any fixes if needed**

```bash
git add -A
git commit -m "chore: post-implementation fixes after full test suite run"
```
