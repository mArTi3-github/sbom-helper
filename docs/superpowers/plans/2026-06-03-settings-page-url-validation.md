# Settings Page with URL Validation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Settings page with a URL validation toggle that verifies cached repository URLs before returning them, deleting invalid entries and falling through to resolvers.

**Architecture:** Validation lives in `service.py::resolve_purl()` after `storage.lookup()`. A new `url_validator.py` module performs HEAD + git ls-remote checks. A `settings_store.py` module manages a JSON config file. New API endpoints and a settings page expose the toggle.

**Tech Stack:** Python, FastAPI, httpx (async HTTP), pydantic-settings, asyncpg, Jinja2 templates, pytest

---

## File Structure

| File | Responsibility |
|------|---------------|
| `src/purl_resolver/settings_store.py` | **Create** — JSON config load/save, AppSettings model |
| `src/purl_resolver/url_validator.py` | **Create** — URL validation with HEAD + git ls-remote, rate limit mitigation |
| `src/purl_resolver/templates/settings.html` | **Create** — Settings page UI |
| `src/purl_resolver/service.py` | **Modify** — Add validation logic after cache lookup |
| `src/purl_resolver/router.py` | **Modify** — Add /settings route + GET/PATCH API endpoints |
| `src/purl_resolver/templates/index.html` | **Modify** — Add "Settings" nav link |
| `src/purl_resolver/templates/sbom.html` | **Modify** — Add "Settings" nav link |
| `src/purl_resolver/templates/db-admin.html` | **Modify** — Add "Settings" nav link |
| `tests/test_settings_store.py` | **Create** — SettingsStore unit tests |
| `tests/test_url_validator.py` | **Create** — URL validator unit tests |
| `tests/test_service_validation.py` | **Create** — Service layer validation integration tests |

---

## Task 1: SettingsStore — JSON config persistence

**Files:**
- Create: `src/purl_resolver/settings_store.py`
- Create: `tests/test_settings_store.py`

- [ ] **Step 1: Write failing tests for SettingsStore**

```python
# tests/test_settings_store.py
from __future__ import annotations

import json
import pytest
from pathlib import Path

from purl_resolver.settings_store import SettingsStore, AppSettings


@pytest.fixture
def tmp_settings_file(tmp_path: Path) -> Path:
    return tmp_path / "settings.json"


@pytest.fixture
def store(tmp_settings_file: Path) -> SettingsStore:
    return SettingsStore(path=tmp_settings_file)


class TestAppSettingsDefaults:
    def test_defaults(self):
        s = AppSettings()
        assert s.validate_db_urls is False
        assert s.url_validation_timeout == 5


class TestSettingsStoreLoad:
    def test_file_missing_creates_with_defaults(self, store: SettingsStore, tmp_settings_file: Path):
        result = store.load()
        assert result.validate_db_urls is False
        assert result.url_validation_timeout == 5
        assert tmp_settings_file.exists()

    def test_file_valid_json(self, store: SettingsStore, tmp_settings_file: Path):
        tmp_settings_file.write_text(json.dumps({
            "validate_db_urls": True,
            "url_validation_timeout": 10,
        }))
        result = store.load()
        assert result.validate_db_urls is True
        assert result.url_validation_timeout == 10

    def test_file_corrupt_json(self, store: SettingsStore, tmp_settings_file: Path):
        tmp_settings_file.write_text("not json {{{")
        result = store.load()
        assert result.validate_db_urls is False
        assert result.url_validation_timeout == 5


class TestSettingsStoreSave:
    def test_save_and_load_roundtrip(self, store: SettingsStore):
        original = AppSettings(validate_db_urls=True, url_validation_timeout=15)
        store.save(original)
        loaded = store.load()
        assert loaded.validate_db_urls is True
        assert loaded.url_validation_timeout == 15

    def test_save_creates_parent_dirs(self, tmp_path: Path):
        nested = tmp_path / "sub" / "dir" / "settings.json"
        store = SettingsStore(path=nested)
        store.save(AppSettings())
        assert nested.exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_settings_store.py -v`
Expected: FAIL — module `purl_resolver.settings_store` not found

- [ ] **Step 3: Implement SettingsStore**

