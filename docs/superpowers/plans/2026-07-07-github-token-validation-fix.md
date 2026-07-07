# GitHub Token Validation Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix GitHub token auto-clear logic (only clear on 401, not 403) and add manual "Check validity" button in Settings UI.

**Architecture:** Backend changes in `url_validator.py` (one condition change) + new endpoint `POST /api/v1/settings/check-github-token` in `routes/settings.py`. Frontend changes in `Settings.vue`, `useSettingsStore.ts`, `api/settings.ts`.

**Tech Stack:** Python (FastAPI, httpx, Pydantic), Vue 3 (Pinia, Vitest), TypeScript

## Global Constraints

- Token must never be cleared on HTTP 403 response from GitHub
- Token must still be auto-cleared on HTTP 401 from GitHub (with retry without token for public repos)
- New endpoint must reuse existing `validate_github_token()` function from `url_validator.py`
- Frontend validity state has three values: `'valid' | 'invalid' | null`
- After successful PATCH save of a new token, frontend auto-sets validity to `'valid'`
- "Check validity" button visible only when token is set
- Use `.venv` virtual environment for Python, npm for frontend

---

### Task 1: Backend — fix TOKEN_INVALID condition in `validate_url()`

**Files:**
- Modify: `src/purl_resolver/url_validator.py:343`
- Test: `tests/test_url_validator.py`

**Interfaces:**
- Consumes: existing `validate_url(url, timeout, github_token)` — no signature change
- Produces: `TOKEN_INVALID` now returned only on HTTP 401 (not 403)

- [ ] **Step 1: Read the current code**

Read `src/purl_resolver/url_validator.py` lines 327-362 to confirm the current condition.

- [ ] **Step 2: Change the condition**

In `src/purl_resolver/url_validator.py:343`, change:

```python
if resp.status_code in (401, 403) and github_token:
```

to:

```python
if resp.status_code == 401 and github_token:
```

- [ ] **Step 3: Write a test that 403 with token does NOT return TOKEN_INVALID**

Add to `tests/test_url_validator.py` in class `TestValidateUrlWithToken`:

```python
@pytest.mark.asyncio
async def test_403_with_token_does_not_return_token_invalid(self):
    with patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head, \
         patch("purl_resolver.url_validator._check_vcs", new_callable=AsyncMock, return_value=True):
        mock_head.return_value = _mock_response(403, {"x-github-media-type": "v3"})
        result = await validate_url(
            "https://github.com/psf/requests", timeout=5, github_token="ghp_valid_token"
        )
        assert result.result != UrlValidationResult.TOKEN_INVALID
```

- [ ] **Step 4: Verify the existing test `test_head_403_without_token_ignored` still passes**

This test already exists at line 51 — it verifies 403 without a token. Just verify it still passes.

- [ ] **Step 5: Verify the existing test `test_token_invalid_response` still passes**

This test at line 179 checks that 401 with token returns TOKEN_INVALID. It must still pass.

- [ ] **Step 6: Run all url_validator tests**

```bash
cd /home/administrator/Desktop/projects/sbom-helper
.venv/bin/python -m pytest tests/test_url_validator.py -v
```

Expected: all tests pass, including the new one.

- [ ] **Step 7: Commit**

```bash
git add src/purl_resolver/url_validator.py tests/test_url_validator.py
git commit -m "fix(url_validator): only return TOKEN_INVALID on 401, not 403"
```

---

### Task 2: Backend — add `POST /api/v1/settings/check-github-token` endpoint

**Files:**
- Modify: `src/purl_resolver/routes/settings.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `validate_github_token(token)` from `url_validator.py`, `SettingsStore` from `request.app.state.settings_store`
- Produces: `POST /api/v1/settings/check-github-token` → `200 { "status": "valid"|"invalid" }` or `400 { "error": "token_not_set", "message": "..." }`

- [ ] **Step 1: Add the endpoint**

Add to `src/purl_resolver/routes/settings.py` after the `clear-validation-cache` endpoint (after line 163):

```python
@router.post("/api/v1/settings/check-github-token")
async def check_github_token(request: Request) -> JSONResponse:
    store: SettingsStore = request.app.state.settings_store
    app_settings = store.load()
    token = app_settings.github_token
    if not token:
        return JSONResponse(
            status_code=400,
            content={"error": "token_not_set", "message": "GitHub token is not set"},
        )
    is_valid = await validate_github_token(token)
    return JSONResponse(content={"status": "valid" if is_valid else "invalid"})
