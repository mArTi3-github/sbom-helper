# GitHub API Token in Settings — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `github_token` to application settings for authenticated `git ls-remote` and HTTP requests in `url_validator.py`, increasing GitHub rate limits.

**Architecture:** `ServiceTokens` dataclass holds API tokens, extensible for future services. Token flows from `AppSettings` → `service.py` → `validate_url()` → internal functions. Token is validated on save and invalidated on use.

**Tech Stack:** Python 3.11+, Pydantic, pytest, httpx, asyncio

**Design Spec:** `docs/superpowers/specs/2026-06-04-github-token-settings-design.md`

---

## File Structure

| File | Responsibility |
|------|---------------|
| `src/purl_resolver/settings_store.py` | `ServiceTokens` dataclass, `github_token` field in `AppSettings`, `service_tokens()` method |
| `src/purl_resolver/url_validator.py` | `TOKEN_INVALID` enum value, `github_token` parameter in all functions, authenticated HTTP/git requests |
| `src/purl_resolver/service.py` | Read token from settings, pass to `validate_url()`, handle `TOKEN_INVALID` |
| `src/purl_resolver/router.py` | `SettingsUpdate.github_token`, token validation on save, masked GET response |
| `src/purl_resolver/templates/settings.html` | GitHub token input section with badge and instructions |
| `tests/test_settings_store.py` | Tests for `ServiceTokens`, `github_token` field, roundtrip |
| `tests/test_url_validator.py` | Tests for authenticated requests, `TOKEN_INVALID` |
| `tests/test_api.py` | Integration tests for settings API with token |

---

### Task 1: ServiceTokens + AppSettings

**Files:**
- Modify: `src/purl_resolver/settings_store.py`
- Modify: `tests/test_settings_store.py`

- [ ] **Step 1: Write failing tests for ServiceTokens and github_token**

Add to `tests/test_settings_store.py`:

```python
from purl_resolver.settings_store import ServiceTokens

class TestServiceTokens:
    def test_default_has_no_github_token(self):
        t = ServiceTokens()
        assert t.github_token is None

    def test_with_github_token(self):
        t = ServiceTokens(github_token="ghp_abc123")
        assert t.github_token == "ghp_abc123"


class TestAppSettingsServiceTokens:
    def test_service_tokens_extracts_github_token(self):
        s = AppSettings(github_token="ghp_xyz")
        tokens = s.service_tokens()
        assert isinstance(tokens, ServiceTokens)
        assert tokens.github_token == "ghp_xyz"

    def test_service_tokens_default_is_none(self):
        s = AppSettings()
        tokens = s.service_tokens()
        assert tokens.github_token is None

    def test_github_token_defaults_to_none(self):
        s = AppSettings()
        assert s.github_token is None

    def test_github_token_roundtrip(self, store: SettingsStore):
        original = AppSettings(github_token="ghp_test123")
        store.save(original)
        loaded = store.load()
        assert loaded.github_token == "ghp_test123"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_settings_store.py -v -k "ServiceTokens or service_tokens or github_token"`
Expected: FAIL with `ImportError: cannot import name 'ServiceTokens'`

- [ ] **Step 3: Implement ServiceTokens and AppSettings changes**

In `src/purl_resolver/settings_store.py`, add at the top:

```python
from dataclasses import dataclass

@dataclass
class ServiceTokens:
    github_token: str | None = None
```

In `AppSettings`, add field and method:

```python
class AppSettings(BaseModel):
    validate_db_urls: bool = False
    url_validation_timeout: int = Field(default=5, ge=1, le=60)
    github_token: str | None = None

    def service_tokens(self) -> ServiceTokens:
        return ServiceTokens(github_token=self.github_token)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_settings_store.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/purl_resolver/settings_store.py tests/test_settings_store.py
git commit -m "feat: add ServiceTokens dataclass and github_token to AppSettings"
```

---

### Task 2: TOKEN_INVALID Enum Value

**Files:**
- Modify: `src/purl_resolver/url_validator.py`
- Modify: `tests/test_url_validator.py`

- [ ] **Step 1: Write failing test for TOKEN_INVALID**

