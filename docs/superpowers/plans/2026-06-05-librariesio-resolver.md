# Libraries.io Resolver Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional libraries.io resolver as a fallback after purl2repo, configurable via the Settings page.

**Architecture:** New `LibrariesIoResolver` class implementing the `Resolver` protocol, registered in the resolver chain after purl2repo. Settings page gets a new card with enable/disable checkbox and API key input. The resolver uses synchronous `httpx.Client` with a `time.sleep()`-based rate limiter.

**Tech Stack:** Python, httpx, FastAPI, Jinja2 templates, Pydantic, pytest

---

### Task 1: Add `Resolver.name` property to the interface

**Files:**
- Modify: `src/purl_resolver/resolver/interface.py`
- Test: `tests/test_resolver_interface.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_resolver_interface.py`:

```python
from __future__ import annotations

from purl_resolver.resolver.interface import Resolution, Resolver


class DummyResolver(Resolver):
    @property
    def name(self) -> str:
        return "dummy"

    def resolve(self, purl: str) -> Resolution:
        return Resolution(purl=purl, repository_url="https://example.com")


class TestResolverName:
    def test_name_property(self) -> None:
        r = DummyResolver()
        assert r.name == "dummy"

    def test_subclass_must_implement_name(self) -> None:
        import pytest
        with pytest.raises(TypeError):
            Resolver()  # type: ignore[abstract]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_resolver_interface.py -v`
Expected: FAIL — `DummyResolver` doesn't implement `name`, or `Resolver` can't be instantiated

- [ ] **Step 3: Implement `name` property in interface.py**

Edit `src/purl_resolver/resolver/interface.py`:

```python
class Resolver(ABC):

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def resolve(self, purl: str) -> Resolution: ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_resolver_interface.py -v`
Expected: PASS

- [ ] **Step 5: Add `name` to `Purl2RepoResolver`**

Edit `src/purl_resolver/resolver/purl2repo.py` — add after line 22:

```python
class Purl2RepoResolver(Resolver):

    @property
    def name(self) -> str:
        return "purl2repo"
```

- [ ] **Step 6: Add `name` to `FakeResolver` in tests**

Edit `tests/helpers.py` — add to `FakeResolver`:

```python
class FakeResolver(Resolver):
    def __init__(self, resolution: Resolution | None = None, error: Exception | None = None) -> None:
        self._resolution = resolution
        self._error = error
        self.call_count = 0

    @property
    def name(self) -> str:
        return "fake"

    def resolve(self, purl: str) -> Resolution:
        self.call_count += 1
        if self._error:
            raise self._error
        if self._resolution:
            return self._resolution
        return Resolution(purl=purl)
```

- [ ] **Step 7: Run all existing tests to verify nothing broke**

Run: `.venv/bin/pytest tests/ -v`
Expected: PASS (all existing tests still pass)

- [ ] **Step 8: Commit**

```bash
git add src/purl_resolver/resolver/interface.py src/purl_resolver/resolver/purl2repo.py tests/helpers.py tests/test_resolver_interface.py
git commit -m "feat: add Resolver.name property for resolver identification"
```

---

### Task 2: Create `LibrariesIoResolver`

**Files:**
- Create: `src/purl_resolver/resolver/librariesio.py`
- Test: `tests/test_librariesio_resolver.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_librariesio_resolver.py`:

