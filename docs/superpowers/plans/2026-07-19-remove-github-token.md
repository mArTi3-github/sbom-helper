# Remove GitHub PAT Functionality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove all GitHub Personal Access Token functionality from backend, frontend, i18n, and tests.

**Architecture:** The token is removed layer-by-layer — data model first, then URL validator plumbing, then service layer, then frontend types/store, then UI/i18n. Each task carries its own test changes for independent verification.

**Tech Stack:** Python 3.12 / FastAPI / Pydantic v2 / Vue 3 / Pinia / Vitest

## Global Constraints

- Pydantic's default `extra="ignore"` ensures old `settings.json` loads without error — no migration needed.
- `token_set` in API responses must still include `librariesio_api_key` and `ecosystems_api_key`.
- libraries.io and ecosystems key UI must be unaffected.
- All existing tests must pass after each task.

---

### Task 1: Backend model + API routes

**Files:**
- Modify: `src/purl_resolver/settings_store.py:20` — remove `github_token` field
- Modify: `src/purl_resolver/routes/settings.py:13,38,88-92,102-114,160-164,175-185` — remove all token handling
- Test: `tests/test_api.py` — remove token-related tests

**Interfaces:**
- Consumes: current `AppSettings` model (before removal)
- Produces: `AppSettings` without `github_token` field; `SettingsUpdate` without `github_token`; settings API without token endpoint

- [ ] **Step 1: Remove `github_token` from `AppSettings`**

In `src/purl_resolver/settings_store.py`, delete line 20:
```python
    github_token: str | None = None
```

- [ ] **Step 2: Remove token-related code from `routes/settings.py`**

Changes:
1. Remove import on line 13: `from ..url_validator import validate_github_token`
2. Remove field from `SettingsUpdate` (line 38): delete `github_token: str | None = None`
3. In `get_settings` response (lines 88-92): remove `"github_token": app_settings.github_token is not None,` from `token_set` dict
4. Delete entire block `if "github_token" in update_data:` (lines 102-114)
5. In `update_settings` response (lines 160-164): remove `"github_token": updated.github_token is not None,` from `token_set` dict
6. Delete entire endpoint `POST /api/v1/settings/check-github-token` (lines 175-185)

- [ ] **Step 3: Remove token-related tests from `test_api.py`**

Delete these test functions:
- `test_get_settings_masks_github_token` (lines 176-183)
- `test_get_settings_shows_token_not_set` (lines 185-191)
- `test_patch_settings_with_valid_token` (lines 193-202)
- `test_patch_settings_with_invalid_token` (lines 204-213)
- `test_patch_empty_string_does_not_clear_token` (lines 215-224)
- `test_patch_null_clears_token` (lines 226-235)
- `test_check_github_token_valid` / `test_check_github_token_invalid` / `test_check_github_token_not_set` (lines 237-258)

- [ ] **Step 4: Run backend tests**

Run: `cd /home/administrator/Desktop/projects/sbom-helper && .venv/bin/python -m pytest tests/test_api.py -v`
Expected: all remaining tests pass

- [ ] **Step 5: Commit**

```bash
git add src/purl_resolver/settings_store.py src/purl_resolver/routes/settings.py tests/test_api.py
git commit -m "feat: remove GitHub token from settings model and API routes"
```

---

### Task 2: Backend url_validator — remove TOKEN_INVALID and token parameters

**Files:**
- Modify: `src/purl_resolver/url_validator.py` — remove TOKEN_INVALID, validate_github_token, validate_url_with_retry, token params/injection
- Modify: `tests/test_url_validator.py` — remove token-related tests
- Modify: `tests/test_vcs_check.py` — remove token-related tests

**Interfaces:**
- Consumes: `UrlValidationResult` (enum modified), `validate_url()` (signature changed)
- Produces: `UrlValidationResult` without `TOKEN_INVALID`; `validate_url(url, timeout)` without `github_token` param; `validate_url_with_retry` deleted; `validate_github_token` deleted

- [ ] **Step 1: Remove `TOKEN_INVALID` from enum**

In `src/purl_resolver/url_validator.py`, delete line 74:
```python
    TOKEN_INVALID = "token_invalid"
```