```python
# src/purl_resolver/settings_store.py
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class AppSettings(BaseModel):
    validate_db_urls: bool = False
    url_validation_timeout: int = 5


class SettingsStore:

    def __init__(self, path: str | Path | None = None) -> None:
        if path is None:
            path = os.environ.get("SETTINGS_FILE", "./data/settings.json")
        self._path = Path(path)

    def load(self) -> AppSettings:
        if not self._path.exists():
            self._ensure_parent()
            defaults = AppSettings()
            self._write(defaults)
            return defaults

        try:
            raw = self._path.read_text(encoding="utf-8")
            data = json.loads(raw)
            return AppSettings(**data)
        except (json.JSONDecodeError, Exception) as exc:
            logger.warning("Corrupt settings file at %s, using defaults: %s", self._path, exc)
            return AppSettings()

    def save(self, settings: AppSettings) -> None:
        self._ensure_parent()
        self._write(settings)

    def _ensure_parent(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _write(self, settings: AppSettings) -> None:
        self._path.write_text(
            json.dumps(settings.model_dump(), indent=2) + "\n",
            encoding="utf-8",
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_settings_store.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/purl_resolver/settings_store.py tests/test_settings_store.py
git commit -m "feat: add SettingsStore for JSON config persistence"
```

---

## Task 2: URL Validator — HEAD + git ls-remote with rate limit mitigation

**Files:**
- Create: `src/purl_resolver/url_validator.py`
- Create: `tests/test_url_validator.py`

- [ ] **Step 1: Write failing tests for URL validator**

```python
# tests/test_url_validator.py
from __future__ import annotations

import asyncio
from enum import Enum
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from purl_resolver.url_validator import UrlValidationResult, validate_url, _RateLimitTracker


@pytest.fixture(autouse=True)
def reset_rate_limit_tracker():
    _RateLimitTracker._count = 0
    _RateLimitTracker._cooldown_until = 0.0
    yield
    _RateLimitTracker._count = 0
    _RateLimitTracker._cooldown_until = 0.0


def _mock_response(status: int = 200, headers: dict | None = None) -> AsyncMock:
    resp = AsyncMock()
    resp.status = status
    resp.headers = headers or {}
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


def _mock_head(status: int = 200, headers: dict | None = None):
    """Return a context manager that yields a mock response."""
    resp = _mock_response(status, headers)
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=resp)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


class TestValidateUrl:
    @pytest.mark.asyncio
    async def test_valid_url(self):
        with patch("purl_resolver.url_validator._check_connectivity", new_callable=AsyncMock, return_value=True), \
             patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head, \
             patch("purl_resolver.url_validator._git_ls_remote", new_callable=AsyncMock, return_value=True):
            mock_head.return_value = _mock_head(200)
            result = await validate_url("https://github.com/psf/requests", timeout=5)
            assert result == UrlValidationResult.VALID

    @pytest.mark.asyncio
    async def test_head_404_returns_invalid(self):
        with patch("purl_resolver.url_validator._check_connectivity", new_callable=AsyncMock, return_value=True), \
             patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head:
            mock_head.return_value = _mock_head(404)
            result = await validate_url("https://github.com/deleted/repo", timeout=5)
            assert result == UrlValidationResult.INVALID

    @pytest.mark.asyncio
    async def test_head_403_without_rate_limit_headers_returns_invalid(self):
        with patch("purl_resolver.url_validator._check_connectivity", new_callable=AsyncMock, return_value=True), \
             patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head:
            mock_head.return_value = _mock_head(403, {"x-github-media-type": "v3"})
            result = await validate_url("https://github.com/private/repo", timeout=5)
            assert result == UrlValidationResult.INVALID

    @pytest.mark.asyncio
    async def test_head_403_with_rate_limit_remaining_zero_returns_rate_limited(self):
        with patch("purl_resolver.url_validator._check_connectivity", new_callable=AsyncMock, return_value=True), \
             patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head:
            mock_head.return_value = _mock_head(403, {"x-ratelimit-remaining": "0"})
            result = await validate_url("https://github.com/psf/requests", timeout=5)
            assert result == UrlValidationResult.RATE_LIMITED

    @pytest.mark.asyncio
    async def test_head_429_returns_rate_limited(self):
        with patch("purl_resolver.url_validator._check_connectivity", new_callable=AsyncMock, return_value=True), \
             patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head:
            mock_head.return_value = _mock_head(429)
            result = await validate_url("https://github.com/psf/requests", timeout=5)
            assert result == UrlValidationResult.RATE_LIMITED

    @pytest.mark.asyncio
    async def test_head_connection_error_returns_invalid(self):
        with patch("purl_resolver.url_validator._check_connectivity", new_callable=AsyncMock, return_value=True), \
             patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head:
            mock_head.side_effect = Exception("Connection refused")
            result = await validate_url("https://github.com/deleted/repo", timeout=5)
            assert result == UrlValidationResult.INVALID

    @pytest.mark.asyncio
    async def test_connectivity_probe_fails_returns_network_error(self):
        with patch("purl_resolver.url_validator._check_connectivity", new_callable=AsyncMock, return_value=False):
            result = await validate_url("https://github.com/psf/requests", timeout=5)
            assert result == UrlValidationResult.NETWORK_ERROR

    @pytest.mark.asyncio
    async def test_git_ls_remote_fails_returns_invalid(self):
        with patch("purl_resolver.url_validator._check_connectivity", new_callable=AsyncMock, return_value=True), \
             patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head, \
             patch("purl_resolver.url_validator._git_ls_remote", new_callable=AsyncMock, return_value=False):
            mock_head.return_value = _mock_head(200)
            result = await validate_url("https://github.com/deleted/repo", timeout=5)
            assert result == UrlValidationResult.INVALID

    @pytest.mark.asyncio
    async def test_rate_limit_cooldown_skips_validation(self):
        _RateLimitTracker._count = 5
        import time
        _RateLimitTracker._cooldown_until = time.time() + 60
        result = await validate_url("https://github.com/psf/requests", timeout=5)
        assert result == UrlValidationResult.VALID
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_url_validator.py -v`
Expected: FAIL — module `purl_resolver.url_validator` not found