Add to `tests/test_url_validator.py`:

```python
class TestTokenInvalidResult:
    def test_token_invalid_is_enum_value(self):
        assert UrlValidationResult.TOKEN_INVALID.value == "token_invalid"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_url_validator.py -v -k "TOKEN_INVALID"`
Expected: FAIL with `AttributeError: TOKEN_INVALID`

- [ ] **Step 3: Add TOKEN_INVALID to UrlValidationResult**

In `src/purl_resolver/url_validator.py`:

```python
class UrlValidationResult(Enum):
    VALID = "valid"
    INVALID = "invalid"
    NETWORK_ERROR = "network_error"
    RATE_LIMITED = "rate_limited"
    TOKEN_INVALID = "token_invalid"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_url_validator.py -v -k "TOKEN_INVALID"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/purl_resolver/url_validator.py tests/test_url_validator.py
git commit -m "feat: add TOKEN_INVALID to UrlValidationResult enum"
```

---

### Task 3: Authenticated URL Validation

**Files:**
- Modify: `src/purl_resolver/url_validator.py`
- Modify: `tests/test_url_validator.py`

- [ ] **Step 1: Write failing tests for token parameters**

Add to `tests/test_url_validator.py`:

```python
class TestValidateUrlWithToken:
    @pytest.mark.asyncio
    async def test_token_passed_to_head_request(self):
        with patch("purl_resolver.url_validator._check_connectivity", new_callable=AsyncMock, return_value=True), \
             patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head, \
             patch("purl_resolver.url_validator._git_ls_remote", new_callable=AsyncMock, return_value=True):
            mock_head.return_value = _mock_head(200)
            await validate_url("https://github.com/psf/requests", timeout=5, github_token="ghp_test")
            mock_head.assert_called_once_with("https://github.com/psf/requests", 5, github_token="ghp_test")

    @pytest.mark.asyncio
    async def test_head_request_with_bearer_token(self):
        with patch("purl_resolver.url_validator._check_connectivity", new_callable=AsyncMock, return_value=True), \
             patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head, \
             patch("purl_resolver.url_validator._git_ls_remote", new_callable=AsyncMock, return_value=True):
            mock_head.return_value = _mock_head(200)
            await validate_url("https://github.com/psf/requests", timeout=5, github_token="ghp_test")
            call_kwargs = mock_head.call_args
            assert call_kwargs[1]["github_token"] == "ghp_test"

    @pytest.mark.asyncio
    async def test_git_ls_remote_with_token_in_url(self):
        with patch("purl_resolver.url_validator._check_connectivity", new_callable=AsyncMock, return_value=True), \
             patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head, \
             patch("purl_resolver.url_validator._git_ls_remote", new_callable=AsyncMock) as mock_git:
            mock_head.return_value = _mock_head(200)
            mock_git.return_value = True
            await validate_url("https://github.com/psf/requests", timeout=5, github_token="ghp_test")
            call_args = mock_git.call_args
            assert call_args[0][0] == "https://github.com/psf/requests"
            assert call_args[1]["github_token"] == "ghp_test"

    @pytest.mark.asyncio
    async def test_token_invalid_response(self):
        with patch("purl_resolver.url_validator._check_connectivity", new_callable=AsyncMock, return_value=True), \
             patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head:
            mock_head.return_value = _mock_response(401, {"x-github-media-type": "v3"})
            result = await validate_url("https://github.com/psf/requests", timeout=5, github_token="ghp_invalid")
            assert result == UrlValidationResult.TOKEN_INVALID
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_url_validator.py -v -k "Token"`
Expected: FAIL (parameter not accepted yet)

- [ ] **Step 3: Add github_token parameter to all functions**

Update `_check_connectivity`:

```python
async def _check_connectivity(github_token: str | None = None) -> bool:
    try:
        import httpx
        headers = {}
        if github_token:
            headers["Authorization"] = f"Bearer {github_token}"
        async with httpx.AsyncClient(timeout=_CONNECTIVITY_TIMEOUT) as client:
            resp = await client.head(_CONNECTIVITY_URL, headers=headers)
            return resp.status_code < 500
    except Exception:
        logger.warning("Connectivity probe to %s failed", _CONNECTIVITY_URL)
        return False
```

