# ecosyste.ms Resolver Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add ecosyste.ms as a fallback resolver between purl2repo and libraries.io, with optional API key support and UI settings.

**Architecture:** New `EcosystemsResolver` class follows the same pattern as `LibrariesIoResolver`. Configured via JSON settings (`ecosyste.ms enabled by default`). Resolver chain: purl2repo → ecosyste.ms → libraries.io.

**Tech Stack:** Python, httpx (sync), FastAPI, pytest, Jinja2

**Design spec:** `docs/superpowers/specs/2026-06-05-ecosyste-ms-resolver-design.md`

---

## File Structure

| File | Action | Purpose |
|---|---|---|
| `src/purl_resolver/resolver/ecosystems.py` | Create | `EcosystemsResolver` class |
| `tests/test_ecosystems_resolver.py` | Create | Unit tests with mocks |
| `tests/e2e/test_ecosystems.py` | Create | E2E test with real API |
| `src/purl_resolver/settings_store.py` | Modify | Add `ecosystems_enabled`, `ecosystems_api_key` |
| `src/purl_resolver/router.py` | Modify | Update `_rebuild_resolvers()`, `SettingsUpdate`, `GET/PATCH /api/v1/settings` |
| `src/purl_resolver/templates/settings.html` | Modify | Add ecosyste.ms settings card |
| `specs/domains/purl-resolution.md` | Modify | Add configuration fields |
| `specs/architecture/layers.md` | Modify | Add `EcosystemsResolver` to resolver layer |
| `docs/adr/0005-ecosyste-ms-as-fallback-resolver.md` | Create | ADR for the decision |

---

### Task 1: Create EcosystemsResolver class

**Files:**
- Create: `src/purl_resolver/resolver/ecosystems.py`

- [ ] **Step 1: Create the resolver file with full implementation**

```python
from __future__ import annotations

import logging
from urllib.parse import quote

import httpx

from ..purl_utils import PurlValidationError, validate
from .interface import Resolution, Resolver

logger = logging.getLogger(__name__)

_API_URL = "https://packages.ecosyste.ms/api/v1/packages/lookup"


def select_repository_url(package_data: dict) -> str | None:
    candidates = [
        package_data.get("repository_url", ""),
        package_data.get("registry_url", ""),
        package_data.get("homepage", ""),
    ]

    for url in candidates:
        if not url or "repos.ecosyste.ms" in url:
            continue
        if "github.com" in url:
            return url

    for url in candidates:
        if url and "repos.ecosyste.ms" not in url:
            return url

    return None


class EcosystemsResolver(Resolver):

    def __init__(self, api_key: str | None = None, timeout: float = 15.0) -> None:
        self._api_key = api_key
        self._timeout = timeout
        self._client = httpx.Client(timeout=timeout)

    @property
    def name(self) -> str:
        return "ecosyste.ms"

    def resolve(self, purl: str) -> Resolution:
        try:
            components = validate(purl)
        except PurlValidationError as e:
            return Resolution(purl=purl, warnings=[f"Invalid PURL: {e}"])

        params: dict[str, str] = {"purl": purl}
        if self._api_key:
            params["api_key"] = self._api_key

        try:
            response = self._client.get(_API_URL, params=params)
            response.raise_for_status()
        except httpx.TimeoutException:
            logger.warning("ecosyste.ms request timed out for %s", purl)
            return Resolution(purl=purl, warnings=[f"ecosyste.ms timeout for {purl}"])
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            logger.warning("ecosyste.ms returned %d for %s", status, purl)
            return Resolution(purl=purl, warnings=[f"ecosyste.ms error {status} for {purl}"])
        except httpx.HTTPError as exc:
            logger.warning("ecosyste.ms request failed for %s: %s", purl, exc)
            return Resolution(purl=purl, warnings=[f"ecosyste.ms network error for {purl}: {exc}"])

        data = response.json()
        if not data:
            return Resolution(purl=purl, warnings=[f"No package found on ecosyste.ms for {purl}"])

        package = data[0]
        repo_url = select_repository_url(package)
        if not repo_url:
            return Resolution(purl=purl, warnings=[f"No repository URL found on ecosyste.ms for {purl}"])

        ecosystem = package.get("ecosystem", "unknown")
        name = package.get("name", "unknown")

        return Resolution(
            purl=purl,
            repository_url=repo_url,
            repository_type=None,
            repository_kind="vcs",
            confidence="medium",
            evidence=[f"ecosyste.ms:{ecosystem}/{name}"],
        )
```