```python
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import httpx
import pytest

from purl_resolver.resolver.interface import Resolution
from purl_resolver.resolver.librariesio import LibrariesIoResolver


class TestEcosystemMapping:
    def test_pypi_maps_to_pyPI(self) -> None:
        assert LibrariesIoResolver.ECOSYSTEM_MAP["pypi"] == "PyPI"

    def test_npm_maps_to_NPM(self) -> None:
        assert LibrariesIoResolver.ECOSYSTEM_MAP["npm"] == "NPM"

    def test_nuget_maps_to_NuGet(self) -> None:
        assert LibrariesIoResolver.ECOSYSTEM_MAP["nuget"] == "NuGet"

    def test_gem_maps_to_RubyGems(self) -> None:
        assert LibrariesIoResolver.ECOSYSTEM_MAP["gem"] == "RubyGems"

    def test_golang_maps_to_Go(self) -> None:
        assert LibrariesIoResolver.ECOSYSTEM_MAP["golang"] == "Go"

    def test_maven_maps_to_Maven(self) -> None:
        assert LibrariesIoResolver.ECOSYSTEM_MAP["maven"] == "Maven"

    def test_cargo_maps_to_Cargo(self) -> None:
        assert LibrariesIoResolver.ECOSYSTEM_MAP["cargo"] == "Cargo"

    def test_unknown_type_returns_none(self) -> None:
        assert LibrariesIoResolver.ECOSYSTEM_MAP.get("unknown") is None


class TestResolverName:
    def test_name_is_libraries_io(self) -> None:
        r = LibrariesIoResolver(api_key="test_key")
        assert r.name == "libraries.io"


class TestResolveUnknownType:
    def test_unknown_purl_type_returns_warning(self) -> None:
        r = LibrariesIoResolver(api_key="test_key")
        result = r.resolve("pkg:deb/debian/libssl")
        assert result.repository_url is None
        assert len(result.warnings) > 0
        assert "Unsupported" in result.warnings[0] or "unsupported" in result.warnings[0].lower()


class TestResolveSuccess:
    def test_successful_resolution(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "name": "requests",
            "repository": {
                "url": "https://github.com/psf/requests",
                "homepage": "https://requests.readthedocs.io",
            },
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_response

        r = LibrariesIoResolver(api_key="test_key")
        r._client = mock_client

        result = r.resolve("pkg:pypi/requests@2.31.0")
        assert result.repository_url == "https://github.com/psf/requests"
        assert result.repository_kind == "source"
        assert result.confidence == "medium"
        assert "libraries.io:pypi/requests" in result.evidence


class TestResolveNoRepository:
    def test_no_repository_in_response(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "name": "some-package",
            "repository": None,
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_response

        r = LibrariesIoResolver(api_key="test_key")
        r._client = mock_client

        result = r.resolve("pkg:pypi/some-package")
        assert result.repository_url is None
        assert any("no repository" in w.lower() for w in result.warnings)


class TestResolveErrors:
    def test_timeout_returns_warning(self) -> None:
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.side_effect = httpx.TimeoutException("timeout")

        r = LibrariesIoResolver(api_key="test_key")
        r._client = mock_client

        result = r.resolve("pkg:pypi/requests")
        assert result.repository_url is None
        assert any("timeout" in w.lower() for w in result.warnings)

    def test_429_returns_warning(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "rate limited", request=MagicMock(), response=mock_response
        )

        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_response

        r = LibrariesIoResolver(api_key="test_key")
        r._client = mock_client

        result = r.resolve("pkg:pypi/requests")
        assert result.repository_url is None
        assert any("rate" in w.lower() or "429" in w for w in result.warnings)

    def test_5xx_returns_warning(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "server error", request=MagicMock(), response=mock_response
        )

        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_response

        r = LibrariesIoResolver(api_key="test_key")
        r._client = mock_client

        result = r.resolve("pkg:pypi/requests")
        assert result.repository_url is None
        assert any("500" in w or "error" in w.lower() for w in result.warnings)

    def test_network_error_returns_warning(self) -> None:
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.side_effect = httpx.ConnectError("connection refused")

        r = LibrariesIoResolver(api_key="test_key")
        r._client = mock_client

        result = r.resolve("pkg:pypi/requests")
        assert result.repository_url is None
        assert len(result.warnings) > 0


class TestRateLimiting:
    def test_minimum_interval_between_requests(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"name": "pkg", "repository": {"url": "https://example.com"}}
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_response

        r = LibrariesIoResolver(api_key="test_key")
        r._client = mock_client
        r._min_interval = 0.1  # short interval for testing

        start = time.monotonic()
        r.resolve("pkg:pypi/requests")
        r.resolve("pkg:npm/express")
        elapsed = time.monotonic() - start

        assert elapsed >= 0.1  # at least min_interval between calls
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_librariesio_resolver.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'purl_resolver.resolver.librariesio'`

- [ ] **Step 3: Implement LibrariesIoResolver**

Create `src/purl_resolver/resolver/librariesio.py`:

```python
from __future__ import annotations

import logging
import time

import httpx

from .interface import Resolution, Resolver

logger = logging.getLogger(__name__)

_API_BASE = "https://libraries.io/api"


class LibrariesIoResolver(Resolver):

    ECOSYSTEM_MAP: dict[str, str] = {
        "nuget": "NuGet",
        "npm": "NPM",
        "pypi": "PyPI",
        "gem": "RubyGems",
        "golang": "Go",
        "maven": "Maven",
        "cargo": "Cargo",
    }

    def __init__(self, api_key: str, timeout: float = 15.0) -> None:
        self._api_key = api_key
        self._timeout = timeout
        self._min_interval = 1.0
        self._last_request_time = 0.0
        self._client = httpx.Client(timeout=timeout)

    @property
    def name(self) -> str:
        return "libraries.io"

    def resolve(self, purl: str) -> Resolution:
        try:
            purl_type = purl.split(":")[1].split("/")[0] if ":" in purl else ""
        except (IndexError, ValueError):
            return Resolution(purl=purl, warnings=[f"Could not parse PURL type from: {purl}"])

        platform = self.ECOSYSTEM_MAP.get(purl_type)
        if platform is None:
            return Resolution(
                purl=purl,
                warnings=[f"Unsupported package type '{purl_type}' for libraries.io"],
            )

        parts = purl.split("/", 1)
        if len(parts) < 2:
            return Resolution(purl=purl, warnings=[f"Could not parse package name from: {purl}"])

        name_with_version = parts[1]
        name = name_with_version.split("@")[0]

        self._rate_limit_wait()

        url = f"{_API_BASE}/{platform}/{name}"
        try:
            response = self._client.get(url, params={"api_key": self._api_key})
            response.raise_for_status()
        except httpx.TimeoutException:
            logger.warning("libraries.io request timed out for %s/%s", platform, name)
            return Resolution(purl=purl, warnings=[f"libraries.io timeout for {platform}/{name}"])
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            logger.warning("libraries.io returned %d for %s/%s", status, platform, name)
            return Resolution(purl=purl, warnings=[f"libraries.io error {status} for {platform}/{name}"])
        except httpx.HTTPError as exc:
            logger.warning("libraries.io request failed for %s/%s: %s", platform, name, exc)
            return Resolution(purl=purl, warnings=[f"libraries.io network error for {platform}/{name}: {exc}"])

        data = response.json()
        repo = data.get("repository")
        if repo is None or not isinstance(repo, dict):
            return Resolution(purl=purl, warnings=[f"No repository found on libraries.io for {platform}/{name}"])

        repo_url = repo.get("url")
        if not repo_url:
            return Resolution(purl=purl, warnings=[f"Empty repository URL on libraries.io for {platform}/{name}"])

        return Resolution(
            purl=purl,
            repository_url=repo_url,
            repository_type=None,
            repository_kind="source",
            confidence="medium",
            evidence=[f"libraries.io:{platform}/{name}"],
        )

    def _rate_limit_wait(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_request_time
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request_time = time.monotonic()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_librariesio_resolver.py -v`
Expected: PASS

- [ ] **Step 5: Run all tests**

Run: `.venv/bin/pytest tests/ -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/purl_resolver/resolver/librariesio.py tests/test_librariesio_resolver.py
git commit -m "feat: add LibrariesIoResolver with ecosystem mapping, rate limiting, and graceful degradation"
```

---

### Task 3: Add settings fields for libraries.io

**Files:**
- Modify: `src/purl_resolver/settings_store.py`
- Test: `tests/test_settings_store.py` (create if not exists, or add to existing)

- [ ] **Step 1: Write failing test**

Create or extend `tests/test_settings_store.py`:

```python
from __future__ import annotations

from pathlib import Path

from purl_resolver.settings_store import AppSettings, SettingsStore


class TestLibrariesIoSettings:
    def test_default_librariesio_disabled(self, tmp_path: Path) -> None:
        store = SettingsStore(path=tmp_path / "settings.json")
        settings = store.load()
        assert settings.librariesio_enabled is False
        assert settings.librariesio_api_key is None

    def test_save_and_load_librariesio_settings(self, tmp_path: Path) -> None:
        store = SettingsStore(path=tmp_path / "settings.json")
        settings = store.load()
        updated = settings.model_copy(update={
            "librariesio_enabled": True,
            "librariesio_api_key": "test_key_123",
        })
        store.save(updated)

        loaded = store.load()
        assert loaded.librariesio_enabled is True
        assert loaded.librariesio_api_key == "test_key_123"

    def test_clear_librariesio_key(self, tmp_path: Path) -> None:
        store = SettingsStore(path=tmp_path / "settings.json")
        settings = store.load()
        with_key = settings.model_copy(update={"librariesio_api_key": "key"})
        store.save(with_key)

        loaded = store.load()
        cleared = loaded.model_copy(update={"librariesio_api_key": None})
        store.save(cleared)

        final = store.load()
        assert final.librariesio_api_key is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_settings_store.py -v`
Expected: FAIL — `AppSettings` has no field `librariesio_enabled`

- [ ] **Step 3: Add fields to AppSettings**