Update `_head_request`:

```python
async def _head_request(url: str, timeout: int, github_token: str | None = None):
    import httpx
    headers = {}
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        return await client.head(url, headers=headers)
```

Update `_git_ls_remote`:

```python
async def _git_ls_remote(url: str, timeout: int, github_token: str | None = None) -> bool | None:
    try:
        git_url = url
        if github_token and "github.com" in url:
            git_url = url.replace("https://", f"https://oauth2:{github_token}@")
        proc = await asyncio.create_subprocess_exec(
            "git", "ls-remote", "--exit-code", git_url,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            logger.warning("git ls-remote timed out for %s", url)
            return None
        if proc.returncode == 0:
            return True
        stderr_text = stderr.decode(errors="replace") if stderr else ""
        if "not found" in stderr_text.lower() or "does not exist" in stderr_text.lower():
            return False
        return None
    except FileNotFoundError:
        logger.warning("git not found, skipping git ls-remote check")
        return True
    except Exception:
        return None
```

Update `validate_url`:

```python
async def validate_url(url: str, timeout: int, github_token: str | None = None) -> UrlValidationResult:
    if _RateLimitTracker.is_in_cooldown():
        return UrlValidationResult.VALID

    try:
        github_ok = await _check_connectivity(github_token=github_token)
    except Exception:
        return UrlValidationResult.NETWORK_ERROR

    if not github_ok:
        return UrlValidationResult.NETWORK_ERROR

    try:
        resp = await _head_request(url, timeout, github_token=github_token)
        headers = dict(resp.headers)
        status = resp.status_code
    except Exception:
        _RateLimitTracker.reset()
        return UrlValidationResult.NETWORK_ERROR

    if _is_rate_limited(status, headers):
        _RateLimitTracker.record_rate_limit()
        return UrlValidationResult.RATE_LIMITED

    _RateLimitTracker.reset()

    if status in (401, 403) and github_token:
        return UrlValidationResult.TOKEN_INVALID

    if status in (404, 405):
        return UrlValidationResult.INVALID
    if status == 403:
        return UrlValidationResult.INVALID
    if status >= 400:
        return UrlValidationResult.INVALID

    try:
        git_result = await _git_ls_remote(url, timeout, github_token=github_token)
    except Exception:
        return UrlValidationResult.NETWORK_ERROR
    if git_result is None:
        return UrlValidationResult.NETWORK_ERROR
    if git_result is False:
        return UrlValidationResult.INVALID

    return UrlValidationResult.VALID
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_url_validator.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/purl_resolver/url_validator.py tests/test_url_validator.py
git commit -m "feat: add github_token parameter to url_validator functions"
```

---

### Task 4: Token Validation on Save

**Files:**
- Modify: `src/purl_resolver/url_validator.py`
- Modify: `tests/test_url_validator.py`

- [ ] **Step 1: Write failing test for validate_github_token**

Add to `tests/test_url_validator.py`:

```python
from purl_resolver.url_validator import validate_github_token

class TestValidateGithubToken:
    @pytest.mark.asyncio
    async def test_valid_token_returns_true(self):
        with patch("purl_resolver.url_validator._check_connectivity", new_callable=AsyncMock, return_value=True), \
             patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head:
            mock_head.return_value = _mock_response(200)
            result = await validate_github_token("ghp_valid")
            assert result is True

    @pytest.mark.asyncio
    async def test_invalid_token_returns_false(self):
        with patch("purl_resolver.url_validator._check_connectivity", new_callable=AsyncMock, return_value=True), \
             patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head:
            mock_head.return_value = _mock_response(401)
            result = await validate_github_token("ghp_invalid")
            assert result is False

    @pytest.mark.asyncio
    async def test_network_error_returns_false(self):
        with patch("purl_resolver.url_validator._check_connectivity", new_callable=AsyncMock, return_value=False):
            result = await validate_github_token("ghp_test")
            assert result is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_url_validator.py -v -k "ValidateGithubToken"`