- [ ] **Step 2: Remove `validate_github_token()` function**

Delete lines 331-341 (the entire function `validate_github_token`).

- [ ] **Step 3: Remove `validate_url_with_retry()` function**

Delete lines 382-405 (the entire function `validate_url_with_retry`). Also remove the `from .settings_store import SettingsStore` import on line 18 — but only if no other code in the file still imports it. Check `TYPE_CHECKING` block.

- [ ] **Step 4: Remove `github_token` parameter from remaining functions**

For each function, remove the `github_token` parameter from signature and any code that uses it:

1. `ensure_connectivity()` (line 84): remove `github_token: str | None = None,` param. Remove lines 97-98 (Authorization header injection).
2. `_head_request()` (line 110): remove `github_token: str | None = None` param. Remove lines 115-116 (Authorization header injection).
3. `_git_probe()` (line 124): remove `github_token: str | None = None` param. Remove lines 129-130 (oauth2 URL rewriting).
4. `_check_vcs()` (line 301): remove `github_token: str | None = None` param. Update line 314 from `("git", lambda: _git_probe(url, timeout, github_token))` to `("git", lambda: _git_probe(url, timeout))`.
5. `validate_url()` (line 347): remove `github_token: str | None = None` param. Remove lines 360-364 (401 TOKEN_INVALID check). Update line 359 from `resp = await _head_request(url, timeout, github_token=github_token)` to `resp = await _head_request(url, timeout)`. Update line 370 from `git_result = await _check_vcs(final_url, timeout, github_token=github_token)` to `git_result = await _check_vcs(final_url, timeout)`.

- [ ] **Step 5: Remove now-unused imports**

If `SettingsStore` from `.settings_store` is no longer referenced anywhere in the file (was only used by `validate_url_with_retry`), remove the `TYPE_CHECKING` import block (lines 17-18).

- [ ] **Step 6: Update `test_url_validator.py`**

Remove these imports if present: `TOKEN_INVALID`, `validate_github_token`, `validate_url_with_retry`.

Delete these test functions/classes:
- Tests that reference `TOKEN_INVALID` — `test_403_with_token_does_not_return_token_invalid`, `test_token_invalid_response`, `test_token_invalid_is_enum_value`
- `TestValidateGithubToken` class (lines 202-222)
- `TestValidateUrlWithRetry` class (lines 262-306)
- Token-specific tests: `test_token_passed_to_head_request`, `test_head_request_with_bearer_token`, `test_git_ls_remote_with_token_in_url`

Update remaining tests that still pass `github_token` parameter — remove the param from calls.

- [ ] **Step 7: Update `test_vcs_check.py`**

Remove these tests:
- `test_github_token_rewrites_url` (lines 264-269)
- `test_non_github_url_no_token_injection` (lines 272-277)

- [ ] **Step 8: Run backend tests**

```bash
.venv/bin/python -m pytest tests/test_url_validator.py tests/test_vcs_check.py -v
```
Expected: all remaining tests pass (may see fewer tests, which is expected)

- [ ] **Step 9: Commit**

```bash
git add src/purl_resolver/url_validator.py tests/test_url_validator.py tests/test_vcs_check.py
git commit -m "feat: remove TOKEN_INVALID, validate_github_token, and token params from url_validator"
```

---

### Task 3: Backend service layer — remove token passing

**Files:**
- Modify: `src/purl_resolver/validation_service.py` — remove `github_token` param, replace `validate_url_with_retry` with `validate_url`
- Modify: `src/purl_resolver/service.py` — remove `github_token=app_settings.github_token` from calls
- Modify: `src/purl_resolver/sbom_enrichment.py` — remove token reading and passing, replace `validate_url_with_retry` with `validate_url`
- Modify: `tests/test_service_validation.py` — remove token param assertions
- Modify: `tests/test_sbom_integration.py` — replace `validate_url_with_retry` patches with `validate_url`

- [ ] **Step 1: `validation_service.py`**

Change import on line 6:
```python
# Old:
from .url_validator import UrlValidationOutput, UrlValidationResult, validate_url_with_retry
# New:
from .url_validator import UrlValidationOutput, UrlValidationResult, validate_url
```