Edit `src/purl_resolver/settings_store.py`:

```python
class AppSettings(BaseModel):
    validate_db_urls: bool = False
    url_validation_timeout: int = Field(default=5, ge=1, le=60)
    github_token: str | None = None
    librariesio_enabled: bool = False
    librariesio_api_key: str | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_settings_store.py -v`
Expected: PASS

- [ ] **Step 5: Run all tests**

Run: `.venv/bin/pytest tests/ -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/purl_resolver/settings_store.py tests/test_settings_store.py
git commit -m "feat: add librariesio_enabled and librariesio_api_key to AppSettings"
```

---

### Task 4: Update router for settings and resolver re-registration

**Files:**
- Modify: `src/purl_resolver/router.py`
- Test: `tests/test_api.py` (extend existing `TestSettingsAPI` class)

- [ ] **Step 1: Write failing tests**

Add to `tests/test_api.py` (in `TestSettingsAPI` class or new class):

```python
class TestLibrariesIoSettings:
    def test_get_settings_includes_librariesio(self, client: TestClient) -> None:
        response = client.get("/api/v1/settings")
        assert response.status_code == 200
        data = response.json()
        assert "librariesio_enabled" in data
        assert "token_set" in data
        assert "librariesio_api_key" in data["token_set"]

    def test_patch_settings_enable_librariesio(self, client: TestClient, tmp_path: Path) -> None:
        client.app.state.settings_store = SettingsStore(path=tmp_path / "settings.json")
        response = client.patch("/api/v1/settings", json={
            "librariesio_enabled": True,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["librariesio_enabled"] is True

    def test_patch_settings_with_valid_librariesio_key(self, client: TestClient, tmp_path: Path) -> None:
        client.app.state.settings_store = SettingsStore(path=tmp_path / "settings.json")
        with patch("purl_resolver.router.validate_librariesio_key", return_value=True):
            response = client.patch("/api/v1/settings", json={
                "librariesio_api_key": "lib_test_key",
            })
        assert response.status_code == 200
        data = response.json()
        assert data["token_set"]["librariesio_api_key"] is True

    def test_patch_settings_with_invalid_librariesio_key(self, client: TestClient, tmp_path: Path) -> None:
        client.app.state.settings_store = SettingsStore(path=tmp_path / "settings.json")
        with patch("purl_resolver.router.validate_librariesio_key", return_value=False):
            response = client.patch("/api/v1/settings", json={
                "librariesio_api_key": "invalid_key",
            })
        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "invalid_token"

    def test_patch_settings_clear_librariesio_key(self, client: TestClient, tmp_path: Path) -> None:
        client.app.state.settings_store = SettingsStore(path=tmp_path / "settings.json")
        # First set a key
        client.app.state.settings_store.save(
            client.app.state.settings_store.load().model_copy(update={"librariesio_api_key": "key"})
        )
        response = client.patch("/api/v1/settings", json={
            "librariesio_api_key": None,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["token_set"]["librariesio_api_key"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_api.py -v -k "LibrariesIo"`
Expected: FAIL — response missing `librariesio_enabled` or `token_set.librariesio_api_key`

- [ ] **Step 3: Add `validate_librariesio_key` function**

Add to `src/purl_resolver/router.py` (near `validate_github_token`):

```python
def validate_librariesio_key(api_key: str) -> bool:
    try:
        response = httpx.get(
            "https://libraries.io/api/platforms",
            params={"api_key": api_key},
            timeout=10.0,
        )
        return response.status_code == 200
    except httpx.HTTPError:
        return True  # Don't block save on network error
```

- [ ] **Step 4: Add import for httpx at top of router.py**

Ensure `import httpx` is present in router.py imports.

- [ ] **Step 5: Update `SettingsUpdate` model**

Edit `src/purl_resolver/router.py` — add fields to `SettingsUpdate`:

```python
class SettingsUpdate(BaseModel):
    validate_db_urls: bool | None = None
    url_validation_timeout: int | None = Field(None, ge=1, le=60)
    github_token: str | None = None
    librariesio_enabled: bool | None = None
    librariesio_api_key: str | None = None
```

- [ ] **Step 6: Update `GET /api/v1/settings` response**

Edit `src/purl_resolver/router.py` — update `get_settings`:

```python
@router.get("/api/v1/settings")
async def get_settings(request: Request) -> JSONResponse:
    store: SettingsStore = request.app.state.settings_store
    settings = store.load()
    return JSONResponse(content={
        "validate_db_urls": settings.validate_db_urls,
        "url_validation_timeout": settings.url_validation_timeout,
        "librariesio_enabled": settings.librariesio_enabled,
        "token_set": {
            "github_token": settings.github_token is not None,
            "librariesio_api_key": settings.librariesio_api_key is not None,
        },
    })
```