- [ ] **Step 3: Implement URL validator**

```python
# src/purl_resolver/url_validator.py
from __future__ import annotations

import asyncio
import logging
import subprocess
import time
from enum import Enum

logger = logging.getLogger(__name__)

_CONNECTIVITY_URL = "https://github.com"
_CONNECTIVITY_TIMEOUT = 2
_RATE_LIMIT_THRESHOLD = 5
_RATE_LIMIT_COOLDOWN = 60


class UrlValidationResult(Enum):
    VALID = "valid"
    INVALID = "invalid"
    NETWORK_ERROR = "network_error"
    RATE_LIMITED = "rate_limited"


class _RateLimitTracker:
    _count: int = 0
    _cooldown_until: float = 0.0

    @classmethod
    def is_in_cooldown(cls) -> bool:
        if cls._cooldown_until > 0 and time.time() >= cls._cooldown_until:
            logger.info("Rate limit cooldown expired")
            cls._count = 0
            cls._cooldown_until = 0.0
        return cls._cooldown_until > 0 and time.time() < cls._cooldown_until

    @classmethod
    def record_rate_limit(cls) -> None:
        cls._count += 1
        if cls._count >= _RATE_LIMIT_THRESHOLD:
            cls._cooldown_until = time.time() + _RATE_LIMIT_COOLDOWN
            logger.warning(
                "Rate limit threshold reached (%d consecutive), "
                "entering %ds cooldown",
                cls._count, _RATE_LIMIT_COOLDOWN,
            )

    @classmethod
    def reset(cls) -> None:
        cls._count = 0
        cls._cooldown_until = 0.0


def _is_rate_limited(status: int, headers: dict) -> bool:
    if status == 429:
        return True
    if status == 403:
        remaining = headers.get("x-ratelimit-remaining") or headers.get("X-RateLimit-Remaining")
        if remaining is not None and int(remaining) <= 0:
            return True
    return False


async def _check_connectivity() -> bool:
    try:
        import httpx
        async with httpx.AsyncClient(timeout=_CONNECTIVITY_TIMEOUT) as client:
            resp = await client.head(_CONNECTIVITY_URL)
            return resp.status_code < 500
    except Exception:
        logger.warning("Connectivity probe to %s failed", _CONNECTIVITY_URL)
        return False


async def _head_request(url: str, timeout: int):
    import httpx
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        return await client.head(url)


async def _git_ls_remote(url: str, timeout: int) -> bool:
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "ls-remote", "--exit-code", url,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            logger.warning("git ls-remote timed out for %s", url)
            return False
        return proc.returncode == 0
    except FileNotFoundError:
        logger.warning("git not found, skipping git ls-remote check")
        return True


async def validate_url(url: str, timeout: int) -> UrlValidationResult:
    if _RateLimitTracker.is_in_cooldown():
        return UrlValidationResult.VALID

    try:
        github_ok = await _check_connectivity()
    except Exception:
        return UrlValidationResult.NETWORK_ERROR

    if not github_ok:
        return UrlValidationResult.NETWORK_ERROR

    try:
        resp = await _head_request(url, timeout)
        headers = dict(resp.headers)
        status = resp.status
    except Exception:
        _RateLimitTracker.reset()
        return UrlValidationResult.INVALID

    if _is_rate_limited(status, headers):
        _RateLimitTracker.record_rate_limit()
        return UrlValidationResult.RATE_LIMITED

    _RateLimitTracker.reset()

    if status in (404, 405):
        return UrlValidationResult.INVALID
    if status == 403:
        return UrlValidationResult.INVALID
    if status >= 400:
        return UrlValidationResult.INVALID

    git_ok = await _git_ls_remote(url, timeout)
    if not git_ok:
        return UrlValidationResult.INVALID

    return UrlValidationResult.VALID
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_url_validator.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/purl_resolver/url_validator.py tests/test_url_validator.py
git commit -m "feat: add URL validator with HEAD + git ls-remote and rate limit mitigation"
```