Remove `github_token: str | None = None` param from `validate_url()` method signature (line 21).

Change lines 32-36:
```python
# Old:
voutput = await validate_url_with_retry(
    url, timeout,
    github_token=github_token,
    settings_store=self._settings_store,
)
# New:
voutput = await validate_url(url, timeout)
```

- [ ] **Step 2: `service.py`**

Remove `github_token` parameter from two `validate_url` calls:

Line 56: `github_token=app_settings.github_token,` — delete this line
Line 126: `github_token=app_settings.github_token,` — delete this line

- [ ] **Step 3: `sbom_enrichment.py`**

Change import on line 14:
```python
# Old:
from .url_validator import UrlValidationOutput, UrlValidationResult, validate_url_with_retry
# New:
from .url_validator import UrlValidationOutput, UrlValidationResult, validate_url
```

Remove line 61: `val_token = app_settings.github_token`

Change lines 80-84:
```python
# Old:
voutput = await vs.validate_url(ref["url"], timeout=val_timeout, github_token=val_token)
...
voutput = await validate_url_with_retry(
    ref["url"], timeout=val_timeout, github_token=val_token,
)
# New:
voutput = await vs.validate_url(ref["url"], timeout=val_timeout)
...
voutput = await validate_url(ref["url"], timeout=val_timeout)
```

- [ ] **Step 4: Update `test_service_validation.py`**

Remove lines that assert `github_token` parameter was passed:
- Line 409: remove `github_token=mock_settings_store.load().github_token` assertion
- Line 434: remove `github_token=mock_settings_store.load().github_token` assertion

- [ ] **Step 5: Update `test_sbom_integration.py`**

Replace `validate_url_with_retry` with `validate_url` in all patches (lines 104, 147, 185, 219, 265, 307, 349, 391, 433).

- [ ] **Step 6: Run all backend tests**

```bash
.venv/bin/python -m pytest tests/ -v
```
Expected: all tests pass

- [ ] **Step 7: Commit**

```bash
git add src/purl_resolver/validation_service.py src/purl_resolver/service.py src/purl_resolver/sbom_enrichment.py tests/test_service_validation.py tests/test_sbom_integration.py
git commit -m "feat: remove token passing from validation service and SBOM enrichment"
```

---

### Task 4: Frontend types, API, and store

**Files:**
- Modify: `frontend/src/api/settings.ts` — remove `checkGithubToken`
- Modify: `frontend/src/types/api.ts` — remove `github_token` from `SettingsTokenSet` and `SettingsUpdate`
- Modify: `frontend/src/stores/useSettingsStore.ts` — remove token state and methods

- [ ] **Step 1: `frontend/src/api/settings.ts`**

Delete lines 16-18:
```typescript
export function checkGithubToken(): Promise<{ status: 'valid' | 'invalid' }> {
  return apiFetch<{ status: 'valid' | 'invalid' }>('/api/v1/settings/check-github-token', { method: 'POST' })
}
```

- [ ] **Step 2: `frontend/src/types/api.ts`**

In `SettingsTokenSet` (lines 19-23), remove `github_token: boolean`:
```typescript
export interface SettingsTokenSet {
  librariesio_api_key: boolean
  ecosystems_api_key: boolean
}
```

In `SettingsUpdate` (line 50), remove `github_token?: string | null`:
```typescript
// Delete this line:
github_token?: string | null
```

- [ ] **Step 3: `frontend/src/stores/useSettingsStore.ts`**

Changes:
1. Line 3: change import to remove `checkGithubToken`
   ```typescript
   // Old:
   import { getSettings, updateSettings, checkGithubToken as checkGithubTokenApi } from '../api/settings'
   // New:
   import { getSettings, updateSettings } from '../api/settings'
   ```
2. Line 24: delete `const githubTokenValidity = ref<'valid' | 'invalid' | null>(null)`
3. Line 25: delete `const githubToken = ref('')`
4. Line 31: change `hasAnyToken` to remove `github_token`:
   ```typescript
   // Old:
   tokenSet.value.github_token || tokenSet.value.librariesio_api_key || tokenSet.value.ecosystems_api_key
   // New:
   tokenSet.value.librariesio_api_key || tokenSet.value.ecosystems_api_key
   ```