- [ ] **Step 2: Commit**

```bash
git add src/purl_resolver/resolver/ecosystems.py
git commit -m "feat: add EcosystemsResolver for ecosyste.ms API"
```

---

### Task 2: Unit tests for EcosystemsResolver

**Files:**
- Create: `tests/test_ecosystems_resolver.py`

- [ ] **Step 1: Create the test file**

```python
from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest

from purl_resolver.resolver.ecosystems import EcosystemsResolver, select_repository_url
from purl_resolver.resolver.interface import Resolution


class TestSelectRepositoryUrl:
    def test_repository_url_with_github(self) -> None:
        data = {"repository_url": "https://github.com/psf/requests", "registry_url": "https://pypi.org/project/requests/"}
        assert select_repository_url(data) == "https://github.com/psf/requests"

    def test_registry_url_when_no_repository(self) -> None:
        data = {"repository_url": "", "registry_url": "https://pypi.org/project/requests/"}
        assert select_repository_url(data) == "https://pypi.org/project/requests/"

    def test_homepage_fallback(self) -> None:
        data = {"repository_url": "", "registry_url": "", "homepage": "https://requests.readthedocs.io"}
        assert select_repository_url(data) == "https://requests.readthedocs.io"

    def test_skip_repos_ecosyste_ms(self) -> None:
        data = {"repository_url": "https://repos.ecosyste.ms/psf/requests", "homepage": "https://example.com"}
        assert select_repository_url(data) == "https://example.com"

    def test_github_preferred_over_other(self) -> None:
        data = {"repository_url": "https://gitlab.com/foo/bar", "homepage": "https://github.com/foo/bar"}
        assert select_repository_url(data) == "https://github.com/foo/bar"

    def test_empty_data_returns_none(self) -> None:
        assert select_repository_url({}) is None

    def test_all_ecosyste_ms_urls_returns_none(self) -> None:
        data = {"repository_url": "https://repos.ecosyste.ms/foo", "homepage": "https://repos.ecosyste.ms/bar"}
        assert select_repository_url(data) is None


class TestResolverName:
    def test_name(self) -> None:
        r = EcosystemsResolver()
        assert r.name == "ecosyste.ms"


class TestResolveSuccess:
    def test_successful_resolution(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "name": "requests",
                "ecosystem": "pypi",
                "repository_url": "https://github.com/psf/requests",
                "registry_url": "https://pypi.org/project/requests/",
                "homepage": None,
            }
        ]
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_response

        r = EcosystemsResolver()
        r._client = mock_client

        result = r.resolve("pkg:pypi/requests@2.31.0")
        assert result.repository_url == "https://github.com/psf/requests"
        assert result.repository_kind == "vcs"
        assert result.confidence == "medium"
        assert "ecosyste.ms:pypi/requests" in result.evidence


class TestResolveNoPackage:
    def test_empty_array_returns_warning(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_response

        r = EcosystemsResolver()
        r._client = mock_client

        result = r.resolve("pkg:pypi/nonexistent")
        assert result.repository_url is None
        assert any("no package" in w.lower() for w in result.warnings)


class TestResolveNoRepositoryUrl:
    def test_no_repository_url_in_response(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "name": "some-pkg",
                "ecosystem": "pypi",
                "repository_url": "",
                "registry_url": "",
                "homepage": "",
            }
        ]
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_response

        r = EcosystemsResolver()
        r._client = mock_client

        result = r.resolve("pkg:pypi/some-pkg")
        assert result.repository_url is None
        assert any("no repository" in w.lower() for w in result.warnings)


class TestResolveErrors:
    def test_timeout_returns_warning(self) -> None:
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.side_effect = httpx.TimeoutException("timeout")

        r = EcosystemsResolver()
        r._client = mock_client

        result = r.resolve("pkg:pypi/requests")
        assert result.repository_url is None
        assert any("timeout" in w.lower() for w in result.warnings)

    def test_5xx_returns_warning(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "server error", request=MagicMock(), response=mock_response
        )

        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_response

        r = EcosystemsResolver()
        r._client = mock_client

        result = r.resolve("pkg:pypi/requests")
        assert result.repository_url is None
        assert any("500" in w or "error" in w.lower() for w in result.warnings)

    def test_network_error_returns_warning(self) -> None:
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.side_effect = httpx.ConnectError("connection refused")

        r = EcosystemsResolver()
        r._client = mock_client

        result = r.resolve("pkg:pypi/requests")
        assert result.repository_url is None
        assert len(result.warnings) > 0


class TestApiKey:
    def test_api_key_passed_in_params(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"name": "pkg", "ecosystem": "pypi", "repository_url": "https://github.com/a/b"}]
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_response

        r = EcosystemsResolver(api_key="test_key_123")
        r._client = mock_client

        r.resolve("pkg:pypi/pkg")
        call_kwargs = mock_client.get.call_args
        assert call_kwargs[1]["params"]["api_key"] == "test_key_123"

    def test_no_key_no_api_key_param(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"name": "pkg", "ecosystem": "pypi", "repository_url": "https://github.com/a/b"}]
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_response

        r = EcosystemsResolver()
        r._client = mock_client

        r.resolve("pkg:pypi/pkg")
        call_kwargs = mock_client.get.call_args
        assert "api_key" not in call_kwargs[1]["params"]


class TestInvalidPurl:
    def test_invalid_purl_returns_warning(self) -> None:
        r = EcosystemsResolver()
        result = r.resolve("not-a-valid-purl")
        assert result.repository_url is None
        assert any("invalid" in w.lower() for w in result.warnings)
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_ecosystems_resolver.py -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_ecosystems_resolver.py
git commit -m "test: add unit tests for EcosystemsResolver"
```