- [ ] **Step 7: Update `PATCH /api/v1/settings` response and validation**

Edit `src/purl_resolver/router.py` — add libraries.io key validation logic in `update_settings` (after the github_token block):

```python
    if "librariesio_api_key" in update_data:
        key_value = update_data["librariesio_api_key"]
        if key_value is None:
            pass  # null → clear the key
        elif key_value == "":
            del update_data["librariesio_api_key"]  # "" → no-op
        else:
            if not validate_librariesio_key(key_value):
                return JSONResponse(
                    status_code=400,
                    content={"error": "invalid_token", "message": "Libraries.io API key is invalid"},
                )
```

And update the return value:

```python
    return JSONResponse(content={
        "validate_db_urls": updated.validate_db_urls,
        "url_validation_timeout": updated.url_validation_timeout,
        "librariesio_enabled": updated.librariesio_enabled,
        "token_set": {
            "github_token": updated.github_token is not None,
            "librariesio_api_key": updated.librariesio_api_key is not None,
        },
    })
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_api.py -v`
Expected: PASS

- [ ] **Step 9: Run all tests**

Run: `.venv/bin/pytest tests/ -v`
Expected: PASS

- [ ] **Step 10: Commit**

```bash
git add src/purl_resolver/router.py tests/test_api.py
git commit -m "feat: add libraries.io settings to API endpoints with key validation"
```

---

### Task 5: Register libraries.io resolver in lifespan

**Files:**
- Modify: `src/purl_resolver/main.py`
- Test: `tests/test_main.py` (create if needed)

- [ ] **Step 1: Write failing test**

Create `tests/test_main.py`:

```python
from __future__ import annotations

from unittest.mock import MagicMock, patch

from purl_resolver.main import app
from purl_resolver.resolver.librariesio import LibrariesIoResolver
from purl_resolver.resolver.purl2repo import Purl2RepoResolver
from purl_resolver.settings_store import AppSettings


class TestResolverRegistration:
    def test_librariesio_registered_when_enabled(self) -> None:
        mock_store = MagicMock()
        mock_store.load.return_value = AppSettings(
            librariesio_enabled=True,
            librariesio_api_key="test_key",
        )
        app.state.settings_store = mock_store

        resolvers = []
        settings = mock_store.load()
        resolvers.append(Purl2RepoResolver())
        if settings.librariesio_enabled and settings.librariesio_api_key:
            resolvers.append(LibrariesIoResolver(api_key=settings.librariesio_api_key))

        assert len(resolvers) == 2
        assert isinstance(resolvers[1], LibrariesIoResolver)

    def test_librariesio_not_registered_when_disabled(self) -> None:
        mock_store = MagicMock()
        mock_store.load.return_value = AppSettings(
            librariesio_enabled=False,
            librariesio_api_key=None,
        )
        settings = mock_store.load()

        resolvers = [Purl2RepoResolver()]
        if settings.librariesio_enabled and settings.librariesio_api_key:
            resolvers.append(LibrariesIoResolver(api_key=settings.librariesio_api_key))

        assert len(resolvers) == 1

    def test_librariesio_not_registered_without_key(self) -> None:
        mock_store = MagicMock()
        mock_store.load.return_value = AppSettings(
            librariesio_enabled=True,
            librariesio_api_key=None,
        )
        settings = mock_store.load()

        resolvers = [Purl2RepoResolver()]
        if settings.librariesio_enabled and settings.librariesio_api_key:
            resolvers.append(LibrariesIoResolver(api_key=settings.librariesio_api_key))

        assert len(resolvers) == 1
```

- [ ] **Step 2: Run tests to verify they pass (logic test)**

Run: `.venv/bin/pytest tests/test_main.py -v`
Expected: PASS (these test the logic, not the lifespan directly)

- [ ] **Step 3: Update lifespan in main.py**

Edit `src/purl_resolver/main.py`:

```python
from .resolver.librariesio import LibrariesIoResolver

@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = None
    try:
        pool = await create_pool()
        app.state.storage = PostgresCache(pool)
        logger.info("Connected to PostgreSQL at %s", storage_settings.url)
    except (asyncpg.InvalidCatalogNameError, OSError, Exception):
        logger.warning(
            "PostgreSQL unavailable, falling back to in-memory cache", exc_info=True
        )
        app.state.storage = InMemoryCache()

    app.state.settings_store = SettingsStore()

    app.state.resolvers = [
        Purl2RepoResolver(
            timeout=settings.timeout,
            use_cache=settings.use_cache,
            strict=settings.strict,
            no_network=settings.no_network,
            cache_dir=settings.cache_dir,
        ),
    ]

    app_settings = app.state.settings_store.load()
    if app_settings.librariesio_enabled and app_settings.librariesio_api_key:
        app.state.resolvers.append(
            LibrariesIoResolver(api_key=app_settings.librariesio_api_key)
        )

    logger.info("Configured %d resolver(s)", len(app.state.resolvers))
    yield
    if pool is not None:
        await pool.close()
```

- [ ] **Step 4: Add helper function for resolver re-registration**

Add to `src/purl_resolver/router.py` (near the top, or as a utility):

```python
def _rebuild_resolvers(request: Request) -> None:
    store: SettingsStore = request.app.state.settings_store
    app_settings = store.load()

    from .resolver.purl2repo import Purl2RepoResolver
    from .resolver.librariesio import LibrariesIoResolver
    from .config import settings

    resolvers = [
        Purl2RepoResolver(
            timeout=settings.timeout,
            use_cache=settings.use_cache,
            strict=settings.strict,
            no_network=settings.no_network,
            cache_dir=settings.cache_dir,
        ),
    ]
    if app_settings.librariesio_enabled and app_settings.librariesio_api_key:
        resolvers.append(
            LibrariesIoResolver(api_key=app_settings.librariesio_api_key)
        )
    request.app.state.resolvers = resolvers
```

- [ ] **Step 5: Call `_rebuild_resolvers` in PATCH /settings**

At the end of `update_settings`, before the return statement, add:

```python
    _rebuild_resolvers(request)
```

- [ ] **Step 6: Run all tests**

Run: `.venv/bin/pytest tests/ -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/purl_resolver/main.py src/purl_resolver/router.py tests/test_main.py
git commit -m "feat: register libraries.io resolver in lifespan and rebuild on settings change"
```

---

### Task 6: Update service.py to use `r.name`

**Files:**
- Modify: `src/purl_resolver/service.py`

- [ ] **Step 1: Update resolver field in resolve_purl**

Edit `src/purl_resolver/service.py` — line 115, change `resolver=resolver` to `resolver=r.name`:

```python
        response = ResolveResponse(
            purl=purl_key,
            repository_url=resolution.repository_url,
            repository_type=resolution.repository_type,
            repository_kind=resolution.repository_kind,
            confidence=resolution.confidence,
            evidence=list(resolution.evidence),
            warnings=list(resolution.warnings),
            version_reference=resolution.version_reference,
            resolver=r.name,
        )
```

- [ ] **Step 2: Run all tests**

Run: `.venv/bin/pytest tests/ -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add src/purl_resolver/service.py
git commit -m "feat: use Resolver.name for resolver field in stored results"
```

---

### Task 7: Add Libraries.io card to settings.html

**Files:**
- Modify: `src/purl_resolver/templates/settings.html`

- [ ] **Step 1: Add Libraries.io card HTML**

Insert after the GitHub token card (before `<button id="save-btn">`):

```html
        <div class="card" style="margin-top:1rem;">
            <div class="card-title">Libraries.io Resolver (optional)</div>
            <div class="setting-row">
                <div>
                    <div class="setting-label">Enable libraries.io resolver</div>
                    <div class="setting-desc">
                        When enabled, libraries.io is used as a fallback resolver
                        when purl2repo cannot find a repository URL.
                    </div>
                </div>
                <label class="toggle">
                    <input type="checkbox" id="librariesio-toggle">
                    <span class="toggle-slider"></span>
                </label>
            </div>
            <div class="setting-row">
                <div>
                    <div class="setting-label">API Key</div>
                    <div class="setting-desc">
                        Optional API key for higher rate limits (60 req/min vs 10 req/min).
                    </div>
                    <div class="setting-desc" style="margin-top:0.25rem;">
                        <a href="https://libraries.io/login" target="_blank" style="color:#2563eb;">
                            Log in to libraries.io
                        </a> → API Settings
                    </div>
                    <div id="librariesio-key-status" class="setting-desc" style="margin-top:0.5rem;">
                        Status: <span id="librariesio-key-badge" style="font-weight:600;">not set</span>
                        <button id="clear-librariesio-key-btn" class="btn-danger btn-small" style="margin-left:0.5rem;display:none;">Clear key</button>
                    </div>
                </div>
                <div style="text-align:right;">
                    <input type="password" id="librariesio-key-input"
                           placeholder="libraries.io API key" style="width:240px;padding:0.5rem;border:1px solid #ccc;border-radius:6px;font-size:0.9rem;">
                </div>
            </div>
        </div>
```