```

- [ ] **Step 2: Write tests**

Add to `tests/test_api.py` in the settings test class (find the right class — look for an existing settings test class or create a new one after the GitHub token tests around line 241):

```python
def test_check_github_token_valid(self, client: TestClient, tmp_path) -> None:
    client.app.state.settings_store = SettingsStore(path=tmp_path / "check1.json")
    client.app.state.settings_store.save(AppSettings(github_token="ghp_valid"))
    with patch("purl_resolver.routes.settings.validate_github_token", new_callable=AsyncMock, return_value=True):
        response = client.post("/api/v1/settings/check-github-token")
    assert response.status_code == 200
    assert response.json() == {"status": "valid"}

def test_check_github_token_invalid(self, client: TestClient, tmp_path) -> None:
    client.app.state.settings_store = SettingsStore(path=tmp_path / "check2.json")
    client.app.state.settings_store.save(AppSettings(github_token="ghp_invalid"))
    with patch("purl_resolver.routes.settings.validate_github_token", new_callable=AsyncMock, return_value=False):
        response = client.post("/api/v1/settings/check-github-token")
    assert response.status_code == 200
    assert response.json() == {"status": "invalid"}

def test_check_github_token_not_set(self, client: TestClient, tmp_path) -> None:
    client.app.state.settings_store = SettingsStore(path=tmp_path / "check3.json")
    client.app.state.settings_store.save(AppSettings(github_token=None))
    response = client.post("/api/v1/settings/check-github-token")
    assert response.status_code == 400
    assert response.json()["error"] == "token_not_set"
```

Check the top of `test_api.py` to see what imports exist — you'll likely need to add `from purl_resolver.routes.settings import validate_github_token` patching path. The existing tests use `from unittest.mock import patch` and `from purl_resolver.settings_store import AppSettings, SettingsStore`.

- [ ] **Step 3: Run the tests**

```bash
cd /home/administrator/Desktop/projects/sbom-helper
.venv/bin/python -m pytest tests/test_api.py -v -k "check_github_token"
```

Expected: all 3 new tests pass.

- [ ] **Step 4: Full test run for affected modules**

```bash
cd /home/administrator/Desktop/projects/sbom-helper
.venv/bin/python -m pytest tests/test_api.py tests/test_url_validator.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/purl_resolver/routes/settings.py tests/test_api.py
git commit -m "feat(settings): add POST /api/v1/settings/check-github-token endpoint"
```

---

### Task 3: Frontend — add `checkGithubToken()` API and store

**Files:**
- Modify: `frontend/src/api/settings.ts`
- Modify: `frontend/src/stores/useSettingsStore.ts`
- Modify: `frontend/src/types/api.ts`

**Interfaces:**
- Consumes: `SettingsUpdate` type from `api.ts`, existing store pattern
- Produces: `checkGithubToken(): Promise<{status: 'valid'|'invalid'}>` in API, `githubTokenValidity: Ref<'valid'|'invalid'|null>` and `checkGithubToken(): Promise<void>` in store

- [ ] **Step 1: Add API function**

In `frontend/src/api/settings.ts`, add:

```typescript
export function checkGithubToken(): Promise<{ status: 'valid' | 'invalid' }> {
  return apiFetch<{ status: 'valid' | 'invalid' }>('/api/v1/settings/check-github-token', { method: 'POST' })
}
```

- [ ] **Step 2: Add store state and action**

In `frontend/src/stores/useSettingsStore.ts`:

Add `githubTokenValidity` ref after `tokenSet` (line 22):

```typescript
const githubTokenValidity = ref<'valid' | 'invalid' | null>(null)
```

Add `checkGithubToken()` action after `clearToken()` (line 64):

```typescript
async function checkGithubToken() {
  const result = await checkGithubTokenApi()
  githubTokenValidity.value = result.status
}
```

Update the imports at the top to include `checkGithubToken` (rename the API import to avoid name collision; or import with alias):

```typescript
import { getSettings, updateSettings, checkGithubToken as checkGithubTokenApi } from '../api/settings'
```

Update the return block (line 68) to include `githubTokenValidity` and `checkGithubToken`:

In the return object, add:
```typescript
githubTokenValidity, checkGithubToken,
```

Update `save()` function (line 56) — after a successful save of `github_token`, set validity to `'valid'`:

```typescript
async function save(partial: SettingsUpdate) {
  const data = await updateSettings(partial)
  tokenSet.value = data.token_set
  if ('github_token' in partial) {
    githubToken.value = ''
    githubTokenValidity.value = 'valid'  // PATCH already validated the token
  }
  if ('librariesio_api_key' in partial) librariesioKey.value = ''
  if ('ecosystems_api_key' in partial) ecosystemsKey.value = ''
}
```

Update `clearToken()` to reset validity:

```typescript
async function clearToken(field: 'github_token' | 'librariesio_api_key' | 'ecosystems_api_key') {
  await updateSettings({ [field]: null } as SettingsUpdate)
  if (field === 'github_token') githubTokenValidity.value = null
}
```

- [ ] **Step 3: Run existing frontend tests to verify no regressions**

```bash
cd /home/administrator/Desktop/projects/sbom-helper/frontend
npx vitest run --reporter=verbose src/views/Settings.test.ts
```

Expected: all existing tests pass.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/settings.ts frontend/src/stores/useSettingsStore.ts
git commit -m "feat(settings): add checkGithubToken API and store state"
```