---

### Task 3: E2E test with real API

**Files:**
- Create: `tests/e2e/test_ecosystems.py`

- [ ] **Step 1: Create the e2e test file**

```python
from __future__ import annotations

import os

import pytest

from purl_resolver.resolver.ecosystems import EcosystemsResolver

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_E2E") == "1",
    reason="Set SKIP_E2E=1 to skip e2e tests (require network)",
)


class TestE2EEcosystemsResolver:

    def test_resolve_real_request(self) -> None:
        r = EcosystemsResolver(timeout=15.0)
        result = r.resolve("pkg:pypi/requests")
        assert result.repository_url == "https://github.com/psf/requests"
        assert result.confidence == "medium"
        assert result.repository_kind == "vcs"
        assert len(result.evidence) > 0

    def test_resolve_unknown_package(self) -> None:
        r = EcosystemsResolver(timeout=15.0)
        result = r.resolve("pkg:pypi/nonexistent-pkg-xyz-12345")
        assert result.repository_url is None
        assert len(result.warnings) > 0

    def test_resolve_npm_package(self) -> None:
        r = EcosystemsResolver(timeout=15.0)
        result = r.resolve("pkg:npm/express")
        assert result.repository_url is not None
        assert "github.com" in result.repository_url
```

- [ ] **Step 2: Run e2e test (without SKIP_E2E)**

Run: `.venv/bin/pytest tests/e2e/test_ecosystems.py -v`
Expected: All tests PASS (requires network)

- [ ] **Step 3: Run with SKIP_E2E=1 to verify skip works**

Run: `SKIP_E2E=1 .venv/bin/pytest tests/e2e/test_ecosystems.py -v`
Expected: All tests SKIPPED

- [ ] **Step 4: Commit**

```bash
git add tests/e2e/test_ecosystems.py
git commit -m "test: add e2e tests for ecosyste.ms resolver"
```

---

### Task 4: Add settings fields to AppSettings