5. Lines 62-64: delete the `if ('github_token' in partial)` block:
   ```typescript
   if ('github_token' in partial) {
     githubToken.value = ''
     githubTokenValidity.value = 'valid'
   }
   ```
6. Line 70: change `clearToken` param type:
   ```typescript
   // Old:
   async function clearToken(field: 'github_token' | 'librariesio_api_key' | 'ecosystems_api_key') {
   // New:
   async function clearToken(field: 'librariesio_api_key' | 'ecosystems_api_key') {
   ```
   And delete line 72: `if (field === 'github_token') githubTokenValidity.value = null`
7. Lines 75-78: delete `checkGithubToken()` method entirely
8. Lines 85-87 (return block): remove `githubToken`, `githubTokenValidity`, `checkGithubToken`

- [ ] **Step 4: Run frontend tests**

```bash
cd frontend && npx vitest run --reporter=verbose 2>&1 | head -60
```
Expected: all tests pass (pre-existing failures excluded)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/settings.ts frontend/src/types/api.ts frontend/src/stores/useSettingsStore.ts
git commit -m "feat: remove GitHub token from frontend types, API, and store"
```

---

### Task 5: Frontend UI, i18n, and tests

**Files:**
- Modify: `frontend/src/views/Settings.vue` — remove GitHub token card
- Modify: `frontend/src/i18n/locales/en.json` — remove token-specific strings
- Modify: `frontend/src/i18n/locales/ru.json` — remove token-specific strings
- Modify: `frontend/src/views/Settings.test.ts` — remove GitHub token card tests

- [ ] **Step 1: `frontend/src/views/Settings.vue` — template**

Delete the entire GitHub token card (lines 117-145):
```html
      <div class="card">
        <div class="card-title">{{ t('settings.githubToken.title') }}</div>
        <div class="setting-row">
          ...
        </div>
      </div>
```

- [ ] **Step 2: `frontend/src/views/Settings.vue` — script**

1. Line 347: remove `githubTokenValidity` from `storeToRefs` destructuring
2. Line 350: delete `const githubTokenInput = ref('')`
3. Line 376: delete `if ('github_token' in partial) githubTokenInput.value = ''`
4. Lines 389-393: delete `onGithubTokenBlur()` function
5. Lines 407-413: delete `clearToken()` function
6. Lines 415-422: delete `onCheckGithubToken()` function

- [ ] **Step 3: `frontend/src/i18n/locales/en.json`**

Remove these keys:
- `errorMessages.tokenClearFailed`
- `errorMessages.tokenCheckFailed`
- `settings.clearToken`
- `settings.checkValidity`
- `settings.valid`
- `settings.invalid`
- `settings.tokenCheckComplete`
- Entire `settings.githubToken` block (title, label, desc, genToken, genTokenHint, status, validity)
- `errors.invalid_token`
- `errors.token_not_set`

Keep: `settings.set`, `settings.notSet`, `settings.clearKey`, `settings.tokenCleared`

- [ ] **Step 4: `frontend/src/i18n/locales/ru.json`**

Same changes as en.json.

- [ ] **Step 5: `frontend/src/views/Settings.test.ts`**

Remove tests for GitHub token card:
- Token save on blur (lines referencing `ghp_test_token`)
- Clear token button test (lines around "Clear token")
- Validity section visibility tests
- Validity after save test
- Check validity button test

Also remove `checkGithubTokenMock` and its injection (lines 31, 36). Remove `token_set: { github_token: true/false }` or simplify to `token_set: { librariesio_api_key: false, ecosystems_api_key: false }`.

- [ ] **Step 6: Run all tests**

Backend:
```bash
.venv/bin/python -m pytest tests/ -v
```

Frontend:
```bash
cd frontend && npx vitest run --reporter=verbose 2>&1 | head -60
```

Expected: all tests pass (pre-existing unrelated failures acceptable)

- [ ] **Step 7: Commit**

```bash
git add frontend/src/views/Settings.vue frontend/src/i18n/locales/en.json frontend/src/i18n/locales/ru.json frontend/src/views/Settings.test.ts
git commit -m "feat: remove GitHub token UI, i18n strings, and frontend tests"
```