---

### Task 4: Frontend — add validity UI to Settings.vue

**Files:**
- Modify: `frontend/src/views/Settings.vue`
- Test: `frontend/src/views/Settings.test.ts`

**Interfaces:**
- Consumes: `githubTokenValidity`, `checkGithubToken()` from store, `tokenSet.github_token` for visibility
- Produces: Validity display + "Check validity" button in the GitHub API Token card

- [ ] **Step 1: Add store refs to the component**

In `frontend/src/views/Settings.vue`, add `githubTokenValidity` to the destructured store refs (around line 318):

```typescript
const {
  validateDbUrls, validateSbomRefs, sbomMultipleVcsBehavior, urlValidationTimeout, revalidationCooldownHours,
  retryMaxAttempts, retryBaseCooldownSeconds, logLevel,
  librariesioEnabled, ecosystemsEnabled, ecosystemsMaxRequestsPerSecond,
  batchSemaphoreLimit, connectivityUrl, connectivityTimeout,
  tokenSet, loading, jsonIndent, githubTokenValidity,
} = storeToRefs(store)
```

- [ ] **Step 2: Add handler function**

Add after `clearToken()` (around line 379):

```typescript
async function onCheckGithubToken() {
  try {
    await store.checkGithubToken()
    showToast('Token check complete', false)
  } catch {
    showToast('Failed to check token', true)
  }
}
```

- [ ] **Step 3: Add validity template to the GitHub card**

In the template, after the Status line in the GitHub API Token card (after line 117, inside the `<div class="setting-desc status-desc">` block or as a new sibling):

```html
<div v-if="tokenSet.github_token" class="setting-desc validity-desc">
  Validity:
  <span v-if="githubTokenValidity === 'valid'" class="status-valid">{{ githubTokenValidity }}</span>
  <span v-else-if="githubTokenValidity === 'invalid'" class="status-invalid">{{ githubTokenValidity }}</span>
  <span v-else>&mdash;</span>
  <button class="btn-small btn-secondary" @click="onCheckGithubToken">Check validity</button>
</div>
```

- [ ] **Step 4: Add CSS styles**

Add to the `<style scoped>` block (after `.status-not-set` around line 501):