**Files:**
- Modify: `src/purl_resolver/settings_store.py:19-24`

- [ ] **Step 1: Add new fields to AppSettings**

In `src/purl_resolver/settings_store.py`, add two fields to the `AppSettings` class after `librariesio_api_key`:

```python
class AppSettings(BaseModel):
    validate_db_urls: bool = False
    url_validation_timeout: int = Field(default=5, ge=1, le=60)
    github_token: str | None = None
    librariesio_enabled: bool = False
    librariesio_api_key: str | None = None
    ecosystems_enabled: bool = True
    ecosystems_api_key: str | None = None

    def service_tokens(self) -> ServiceTokens:
        return ServiceTokens(github_token=self.github_token)
```

- [ ] **Step 2: Run existing settings tests to verify no regression**

Run: `.venv/bin/pytest tests/test_settings_store.py -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add src/purl_resolver/settings_store.py
git commit -m "feat: add ecosystems_enabled and ecosystems_api_key to AppSettings"
```

---

### Task 5: Update router — SettingsUpdate, _rebuild_resolvers, GET/PATCH

**Files:**
- Modify: `src/purl_resolver/router.py:51-56` (SettingsUpdate)
- Modify: `src/purl_resolver/router.py:320-341` (_rebuild_resolvers)
- Modify: `src/purl_resolver/router.py:344-356` (get_settings)
- Modify: `src/purl_resolver/router.py:400-408` (update_settings response)

- [ ] **Step 1: Add fields to SettingsUpdate model**

In `src/purl_resolver/router.py`, add two fields to `SettingsUpdate` after `librariesio_api_key`:

```python
class SettingsUpdate(BaseModel):
    validate_db_urls: bool | None = None
    url_validation_timeout: int | None = Field(None, ge=1, le=60)
    github_token: str | None = None
    librariesio_enabled: bool | None = None
    librariesio_api_key: str | None = None
    ecosystems_enabled: bool | None = None
    ecosystems_api_key: str | None = None
```

- [ ] **Step 2: Update _rebuild_resolvers to include EcosystemsResolver**

Replace the `_rebuild_resolvers` function:

```python
def _rebuild_resolvers(request: Request) -> None:
    store: SettingsStore = request.app.state.settings_store
    app_settings = store.load()

    from .resolver.purl2repo import Purl2RepoResolver
    from .resolver.ecosystems import EcosystemsResolver
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
    if app_settings.ecosystems_enabled:
        resolvers.append(
            EcosystemsResolver(api_key=app_settings.ecosystems_api_key)
        )
    if app_settings.librariesio_enabled and app_settings.librariesio_api_key:
        resolvers.append(
            LibrariesIoResolver(api_key=app_settings.librariesio_api_key)
        )
    request.app.state.resolvers = resolvers
```

- [ ] **Step 3: Update GET /api/v1/settings response**

Replace the `get_settings` function:

```python
@router.get("/api/v1/settings")
async def get_settings(request: Request) -> JSONResponse:
    store: SettingsStore = request.app.state.settings_store
    settings = store.load()
    return JSONResponse(content={
        "validate_db_urls": settings.validate_db_urls,
        "url_validation_timeout": settings.url_validation_timeout,
        "librariesio_enabled": settings.librariesio_enabled,
        "ecosystems_enabled": settings.ecosystems_enabled,
        "token_set": {
            "github_token": settings.github_token is not None,
            "librariesio_api_key": settings.librariesio_api_key is not None,
            "ecosystems_api_key": settings.ecosystems_api_key is not None,
        },
    })
```

- [ ] **Step 4: Update PATCH /api/v1/settings response**

Replace the return statement at the end of `update_settings`:

```python
    _rebuild_resolvers(request)

    return JSONResponse(content={
        "validate_db_urls": updated.validate_db_urls,
        "url_validation_timeout": updated.url_validation_timeout,
        "librariesio_enabled": updated.librariesio_enabled,
        "ecosystems_enabled": updated.ecosystems_enabled,
        "token_set": {
            "github_token": updated.github_token is not None,
            "librariesio_api_key": updated.librariesio_api_key is not None,
            "ecosystems_api_key": updated.ecosystems_api_key is not None,
        },
    })
```

