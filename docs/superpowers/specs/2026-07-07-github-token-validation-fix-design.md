# GitHub Token Validation Fix

**Date:** 2026-07-07
**Status:** Draft
**Scope:** url_validator.py, routes/settings.py, Settings.vue, useSettingsStore.ts, types/api.ts, api/settings.ts, tests

## Problem

The GitHub token auto-clears from saved settings without user intent. Root cause: `validate_url()` treats both HTTP 401 and 403 as `TOKEN_INVALID`, and `validate_url_with_retry()` unconditionally deletes the token from settings when `TOKEN_INVALID` is returned.

According to GitHub API documentation:
- **401 Unauthorized** — returned ONLY when the token itself is invalid (expired, revoked, bad credentials). This is a reliable indicator.
- **403 Forbidden** — returned in multiple cases where the token is still valid: rate limit exceeded, insufficient scopes, fine-grained PAT resource owner mismatch, failed login limit. Clearing the token on 403 is incorrect.

The current code at `url_validator.py:343` treats both `resp.status_code in (401, 403)` as `TOKEN_INVALID`, causing valid tokens to be silently removed during URL validation when rate limiting occurs.

## Solution

### 1. Fix auto-clear logic in `url_validator.py`

**`validate_url()`** — change the condition to only return `TOKEN_INVALID` on 401:

```python
# Before:
if resp.status_code in (401, 403) and github_token:

# After:
if resp.status_code == 401 and github_token:
```

For 403, fall through to the normal error handling path (return `NETWORK_ERROR` via the existing exception flow or a new branch). The token remains untouched.

**`validate_url_with_retry()`** — keep the existing auto-clear logic for `TOKEN_INVALID`, which now only triggers on genuine 401. The retry-without-token fallback remains correct: for public repos, the unauthenticated request will succeed; for private repos, it returns 404.

### 2. New endpoint: `POST /api/v1/settings/check-github-token`

Allows the user to manually verify the stored GitHub token from the Settings UI.

```
POST /api/v1/settings/check-github-token
Request: (no body)
Response 200: { "status": "valid" }   ← validate_github_token returned True
Response 200: { "status": "invalid" } ← validate_github_token returned False
Response 400: { "error": "...", "message": "GitHub token is not set" }
```

Implementation:
- Read `github_token` from `SettingsStore`
- If `None` or empty → return 400
- Call existing `validate_github_token(token)` from `url_validator.py`
- Return result as-is (True → "valid", False → "invalid")

### 3. Frontend: validity indicator and check button

**New state in `useSettingsStore`:**
- `githubTokenValidity: ref<'valid' | 'invalid' | null>(null)` — null means "not checked yet"

**Behaviour:**
- Initial load: `githubTokenValidity` = `null` (no label shown until first check)
- After successful PATCH save of a new token: set `githubTokenValidity = 'valid'` (PATCH already validated it)
- After "Check validity" click: POST to new endpoint → set `githubTokenValidity = 'valid' | 'invalid'`
- After "Clear token": set `githubTokenValidity = null`

**UI in Settings.vue** (GitHub API Token card, after Status line):

```html
<div class="setting-desc validity-desc" v-if="tokenSet.github_token">
  Validity:
  <span :class="validityClass">{{ githubTokenValidity ?? '—' }}</span>
  <button class="btn-small btn-secondary" @click="onCheckGithubToken">Check validity</button>
</div>
```

- Button "Check validity" visible only when `tokenSet.github_token === true`
- `valid` — green (`color: var(--color-success)`)
- `invalid` — red (`color: var(--color-error)`)
- `null` — dash `—`

**API client** — add `checkGithubToken()` function in `api/settings.ts`:

```typescript
export function checkGithubToken(): Promise<{ status: 'valid' | 'invalid' }> {
  return apiFetch('/api/v1/settings/check-github-token', { method: 'POST' })
}
```

**TypeScript types** — add `GithubTokenCheckResponse` to `types/api.ts` if needed (inline is fine for a single field).

## Files to Modify

| File | Change |
|------|--------|
| `src/purl_resolver/url_validator.py:343` | Change `401, 403` → `401` only in `validate_url()` |
| `src/purl_resolver/routes/settings.py` | Add `POST /api/v1/settings/check-github-token` endpoint |
| `frontend/src/views/Settings.vue` | Add validity display + "Check validity" button + handler |
| `frontend/src/stores/useSettingsStore.ts` | Add `githubTokenValidity` ref and `checkGithubToken()` action |
| `frontend/src/api/settings.ts` | Add `checkGithubToken()` function |
| `tests/test_url_validator.py` | Update tests: 403 no longer returns TOKEN_INVALID |
| `tests/test_api.py` | Add tests for new endpoint |
| `frontend/src/views/Settings.test.ts` | Add tests for validity UI |

## API Changes

### New endpoint

```
POST /api/v1/settings/check-github-token
→ 200 { "status": "valid" }
→ 200 { "status": "invalid" }
→ 400 { "error": "token_not_set", "message": "GitHub token is not set" }
```

### Modified endpoint

`PATCH /api/v1/settings` — no functional change. Token validation on save remains unchanged.

## Test Scenarios

### Backend
- `validate_url()` with token → 401 → returns `TOKEN_INVALID`
- `validate_url()` with token → 403 → does NOT return `TOKEN_INVALID` (returns NETWORK_ERROR or similar)
- `validate_url()` with token → 200 → returns VALID
- `POST /api/v1/settings/check-github-token` with valid stored token → `{ status: "valid" }`
- `POST /api/v1/settings/check-github-token` with invalid stored token → `{ status: "invalid" }`
- `POST /api/v1/settings/check-github-token` with no stored token → 400
- Token removal on 401 still works via `validate_url_with_retry`
- Token removal does NOT trigger on 403

### Frontend
- Validity label is hidden when token is not set
- Validity label shows `—` initially when token is set
- "Check validity" button triggers POST and updates label
- Saving a new valid token sets validity to "valid" automatically
- Clearing token resets validity to null