---

## Task 3: Service Layer — integrate validation after cache lookup

**Files:**
- Modify: `src/purl_resolver/service.py`
- Create: `tests/test_service_validation.py`

- [ ] **Step 1: Write failing tests for validation integration**

```python
# tests/test_service_validation.py
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from purl_resolver.schemas import ResolveResponse, ResolveResult
from purl_resolver.service import resolve_purl
from purl_resolver.url_validator import UrlValidationResult


def _cached_response(purl: str = "pkg:pypi/requests", days_ago: int = 0) -> ResolveResponse:
    resolved_at = (datetime.now() - timedelta(days=days_ago)).isoformat()
    return ResolveResponse(
        purl=purl,
        repository_url="https://github.com/psf/requests",
        resolved_at=resolved_at,
    )


@pytest.fixture
def mock_storage():
    storage = AsyncMock()
    storage.lookup = AsyncMock(return_value=None)
    storage.store = AsyncMock()
    storage.delete_purls = AsyncMock(return_value=1)
    return storage


@pytest.fixture
def mock_settings_store():
    store = MagicMock()
    store.load = MagicMock(return_value=MagicMock(validate_db_urls=True, url_validation_timeout=5))
    return store


@pytest.fixture
def resolver():
    r = MagicMock()
    r.resolve = MagicMock(return_value=MagicMock(
        repository_url="https://github.com/new/repo",
        repository_type="git",
        repository_kind="github",
        confidence="high",
        evidence=["test"],
        warnings=[],
        version_reference=None,
    ))
    return r


class TestValidationIntegration:
    @pytest.mark.asyncio
    async def test_valid_url_updates_resolved_at(self, mock_storage, mock_settings_store):
        mock_storage.lookup.return_value = _cached_response(days_ago=3)
        with patch("purl_resolver.service.validate_url", new_callable=AsyncMock, return_value=UrlValidationResult.VALID):
            result = await resolve_purl(
                "pkg:pypi/requests", mock_storage, [],
                settings_store=mock_settings_store,
            )
            assert result.response is not None
            mock_storage.store.assert_called_once()
            mock_storage.delete_purls.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_url_deletes_and_falls_through(self, mock_storage, mock_settings_store, resolver):
        mock_storage.lookup.return_value = _cached_response(days_ago=3)
        with patch("purl_resolver.service.validate_url", new_callable=AsyncMock, return_value=UrlValidationResult.INVALID):
            result = await resolve_purl(
                "pkg:pypi/requests", mock_storage, [resolver],
                settings_store=mock_settings_store,
            )
            mock_storage.delete_purls.assert_called_once_with(["pkg:pypi/requests"])
            resolver.resolve.assert_called_once()

    @pytest.mark.asyncio
    async def test_network_error_returns_cached(self, mock_storage, mock_settings_store):
        mock_storage.lookup.return_value = _cached_response(days_ago=3)
        with patch("purl_resolver.service.validate_url", new_callable=AsyncMock, return_value=UrlValidationResult.NETWORK_ERROR):
            result = await resolve_purl(
                "pkg:pypi/requests", mock_storage, [],
                settings_store=mock_settings_store,
            )
            assert result.response is not None
            mock_storage.store.assert_not_called()
            mock_storage.delete_purls.assert_not_called()

    @pytest.mark.asyncio
    async def test_rate_limited_returns_cached(self, mock_storage, mock_settings_store):
        mock_storage.lookup.return_value = _cached_response(days_ago=3)
        with patch("purl_resolver.service.validate_url", new_callable=AsyncMock, return_value=UrlValidationResult.RATE_LIMITED):
            result = await resolve_purl(
                "pkg:pypi/requests", mock_storage, [],
                settings_store=mock_settings_store,
            )
            assert result.response is not None
            mock_storage.store.assert_not_called()

    @pytest.mark.asyncio
    async def test_validate_db_urls_false_skips_validation(self, mock_storage):
        mock_storage.lookup.return_value = _cached_response(days_ago=3)
        settings_store = MagicMock()
        settings_store.load = MagicMock(return_value=MagicMock(validate_db_urls=False))
        with patch("purl_resolver.service.validate_url", new_callable=AsyncMock) as mock_validate:
            result = await resolve_purl(
                "pkg:pypi/requests", mock_storage, [],
                settings_store=settings_store,
            )
            mock_validate.assert_not_called()

    @pytest.mark.asyncio
    async def test_resolved_at_today_skips_validation(self, mock_storage, mock_settings_store):
        mock_storage.lookup.return_value = _cached_response(days_ago=0)
        with patch("purl_resolver.service.validate_url", new_callable=AsyncMock) as mock_validate:
            result = await resolve_purl(
                "pkg:pypi/requests", mock_storage, [],
                settings_store=mock_settings_store,
            )
            mock_validate.assert_not_called()

    @pytest.mark.asyncio
    async def test_settings_store_none_skips_validation(self, mock_storage):
        mock_storage.lookup.return_value = _cached_response(days_ago=3)
        with patch("purl_resolver.service.validate_url", new_callable=AsyncMock) as mock_validate:
            result = await resolve_purl("pkg:pypi/requests", mock_storage, [])
            mock_validate.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_service_validation.py -v`