- [ ] **Step 5: Run existing API tests to verify no regression**

Run: `.venv/bin/pytest tests/test_api.py tests/test_main.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/purl_resolver/router.py
git commit -m "feat: integrate EcosystemsResolver into settings and resolver chain"
```

---

### Task 6: Add ecosyste.ms settings card to UI

**Files:**
- Modify: `src/purl_resolver/templates/settings.html`

- [ ] **Step 1: Add HTML card after the Libraries.io card (before the Save button)**

Insert the following HTML block after the closing `</div>` of the Libraries.io card (after line 161, before `<button id="save-btn"`):

```html
        <div class="card" style="margin-top:1rem;">
            <div class="card-title">eCosyste.ms Resolver</div>
            <div class="setting-row">
                <div>
                    <div class="setting-label">Enable ecosyste.ms resolver</div>
                    <div class="setting-desc">
                        Live query to ecosyste.ms API for repository URL lookup.
                        Works without API key. Key is optional for higher rate limits.
                    </div>
                </div>
                <label class="toggle">
                    <input type="checkbox" id="ecosystems-toggle">
                    <span class="toggle-slider"></span>
                </label>
            </div>
            <div class="setting-row">
                <div>
                    <div class="setting-label">API Key (optional)</div>
                    <div class="setting-desc">
                        Optional API key for higher rate limits.
                    </div>
                    <div id="ecosystems-key-status" class="setting-desc" style="margin-top:0.5rem;">
                        Status: <span id="ecosystems-key-badge" style="font-weight:600;">not set</span>
                        <button id="clear-ecosystems-key-btn" class="btn-danger btn-small" style="margin-left:0.5rem;display:none;">Clear key</button>
                    </div>
                </div>
                <div style="text-align:right;">
                    <input type="password" id="ecosystems-key-input"
                           placeholder="eCosyste.ms API key (optional)" style="width:240px;padding:0.5rem;border:1px solid #ccc;border-radius:6px;font-size:0.9rem;">
                </div>
            </div>
        </div>
```

- [ ] **Step 2: Add JavaScript variables and update load/save/clear functions**

In the `<script>` section, add new variable declarations after the existing `lioClearBtn` line:

```javascript
        const ecoToggle = document.getElementById("ecosystems-toggle");
        const ecoKeyInput = document.getElementById("ecosystems-key-input");
        const ecoBadge = document.getElementById("ecosystems-key-badge");
        const ecoClearBtn = document.getElementById("clear-ecosystems-key-btn");
```

In the `loadSettings()` function, add after the `lioClearBtn` line:

```javascript
                ecoToggle.checked = data.ecosystems_enabled;
                ecoBadge.textContent = data.token_set.ecosystems_api_key ? "set" : "not set";
                ecoBadge.style.color = data.token_set.ecosystems_api_key ? "#166534" : "#991b1b";
                ecoClearBtn.style.display = data.token_set.ecosystems_api_key ? "inline-block" : "none";
```

In the `saveSettings()` function, add after `body.librariesio_api_key = lioKeyInput.value.trim();`:

```javascript
                body.ecosystems_enabled = ecoToggle.checked;
                if (ecoKeyInput.value.trim() !== "") {
                    body.ecosystems_api_key = ecoKeyInput.value.trim();
                }
```

In the `saveSettings()` function, add after `lioKeyInput.value = "";`:

```javascript
                    ecoKeyInput.value = "";
```

Add a new `clearEcosystemsKey` function after `clearLibrariesIoKey`:

```javascript
        async function clearEcosystemsKey() {
            ecoClearBtn.disabled = true;
            try {
                const res = await fetch("/api/v1/settings", {
                    method: "PATCH",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ ecosystems_api_key: null }),
                });
                if (res.ok) {
                    showMessage("eCosyste.ms key cleared", false);
                    loadSettings();
                } else {
                    const data = await res.json();
                    showMessage(data.message || "Failed to clear key", true);
                }
            } catch {
                showMessage("Network error", true);
            } finally {
                ecoClearBtn.disabled = false;
            }
        }
```