Expected: FAIL with `ImportError: cannot import name 'validate_github_token'`

- [ ] **Step 3: Implement validate_github_token**

Add to `src/purl_resolver/url_validator.py`:

```python
async def validate_github_token(token: str) -> bool:
    """Validate a GitHub token by checking /rate_limit endpoint."""
    try:
        result = await _head_request(
            "https://api.github.com/rate_limit",
            timeout=5,
            github_token=token,
        )
        return result.status_code == 200
    except Exception:
        return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_url_validator.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/purl_resolver/url_validator.py tests/test_url_validator.py
git commit -m "feat: add validate_github_token function for save-time validation"
```

---

### Task 5: Service Layer Token Passing

**Files:**
- Modify: `src/purl_resolver/service.py`
- Modify: `tests/test_service_validation.py` (or new test file)

- [ ] **Step 1: Write failing test for token passing**

Add to a new test or existing test file:

```python
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from purl_resolver.service import resolve_purl
from purl_resolver.settings_store import SettingsStore, AppSettings
from purl_resolver.storage.inmemory import InMemoryCache
from purl_resolver.url_validator import UrlValidationResult

@pytest.mark.asyncio
async def test_resolve_purl_passes_token_to_validate_url():
    storage = InMemoryCache()
    resolver = MagicMock()
    resolver.resolve.return_value = MagicMock(repository_url=None)
    settings_store = MagicMock(spec=SettingsStore)
    settings_store.load.return_value = AppSettings(
        validate_db_urls=True,
        github_token="ghp_test123",
    )
    with patch("purl_resolver.service.validate_url", new_callable=AsyncMock, return_value=UrlValidationResult.VALID) as mock_validate:
        await resolve_purl(
            purl="pkg:pypi/requests@2.31.0",
            storage=storage,
            resolvers=[resolver],
            settings_store=settings_store,
        )
        mock_validate.assert_called()
        call_kwargs = mock_validate.call_args[1]
        assert call_kwargs.get("github_token") == "ghp_test123"

@pytest.mark.asyncio
async def test_resolve_purl_handles_token_invalid():
    storage = InMemoryCache()
    resolver = MagicMock()
    resolver.resolve.return_value = MagicMock(repository_url=None)
    settings_store = MagicMock(spec=SettingsStore)
    settings_store.load.return_value = AppSettings(
        validate_db_urls=True,
        github_token="ghp_invalid",
    )
    with patch("purl_resolver.service.validate_url", new_callable=AsyncMock) as mock_validate, \
         patch.object(settings_store, "save") as mock_save:
        mock_validate.side_effect = [
            UrlValidationResult.TOKEN_INVALID,
            UrlValidationResult.VALID,
        ]
        await resolve_purl(
            purl="pkg:pypi/requests@2.31.0",
            storage=storage,
            resolvers=[resolver],
            settings_store=settings_store,
        )
        mock_save.assert_called_once()
        saved_settings = mock_save.call_args[0][0]
        assert saved_settings.github_token is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_service_validation.py -v -k "token"`
Expected: FAIL

- [ ] **Step 3: Update resolve_purl to pass token**

In `src/purl_resolver/service.py`, update the URL validation section:

```python
# URL validation
if settings_store is not None:
    app_settings = settings_store.load()
    if app_settings.validate_db_urls:
        resolved_date = None
        if cached.resolved_at:
            try:
                resolved_date = datetime.fromisoformat(cached.resolved_at).date()
            except (ValueError, TypeError):
                pass
        if resolved_date != datetime.now().date():
            github_token = app_settings.github_token
            vresult = await validate_url(
                cached.repository_url,
                app_settings.url_validation_timeout,
                github_token=github_token,
            )
            if vresult == UrlValidationResult.TOKEN_INVALID:
                logger.warning("GitHub token invalid, removing from settings")
                settings_store.save(app_settings.model_copy(update={"github_token": None}))
                vresult = await validate_url(
                    cached.repository_url,
                    app_settings.url_validation_timeout,
                    github_token=None,
                )
            if vresult == UrlValidationResult.VALID:
                # ... existing code
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/purl_resolver/service.py tests/
git commit -m "feat: pass github_token through service layer to url_validator"
```