Expected: FAIL — `resolve_purl()` doesn't accept `settings_store` parameter

- [ ] **Step 3: Modify service.py to add validation**

Add `from datetime import datetime` at the top of `service.py` (next to existing imports).

Then modify `resolve_purl()` — add `settings_store=None` parameter and insert validation logic after cache lookup:
    try:
        cached = await storage.lookup(purl_key)
        if cached is not None:
            logger.info("Cache hit for %s", purl_key)

            # --- URL validation ---
            if settings_store is not None:
                from datetime import date
                from .settings_store import AppSettings
                app_settings = settings_store.load()
                if app_settings.validate_db_urls:
                    resolved_date = None
                    if cached.resolved_at:
                        try:
                            resolved_date = datetime.fromisoformat(cached.resolved_at).date()
                        except (ValueError, TypeError):
                            pass
                    if resolved_date != date.today():
                        from .url_validator import validate_url, UrlValidationResult
                        vresult = await validate_url(
                            cached.repository_url,
                            app_settings.url_validation_timeout,
                        )
                        if vresult == UrlValidationResult.VALID:
                            try:
                                await storage.store(cached)
                            except Exception:
                                logger.warning(
                                    "Failed to update resolved_at for %s",
                                    purl_key, exc_info=True,
                                )
                        elif vresult == UrlValidationResult.INVALID:
                            try:
                                await storage.delete_purls([purl_key])
                            except Exception:
                                logger.warning(
                                    "Failed to delete invalid URL for %s",
                                    purl_key, exc_info=True,
                                )
                            cached = None
                        # NETWORK_ERROR and RATE_LIMITED: return cached as-is
            # --- end URL validation ---

            if cached is not None:
                return ResolveResult.ok(cached)
    except Exception:
        logger.warning(
            "Cache lookup failed for %s, falling through to resolver",
            purl_key,
            exc_info=True,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_service_validation.py -v`
Expected: All PASS

- [ ] **Step 5: Run full test suite**

Run: `.venv/bin/pytest tests/ -v`
Expected: All PASS (no regressions)

- [ ] **Step 6: Commit**

```bash
git add src/purl_resolver/service.py tests/test_service_validation.py
git commit -m "feat: integrate URL validation into service layer after cache lookup"
```

---

## Task 4: API endpoints — GET/PATCH /api/v1/settings

**Files:**
- Modify: `src/purl_resolver/router.py`
- Modify: `src/purl_resolver/main.py`

- [ ] **Step 1: Add SettingsStore to app lifespan in main.py**

```python
# In main.py, add import at top:
from .settings_store import SettingsStore

# In lifespan(), after resolvers are configured (after line 40), add:
    app.state.settings_store = SettingsStore()
```

- [ ] **Step 2: Add settings API endpoints to router.py**

```python
# Add import at top of router.py:
from .settings_store import SettingsStore, AppSettings
from pydantic import BaseModel, Field

# Add Pydantic model for partial update:
class SettingsUpdate(BaseModel):
    validate_db_urls: bool | None = None
    url_validation_timeout: int | None = Field(None, ge=1, le=60)

# Add endpoints before the closing of router.py:

@router.get("/api/v1/settings")
async def get_settings(request: Request) -> JSONResponse:
    store: SettingsStore = request.app.state.settings_store
    settings = store.load()
    return JSONResponse(content=settings.model_dump())


@router.patch("/api/v1/settings")
async def update_settings(body: SettingsUpdate, request: Request) -> JSONResponse:
    store: SettingsStore = request.app.state.settings_store
    current = store.load()
    update_data = body.model_dump(exclude_unset=True)
    if update_data:
        updated = current.model_copy(update=update_data)
        store.save(updated)
    else:
        updated = current
    return JSONResponse(content=updated.model_dump())
```

- [ ] **Step 3: Add resolve_purl call with settings_store in router.py**

```python
# In resolve_endpoint(), change the resolve_purl call to pass settings_store:
    from .settings_store import SettingsStore
    settings_store: SettingsStore = request.app.state.settings_store
    result = await resolve_purl(
        purl=body.purl,
        storage=request.app.state.storage,
        resolvers=request.app.state.resolvers,
        settings_store=settings_store,
    )
```

- [ ] **Step 4: Run tests to verify endpoints work**

Run: `.venv/bin/pytest tests/ -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/purl_resolver/router.py src/purl_resolver/main.py
git commit -m "feat: add GET/PATCH /api/v1/settings endpoints"
```

---

## Task 5: Settings page UI + nav-bar updates

**Files:**
- Create: `src/purl_resolver/templates/settings.html`
- Modify: `src/purl_resolver/templates/index.html:81-85`
- Modify: `src/purl_resolver/templates/sbom.html:74-78`
- Modify: `src/purl_resolver/templates/db-admin.html:128-132`
- Modify: `src/purl_resolver/router.py`

- [ ] **Step 1: Add settings page route to router.py**

```python
# Add before or after the db_admin_page route:
@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="settings.html")
```

- [ ] **Step 2: Create settings.html template**

```html
<!-- src/purl_resolver/templates/settings.html -->
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Settings — sbom-helper</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #f5f5f5; color: #1a1a1a; line-height: 1.6;
            min-height: 100vh; display: flex; flex-direction: column;
        }
        .container { max-width: 720px; margin: 0 auto; padding: 2rem 1rem; flex: 1; }
        h1 { font-size: 1.5rem; margin-bottom: 0.25rem; }
        .subtitle { color: #666; margin-bottom: 1.5rem; }
        .card {
            background: #fff; border: 1px solid #e5e7eb; border-radius: 8px;
            padding: 1.5rem; box-shadow: 0 1px 3px rgba(0,0,0,0.08);
        }
        .card-title { font-size: 0.75rem; text-transform: uppercase; color: #888; margin-bottom: 1rem; }
        .setting-row {
            display: flex; align-items: center; justify-content: space-between;
            padding: 0.75rem 0; border-bottom: 1px solid #f3f4f6;
        }
        .setting-row:last-child { border-bottom: none; }
        .setting-label { font-weight: 500; }
        .setting-desc { font-size: 0.85rem; color: #666; margin-top: 0.25rem; }
        .toggle {
            position: relative; width: 48px; height: 26px; cursor: pointer;
        }
        .toggle input { opacity: 0; width: 0; height: 0; }
        .toggle-slider {
            position: absolute; top: 0; left: 0; right: 0; bottom: 0;
            background: #ccc; border-radius: 26px; transition: background 0.2s;
        }
        .toggle-slider::before {
            content: ""; position: absolute; height: 20px; width: 20px;
            left: 3px; bottom: 3px; background: white; border-radius: 50%;
            transition: transform 0.2s;
        }
        .toggle input:checked + .toggle-slider { background: #2563eb; }
        .toggle input:checked + .toggle-slider::before { transform: translateX(22px); }
        input[type="number"] {
            width: 80px; padding: 0.5rem; border: 1px solid #ccc;
            border-radius: 6px; font-size: 0.9rem; text-align: center;
        }
        input[type="number"]:focus { outline: none; border-color: #2563eb; }
        button {
            padding: 0.75rem 1.5rem; background: #2563eb; color: #fff;
            border: none; border-radius: 6px; font-size: 1rem; cursor: pointer;
            margin-top: 1rem;
        }
        button:hover { background: #1d4ed8; }
        .msg { margin-top: 0.75rem; padding: 0.75rem; border-radius: 6px; display: none; }
        .msg-ok { background: #dcfce7; color: #166534; }
        .msg-err { background: #fee2e2; color: #991b1b; }
        footer { text-align: center; padding: 1rem; color: #999; font-size: 0.8rem; }
    </style>
</head>
<body>
    <div class="container">
        <h1>sbom-helper</h1>
        <p class="subtitle">Application settings</p>
        <div style="margin-bottom:1rem;display:flex;gap:1rem;">
            <a href="/" style="color:#2563eb;text-decoration:none;font-size:0.9rem;">PURL Resolver</a>
            <a href="/sbom-updater" style="color:#2563eb;text-decoration:none;font-size:0.9rem;">SBOM Updater</a>
            <a href="/db-admin" style="color:#2563eb;text-decoration:none;font-size:0.9rem;">Database Admin</a>
            <a href="/settings" style="text-decoration:none;color:inherit;font-weight:600;font-size:0.9rem;">Settings</a>
        </div>

        <div class="card">
            <div class="card-title">URL Validation</div>
            <div class="setting-row">
                <div>
                    <div class="setting-label">Validate URLs from local database</div>
                    <div class="setting-desc">
                        When enabled, repository URLs found in the local database are verified
                        (HTTP HEAD + git ls-remote) before being returned. Invalid URLs are
                        deleted and resolution continues through the resolver chain.
                    </div>
                </div>
                <label class="toggle">
                    <input type="checkbox" id="validate-toggle">
                    <span class="toggle-slider"></span>
                </label>
            </div>
            <div class="setting-row">
                <div>
                    <div class="setting-label">Validation timeout (seconds)</div>
                    <div class="setting-desc">
                        Timeout for each HTTP HEAD and git ls-remote check (1–60 seconds).
                    </div>
                </div>
                <input type="number" id="timeout-input" min="1" max="60" value="5">
            </div>
        </div>

        <button id="save-btn">Save</button>
        <div id="msg" class="msg"></div>
    </div>

    <footer>sbom-helper — Settings</footer>

    <script>
        const toggle = document.getElementById("validate-toggle");
        const timeoutInput = document.getElementById("timeout-input");
        const saveBtn = document.getElementById("save-btn");
        const msgDiv = document.getElementById("msg");

        async function loadSettings() {
            try {
                const res = await fetch("/api/v1/settings");
                const data = await res.json();
                toggle.checked = data.validate_db_urls;
                timeoutInput.value = data.url_validation_timeout;
            } catch {
                showMessage("Failed to load settings", true);
            }
        }

        async function saveSettings() {
            saveBtn.disabled = true;
            try {
                const res = await fetch("/api/v1/settings", {
                    method: "PATCH",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        validate_db_urls: toggle.checked,
                        url_validation_timeout: parseInt(timeoutInput.value, 10),
                    }),
                });
                if (res.ok) {
                    showMessage("Settings saved", false);
                } else {
                    showMessage("Failed to save settings", true);
                }
            } catch {
                showMessage("Network error", true);
            } finally {
                saveBtn.disabled = false;
            }
        }

        function showMessage(text, isError) {
            msgDiv.textContent = text;
            msgDiv.className = "msg " + (isError ? "msg-err" : "msg-ok");
            msgDiv.style.display = "block";
            setTimeout(() => { msgDiv.style.display = "none"; }, 3000);
        }

        saveBtn.addEventListener("click", saveSettings);
        loadSettings();
    </script>
</body>
</html>
```

- [ ] **Step 3: Add "Settings" nav link to index.html**

In `src/purl_resolver/templates/index.html`, after line 84 (the Database Admin link), add:
```html
            <a href="/settings" style="color:#2563eb;text-decoration:none;font-size:0.9rem;">Settings</a>
```

- [ ] **Step 4: Add "Settings" nav link to sbom.html**

In `src/purl_resolver/templates/sbom.html`, after line 77 (the Database Admin link), add:
```html
            <a href="/settings" style="color:#2563eb;text-decoration:none;font-size:0.9rem;">Settings</a>
```

- [ ] **Step 5: Add "Settings" nav link to db-admin.html**

In `src/purl_resolver/templates/db-admin.html`, after line 131 (the Database Admin link), add:
```html
            <a href="/settings">Settings</a>
```

- [ ] **Step 6: Verify app starts and settings page loads**

Run: `.venv/bin/python -m purl_resolver.main` (in background)
Open: `http://localhost:8000/settings`
Expected: Settings page renders with toggle and timeout input

- [ ] **Step 7: Commit**

```bash
git add src/purl_resolver/templates/settings.html src/purl_resolver/templates/index.html src/purl_resolver/templates/sbom.html src/purl_resolver/templates/db-admin.html src/purl_resolver/router.py
git commit -m "feat: add Settings page UI with nav links on all pages"
```

---

## Task 6: Wire settings_store into resolve_batch and SBOM enrichment

**Files:**
- Modify: `src/purl_resolver/service.py`
- Modify: `src/purl_resolver/router.py`

- [ ] **Step 1: Pass settings_store through resolve_batch**

In `service.py`, modify `resolve_batch()` signature and the internal `_resolve_one` call:

```python
async def resolve_batch(
    purls: list[str],
    storage: Storage,
    resolvers: list[Resolver],
    settings_store=None,
) -> dict[str, str]:
    semaphore = asyncio.Semaphore(_BATCH_SEMAPHORE_LIMIT)

    async def _resolve_one(original: str) -> tuple[str, str | None]:
        async with semaphore:
            result = await resolve_purl(original, storage, resolvers, settings_store=settings_store)
            key = safe_normalize(original)
            if result.response and result.response.repository_url:
                return (key, result.response.repository_url)
            return (key, None)
    # ... rest unchanged
```

- [ ] **Step 2: Pass settings_store in router.py SBOM endpoint**

In `router.py`, `resolve_sbom_endpoint()`, change the `resolve_batch` call:

```python
    from .settings_store import SettingsStore
    settings_store: SettingsStore = request.app.state.settings_store
    resolved = await resolve_batch(unique_purls, storage, resolvers, settings_store=settings_store)
```

- [ ] **Step 3: Run full test suite**

Run: `.venv/bin/pytest tests/ -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add src/purl_resolver/service.py src/purl_resolver/router.py
git commit -m "feat: pass settings_store through batch resolution and SBOM enrichment"
```

---

## Task 7: Final verification and cleanup

- [ ] **Step 1: Run full test suite**

Run: `.venv/bin/pytest tests/ -v`
Expected: All PASS

- [ ] **Step 2: Verify no import errors**

Run: `.venv/bin/python -c "from purl_resolver.main import app; print('OK')"`
Expected: OK

- [ ] **Step 3: Verify lint/typecheck if configured**

Run: `.venv/bin/python -m py_compile src/purl_resolver/settings_store.py && .venv/bin/python -m py_compile src/purl_resolver/url_validator.py && echo "OK"`
Expected: OK

- [ ] **Step 4: Final commit if needed**

```bash
git status
# If uncommitted changes remain:
git add -A && git commit -m "chore: final cleanup for settings page feature"
```