- [ ] **Step 2: Add JavaScript for libraries.io settings**

Add to the `<script>` section in settings.html, inside `loadSettings()`:

```javascript
                const lioToggle = document.getElementById("librariesio-toggle");
                const lioBadge = document.getElementById("librariesio-key-badge");
                const lioClearBtn = document.getElementById("clear-librariesio-key-btn");

                // In loadSettings():
                lioToggle.checked = data.librariesio_enabled;
                lioBadge.textContent = data.token_set.librariesio_api_key ? "set" : "not set";
                lioBadge.style.color = data.token_set.librariesio_api_key ? "#166534" : "#991b1b";
                lioClearBtn.style.display = data.token_set.librariesio_api_key ? "inline-block" : "none";
```

Add to `saveSettings()`:

```javascript
                body.librariesio_enabled = lioToggle.checked;
                const lioKeyInput = document.getElementById("librariesio-key-input");
                if (lioKeyInput.value.trim() !== "") {
                    body.librariesio_api_key = lioKeyInput.value.trim();
                }
```

Add new `clearLibrariesIoKey()` function:

```javascript
        async function clearLibrariesIoKey() {
            lioClearBtn.disabled = true;
            try {
                const res = await fetch("/api/v1/settings", {
                    method: "PATCH",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ librariesio_api_key: null }),
                });
                if (res.ok) {
                    showMessage("Libraries.io key cleared", false);
                    loadSettings();
                } else {
                    const data = await res.json();
                    showMessage(data.message || "Failed to clear key", true);
                }
            } catch {
                showMessage("Network error", true);
            } finally {
                lioClearBtn.disabled = false;
            }
        }
```

Add event listener:

```javascript
        clearLibrariesioKeyBtn.addEventListener("click", clearLibrariesIoKey);
```

Also clear the libraries.io key input after save in `saveSettings()`:

```javascript
                    lioKeyInput.value = "";
```

- [ ] **Step 3: Verify UI renders correctly (manual check)**

Start the dev server and navigate to `/settings`. Verify:
- Libraries.io card appears below GitHub token card
- Toggle, input, badge, clear button all visible
- Toggle saves/persists
- API key input and clear button work

- [ ] **Step 4: Commit**

```bash
git add src/purl_resolver/templates/settings.html
git commit -m "feat: add Libraries.io resolver card to settings page"
```

---

### Task 8: Integration tests for the full flow

**Files:**
- Test: `tests/test_librariesio_integration.py`

- [ ] **Step 1: Write integration tests**

Create `tests/test_librariesio_integration.py`:

```python
from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from purl_resolver.resolver.interface import Resolution
from purl_resolver.resolver.librariesio import LibrariesIoResolver
from purl_resolver.resolver.purl2repo import Purl2RepoResolver
from purl_resolver.service import resolve_purl
from purl_resolver.settings_store import AppSettings, SettingsStore
from purl_resolver.storage.inmemory import InMemoryCache


class TestResolverChain:
    @pytest.mark.asyncio
    async def test_purl2repo_fails_librariesio_succeeds(self) -> None:
        purl2repo = MagicMock(spec=Purl2RepoResolver)
        purl2repo.name = "purl2repo"
        purl2repo.resolve.return_value = Resolution(
            purl="pkg:pypi/requests",
            warnings=["Unsupported ecosystem"],
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "name": "requests",
            "repository": {"url": "https://github.com/psf/requests"},
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_response

        lio = LibrariesIoResolver(api_key="test_key")
        lio._client = mock_client

        storage = InMemoryCache()
        resolvers = [purl2repo, lio]

        result = await resolve_purl(
            "pkg:pypi/requests@2.31.0",
            storage,
            resolvers,
        )

        assert result.response is not None
        assert result.response.repository_url == "https://github.com/psf/requests"
        assert result.response.resolver == "libraries.io"

    @pytest.mark.asyncio
    async def test_both_fail_returns_warnings(self) -> None:
        purl2repo = MagicMock(spec=Purl2RepoResolver)
        purl2repo.name = "purl2repo"
        purl2repo.resolve.return_value = Resolution(
            purl="pkg:deb/debian/libssl",
            warnings=["Unsupported ecosystem"],
        )

        lio = MagicMock(spec=LibrariesIoResolver)
        lio.name = "libraries.io"
        lio.resolve.return_value = Resolution(
            purl="pkg:deb/debian/libssl",
            warnings=["Unsupported package type 'deb' for libraries.io"],
        )

        storage = InMemoryCache()
        resolvers = [purl2repo, lio]

        result = await resolve_purl(
            "pkg:deb/debian/libssl",
            storage,
            resolvers,
        )

        assert result.response is not None
        assert result.response.repository_url is None
        assert len(result.response.warnings) > 0

    @pytest.mark.asyncio
    async def test_librariesio_error_does_not_interrupt_chain(self) -> None:
        purl2repo = MagicMock(spec=Purl2RepoResolver)
        purl2repo.name = "purl2repo"
        purl2repo.resolve.return_value = Resolution(
            purl="pkg:pypi/requests",
            warnings=["Could not resolve"],
        )

        lio = MagicMock(spec=LibrariesIoResolver)
        lio.name = "libraries.io"
        lio.resolve.return_value = Resolution(
            purl="pkg:pypi/requests",
            warnings=["libraries.io timeout for PyPI/requests"],
        )

        storage = InMemoryCache()
        resolvers = [purl2repo, lio]

        result = await resolve_purl(
            "pkg:pypi/requests@2.31.0",
            storage,
            resolvers,
        )

        assert result.response is not None
        assert result.response.repository_url is None
        assert any("No resolver found" in w for w in result.response.warnings)
```