Add event listener after `lioClearBtn.addEventListener`:

```javascript
        ecoClearBtn.addEventListener("click", clearEcosystemsKey);
```

- [ ] **Step 3: Verify the settings page loads correctly**

Run: `.venv/bin/uvicorn purl_resolver.main:app --port 8000` and open `http://localhost:8000/settings`
Expected: New "eCosyste.ms Resolver" card visible with toggle and API key input

- [ ] **Step 4: Commit**

```bash
git add src/purl_resolver/templates/settings.html
git commit -m "feat: add ecosyste.ms resolver card to settings page"
```

---

### Task 7: Update specs and ADR

**Files:**
- Modify: `specs/domains/purl-resolution.md:143-167`
- Modify: `specs/architecture/layers.md:65-69`
- Create: `docs/adr/0005-ecosyste-ms-as-fallback-resolver.md`

- [ ] **Step 1: Add configuration fields to purl-resolution.md**

In `specs/domains/purl-resolution.md`, add to the JSON Settings table after `librariesio_api_key`:

```markdown
| `ecosystems_enabled` | `true` | Enable ecosyste.ms as a fallback resolver after purl2repo |
| `ecosystems_api_key` | `null` | Optional API key for ecosyste.ms (higher rate limits) |
```

- [ ] **Step 2: Add EcosystemsResolver to layers.md**

In `specs/architecture/layers.md`, add `EcosystemsResolver` to the Resolver Layer diagram after `LibrariesIoResolver`:

```
|  |  Resolver (ABC)             |                   |
|  |  Resolution dataclass       |                   |
|  |  Purl2RepoResolver          |                   |
|  |  EcosystemsResolver         |                   |
|  |  LibrariesIoResolver        |                   |
|  |  (future: LLM, purl2src)   |                   |
```

Also update the Resolver Layer description in "Layer Responsibilities" section to mention `EcosystemsResolver`.

- [ ] **Step 3: Create ADR-0005**

Create `docs/adr/0005-ecosyste-ms-as-fallback-resolver.md`:

```markdown
# ADR-0005: ecosyste.ms as fallback resolver

## Context

purl2repo does not support all ecosystems. libraries.io improves coverage but requires an API key for reasonable rate limits. A free, no-auth data source is needed to improve coverage further.

## Decision

Add ecosyste.ms as a fallback resolver between purl2repo and libraries.io. It is:
- Enabled by default (no API key required)
- Tried only after purl2repo fails to find a repository URL
- Uses `httpx` (synchronous) with a 15-second timeout
- Errors are logged as warnings and do not interrupt processing (graceful degradation)
- Optional API key for higher rate limits (no validation — API does not distinguish valid/invalid keys)

## Consequences

- Improved PURL resolution coverage for ecosystems not supported by purl2repo
- Enabled by default — no configuration needed for basic usage
- Graceful degradation: ecosyste.ms outages do not affect the primary resolver
- Resolver chain order: purl2repo → ecosyste.ms → libraries.io
- Resolver name stored in DB results distinguishes resolution source
```

- [ ] **Step 4: Commit**

```bash
git add specs/domains/purl-resolution.md specs/architecture/layers.md docs/adr/0005-ecosyste-ms-as-fallback-resolver.md
git commit -m "docs: update specs and add ADR-0005 for ecosyste.ms resolver"
```

---

### Task 8: Run full test suite and verify

- [ ] **Step 1: Run all tests**

Run: `.venv/bin/pytest tests/ -v --ignore=tests/e2e`
Expected: All tests PASS

- [ ] **Step 2: Run e2e tests (optional, requires network)**

Run: `.venv/bin/pytest tests/e2e/ -v`
Expected: All tests PASS or SKIP (if network unavailable)

- [ ] **Step 3: Final commit if any fixes needed**

```bash
git add -A
git commit -m "fix: address test failures for ecosyste.ms resolver"
```