---

### Task 6: API Contract Changes

**Files:**
- Modify: `src/purl_resolver/router.py`
- Modify: `tests/test_api.py`

- [ ] **Step 1: Write failing tests for settings API**

Add to `tests/test_api.py`:

```python
class TestSettingsAPI:
    def test_get_settings_masks_github_token(self, client: TestClient) -> None:
        client.app.state.settings_store = SettingsStore(path="/tmp/test_settings.json")
        client.app.state.settings_store.save(AppSettings(github_token="ghp_secret"))
        response = client.get("/api/v1/settings")
        assert response.status_code == 200
        data = response.json()
        assert "github_token" not in data
        assert data["token_set"]["github_token"] is True

    def test_get_settings_shows_token_not_set(self, client: TestClient) -> None:
        client.app.state.settings_store = SettingsStore(path="/tmp/test_settings2.json")
        client.app.state.settings_store.save(AppSettings())
        response = client.get("/api/v1/settings")
        assert response.status_code == 200
        data = response.json()
        assert data["token_set"]["github_token"] is False

    def test_patch_settings_with_valid_token(self, client: TestClient) -> None:
        client.app.state.settings_store = SettingsStore(path="/tmp/test_settings3.json")
        with patch("purl_resolver.router.validate_github_token", new_callable=AsyncMock, return_value=True):
            response = client.patch(
                "/api/v1/settings",
                json={"github_token": "ghp_valid"},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["token_set"]["github_token"] is True

    def test_patch_settings_with_invalid_token(self, client: TestClient) -> None:
        client.app.state.settings_store = SettingsStore(path="/tmp/test_settings4.json")
        with patch("purl_resolver.router.validate_github_token", new_callable=AsyncMock, return_value=False):
            response = client.patch(
                "/api/v1/settings",
                json={"github_token": "ghp_invalid"},
            )
        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "invalid_token"

    def test_patch_settings_clears_token_with_empty_string(self, client: TestClient) -> None:
        client.app.state.settings_store = SettingsStore(path="/tmp/test_settings5.json")
        client.app.state.settings_store.save(AppSettings(github_token="ghp_old"))
        response = client.patch(
            "/api/v1/settings",
            json={"github_token": ""},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["token_set"]["github_token"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_api.py -v -k "Settings"`
Expected: FAIL

- [ ] **Step 3: Update SettingsUpdate and router**

In `src/purl_resolver/router.py`, update `SettingsUpdate`:

```python
class SettingsUpdate(BaseModel):
    validate_db_urls: bool | None = None
    url_validation_timeout: int | None = Field(None, ge=1, le=60)
    github_token: str | None = None
```

Add import:

```python
from .url_validator import validate_github_token
```

Update `get_settings`:

```python
@router.get("/api/v1/settings")
async def get_settings(request: Request) -> JSONResponse:
    store: SettingsStore = request.app.state.settings_store
    settings = store.load()
    return JSONResponse(content={
        "validate_db_urls": settings.validate_db_urls,
        "url_validation_timeout": settings.url_validation_timeout,
        "token_set": {
            "github_token": settings.github_token is not None,
        },
    })
```

Update `update_settings`:

```python
@router.patch("/api/v1/settings")
async def update_settings(body: SettingsUpdate, request: Request) -> JSONResponse:
    store: SettingsStore = request.app.state.settings_store
    current = store.load()
    update_data = body.model_dump(exclude_unset=True)

    if "github_token" in update_data:
        token_value = update_data["github_token"]
        if token_value == "" or token_value is None:
            update_data["github_token"] = None
        else:
            is_valid = await validate_github_token(token_value)
            if not is_valid:
                return JSONResponse(
                    status_code=400,
                    content={"error": "invalid_token", "message": "GitHub token is invalid or expired"},
                )

    if update_data:
        updated = current.model_copy(update=update_data)
        store.save(updated)
    else:
        updated = current

    return JSONResponse(content={
        "validate_db_urls": updated.validate_db_urls,
        "url_validation_timeout": updated.url_validation_timeout,
        "token_set": {
            "github_token": updated.github_token is not None,
        },
    })
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_api.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/purl_resolver/router.py tests/test_api.py
git commit -m "feat: update settings API for github_token with validation and masking"
```