```css
.status-valid {
  font-weight: 600;
  color: var(--color-success);
}

.status-invalid {
  font-weight: 600;
  color: var(--color-error);
}

.validity-desc {
  margin-top: 0.25rem;
}

.btn-secondary {
  background: var(--color-bg-secondary, #e2e8f0);
  color: var(--color-text, #1a202c);
  border: 1px solid var(--color-border, #cbd5e1);
  border-radius: var(--border-radius);
  cursor: pointer;
}

.btn-secondary:hover {
  background: var(--color-bg-secondary-hover, #cbd5e1);
}
```

- [ ] **Step 5: Write frontend tests**

Add to `frontend/src/views/Settings.test.ts`. First update the mock to also mock `checkGithubToken`:

Update the mock block (line 29-32) to include checkGithubToken:

```typescript
const checkGithubTokenMock = vi.fn()

vi.mock('../api/settings', () => ({
  getSettings: () => getSettingsMock(),
  updateSettings: (body: unknown) => successUpdate(body),
  checkGithubToken: () => checkGithubTokenMock(),
}))
```

Add new tests inside or after the existing describe block (before the closing bracket):

```typescript
it('shows validity section when token is set', async () => {
  getSettingsMock.mockResolvedValueOnce({
    ...defaultSettings,
    token_set: { github_token: true, librariesio_api_key: false, ecosystems_api_key: false },
  })
  const wrapper = mountSettings()
  await flushPromises()

  const validitySection = wrapper.find('.validity-desc')
  expect(validitySection.exists()).toBe(true)
  expect(validitySection.text()).toContain('Check validity')
})

it('hides validity section when token is not set', async () => {
  const wrapper = mountSettings()
  await flushPromises()

  expect(wrapper.find('.validity-desc').exists()).toBe(false)
})

it('sets validity to valid after successful token save', async () => {
  getSettingsMock.mockResolvedValueOnce(defaultSettings)
  // After save, the response shows token as set
  successUpdate.mockResolvedValue({
    ...defaultSettings,
    token_set: { github_token: true, librariesio_api_key: false, ecosystems_api_key: false },
  })
  const wrapper = mountSettings()
  await flushPromises()

  // Trigger a token save
  const pwInputs = wrapper.findAll<HTMLInputElement>('input[type="password"]')
  await pwInputs[0].setValue('ghp_new_token')
  await pwInputs[0].trigger('blur')
  await flushPromises()

  // After successful PATCH, validity should show as "valid"
  const validitySection = wrapper.find('.validity-desc')
  expect(validitySection.text()).toContain('valid')
})

it('calls checkGithubToken on button click', async () => {
  checkGithubTokenMock.mockResolvedValue({ status: 'valid' })
  getSettingsMock.mockResolvedValueOnce({
    ...defaultSettings,
    token_set: { github_token: true, librariesio_api_key: false, ecosystems_api_key: false },
  })
  const wrapper = mountSettings()
  await flushPromises()

  const checkBtn = wrapper.find('.validity-desc .btn-secondary')
  expect(checkBtn.exists()).toBe(true)
  await checkBtn.trigger('click')
  await flushPromises()

  expect(checkGithubTokenMock).toHaveBeenCalledTimes(1)
})
```

- [ ] **Step 6: Run frontend tests**

```bash
cd /home/administrator/Desktop/projects/sbom-helper/frontend
npx vitest run --reporter=verbose
```

Expected: all tests pass (old + new).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/views/Settings.vue frontend/src/views/Settings.test.ts
git commit -m "feat(settings): add token validity check UI"
```

---

### Task 5: Final verification

- [ ] **Step 1: Run all backend tests**

```bash
cd /home/administrator/Desktop/projects/sbom-helper
.venv/bin/python -m pytest tests/ -v
```

Expected: all backend tests pass.

- [ ] **Step 2: Run all frontend tests**

```bash
cd /home/administrator/Desktop/projects/sbom-helper/frontend
npx vitest run --reporter=verbose
```

Expected: all frontend tests pass.

- [ ] **Step 3: Check git status**

```bash
cd /home/administrator/Desktop/projects/sbom-helper
git status
git log --oneline -5
```