- [ ] **Step 2: Run integration tests**

Run: `.venv/bin/pytest tests/test_librariesio_integration.py -v`
Expected: PASS

- [ ] **Step 3: Run full test suite**

Run: `.venv/bin/pytest tests/ -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_librariesio_integration.py
git commit -m "test: add integration tests for libraries.io resolver chain"
```

---

### Task 9: Update specs and ADR

**Files:**
- Modify: `specs/contracts/api-contract.md` (settings section)
- Modify: `specs/domains/purl-resolution.md` (resolver list)
- Modify: `specs/domains/web-ui.md` (settings page)
- Create: `docs/adr/0004-librariesio-as-fallback-resolver.md`

- [ ] **Step 1: Create ADR**

Create `docs/adr/0004-librariesio-as-fallback-resolver.md`:

```markdown
# ADR-0004: libraries.io as fallback resolver

## Context

purl2repo does not support all ecosystems. Some packages (especially in less common ecosystems) cannot be resolved. A secondary data source is needed to improve coverage.

## Decision

Add libraries.io as a fallback resolver in the resolver chain. It is:
- Disabled by default, enabled via Settings page (checkbox + API key)
- Tried only after purl2repo fails to find a repository URL
- Uses `httpx` (synchronous) with a 1-second rate limiter
- Errors are logged as warnings and do not interrupt processing (graceful degradation)
- API key validated via `GET /api/v1/platforms?api_key={key}` at save time

## Consequences

- Improved PURL resolution coverage for ecosystems not supported by purl2repo
- No impact on existing behavior when disabled (default state)
- Graceful degradation: libraries.io outages do not affect the primary resolver
- Rate limiting ensures compliance with libraries.io API limits (60 req/min with key)
- Resolver name stored in DB results distinguishes purl2repo vs libraries.io resolution
```

- [ ] **Step 2: Update API contract settings section**

Add to `specs/contracts/api-contract.md` in the settings section:

- `GET /api/v1/settings` response: add `librariesio_enabled` (bool), `token_set.librariesio_api_key` (bool)
- `PATCH /api/v1/settings` body: add `librariesio_enabled` (bool, optional), `librariesio_api_key` (str|null, optional)
- `librariesio_api_key: null` → clears the key; empty string → no-op; non-empty → validated

- [ ] **Step 3: Update purl-resolution spec**

Add to `specs/domains/purl-resolution.md` in the resolver list section:

- `LibrariesIoResolver` — fallback resolver, libraries.io API, optional (settings-controlled)

- [ ] **Step 4: Update web-ui spec**

Add to `specs/domains/web-ui.md` in the settings page section:

- Libraries.io Resolver card: enable toggle, API key input, status badge, clear button

- [ ] **Step 5: Commit**

```bash
git add docs/adr/0004-librariesio-as-fallback-resolver.md specs/contracts/api-contract.md specs/domains/purl-resolution.md specs/domains/web-ui.md
git commit -m "docs: add ADR-0004 and update specs for libraries.io resolver"
```