---

### Task 7: Settings UI

**Files:**
- Modify: `src/purl_resolver/templates/settings.html`

- [ ] **Step 1: Add GitHub token section to settings.html**

Add after the "URL Validation" card:

```html
<div class="card" style="margin-top:1rem;">
    <div class="card-title">GitHub API Token</div>
    <div class="setting-row">
        <div>
            <div class="setting-label">GitHub Personal Access Token</div>
            <div class="setting-desc">
                Used for authenticated git ls-remote and HTTP requests.
                Increases rate limits from 60/hr to 5000/hr for API,
                and removes limits for git operations.
            </div>
            <div class="setting-desc" style="margin-top:0.25rem;">
                <a href="https://github.com/settings/tokens" target="_blank" style="color:#2563eb;">
                    Generate token
                </a> → Settings → Developer settings → Personal access tokens → Fine-grained or classic
            </div>
            <div id="token-status" class="setting-desc" style="margin-top:0.5rem;">
                Status: <span id="token-badge" style="font-weight:600;">not set</span>
            </div>
        </div>
        <div style="text-align:right;">
            <input type="password" id="token-input"
                   placeholder="ghp_..." style="width:240px;padding:0.5rem;border:1px solid #ccc;border-radius:6px;font-size:0.9rem;">
        </div>
    </div>
</div>
```

- [ ] **Step 2: Update JavaScript to handle token**

Update the `loadSettings` function:

```javascript
async function loadSettings() {
    try {
        const res = await fetch("/api/v1/settings");
        const data = await res.json();
        toggle.checked = data.validate_db_urls;
        timeoutInput.value = data.url_validation_timeout;
        const badge = document.getElementById("token-badge");
        badge.textContent = data.token_set.github_token ? "set" : "not set";
        badge.style.color = data.token_set.github_token ? "#166534" : "#991b1b";
    } catch {
        showMessage("Failed to load settings", true);
    }
}
```

Update the `saveSettings` function:

```javascript
async function saveSettings() {
    saveBtn.disabled = true;
    try {
        const body = {
            validate_db_urls: toggle.checked,
            url_validation_timeout: parseInt(timeoutInput.value, 10),
        };
        const tokenInput = document.getElementById("token-input");
        if (tokenInput.value.trim() !== "") {
            body.github_token = tokenInput.value.trim();
        }
        const res = await fetch("/api/v1/settings", {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });
        if (res.ok) {
            showMessage("Settings saved", false);
            tokenInput.value = "";
            loadSettings();
        } else {
            const data = await res.json();
            showMessage(data.message || "Failed to save settings", true);
        }
    } catch {
        showMessage("Network error", true);
    } finally {
        saveBtn.disabled = false;
    }
}
```

- [ ] **Step 3: Run all tests**

Run: `.venv/bin/pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add src/purl_resolver/templates/settings.html
git commit -m "feat: add GitHub token section to settings page"
```

---

### Task 8: Spec Update

**Files:**
- Modify: `specs/contracts/api-contract.md`
- Modify: `specs/domains/purl-resolution.md`
- Modify: `specs/architecture/layers.md`

- [ ] **Step 1: Update API contract**

In `specs/contracts/api-contract.md`, update `GET /api/v1/settings` and `PATCH /api/v1/settings` sections to reflect the new `token_set` field and `github_token` parameter.

- [ ] **Step 2: Update domain spec**

In `specs/domains/purl-resolution.md`, add `github_token` to the Configuration table.

- [ ] **Step 3: Update architecture layers**

In `specs/architecture/layers.md`, update the Settings Store description to mention `ServiceTokens` and `github_token`.

- [ ] **Step 4: Run all tests one final time**

Run: `.venv/bin/pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add specs/
git commit -m "docs: update specs for github_token feature"
```

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-04-github-token-settings.md`.

Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
