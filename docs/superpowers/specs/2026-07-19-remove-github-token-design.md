# Remove GitHub Personal Access Token Functionality

## Status

Approved

## Context

The GitHub Personal Access Token (PAT) is never used in practice. All URL validation requests to github.com are unauthenticated — the token is only useful for `api.github.com` endpoints. The token was consumed only in:

- `ensure_connectivity()` — HEAD to `connectivity_url` (default `https://github.com`, not `api.github.com`)
- `_head_request()` — HEAD to the resolved repository URL (always `github.com/org/repo`, never `api.github.com`)
- `_git_probe()` — `git ls-remote` to `github.com/org/repo` (no auth required for public repos)

Since sbom-helper assumes all repositories are public, the token provides zero value. The option to retry with `oauth2:token@` for private repos was not pursued by design.

The previous iteration (2026-07-07) fixed the 401/403 confusion and added a manual "Check validity" button, but the core issue remains: the token is never sent to an endpoint that would use it, making the entire feature dead weight.

## Decision

Remove the GitHub PAT functionality entirely: backend model, URL validation plumbing, API endpoints, frontend UI, i18n strings, and all tests.

## Detailed Design

### 1. Backend — Data model (`settings_store.py`, `routes/settings.py`)

- **`AppSettings`** (`settings_store.py:20`): remove `github_token: str | None = None` field.
  Pydantic v2 default `extra="ignore"` ensures old `settings.json` with `github_token` load without error; the field disappears from the file on next `save()`.
- **`SettingsUpdate`** (`routes/settings.py:38`): remove `github_token: str | None = None`.
- **`get_settings` response** (`routes/settings.py:88-92`): remove `"github_token": ...` from `token_set`.
- **`update_settings` handler** (`routes/settings.py:102-114`): remove the entire `if "github_token" in update_data` block.
- **`update_settings` response** (`routes/settings.py:160-164`): remove `"github_token": ...` from `token_set`.
- **Import** (`routes/settings.py:13`): remove `from ..url_validator import validate_github_token`.
- **Endpoint** (`routes/settings.py:175-185`): remove `POST /api/v1/settings/check-github-token` entirely.

`token_set` in API responses will contain only `librariesio_api_key` and `ecosystems_api_key`.

### 2. Backend — URL validator (`url_validator.py`)

- **Enum** (`url_validator.py:74`): remove `TOKEN_INVALID = "token_invalid"` from `UrlValidationResult`.
- **Function** (`url_validator.py:331-339`): remove `validate_github_token()` entirely.
- **Function** (`url_validator.py:382-405`): remove `validate_url_with_retry()` entirely — it was a wrapper that only existed for TOKEN_INVALID retry logic.
- **Parameter `github_token`**: remove from all function signatures:
  - `ensure_connectivity()` (`url_validator.py:84`)
  - `_head_request()` (`url_validator.py:110`)
  - `_git_probe()` (`url_validator.py:124`)
  - `_check_vcs()` (`url_validator.py:301`)
  - `validate_url()` (`url_validator.py:347`)
- **Authorization injection**:
  - Bearer header in `ensure_connectivity()` (`url_validator.py:97-98`)
  - Bearer header in `_head_request()` (`url_validator.py:115-116`)
  - `oauth2:` URL rewriting in `_git_probe()` (`url_validator.py:129-130`)
- **TOKEN_INVALID logic**:
  - 401 check in `validate_url()` (`url_validator.py:360-362`)
  - Auto-clear + retry in removed `validate_url_with_retry()` (old `url_validator.py:393-402`)

### 3. Backend — Service layer

- **`validation_service.py`**: remove `github_token` parameter from `validate_url()`. Replace `validate_url_with_retry` import/call with `validate_url`.
- **`service.py`** (`service.py:56,126`): remove `github_token=app_settings.github_token` from `validate_url()` calls.
- **`sbom_enrichment.py`** (`sbom_enrichment.py:61,80,83`): remove `val_token = app_settings.github_token` and its usage. Replace `validate_url_with_retry` import/call with `validate_url`.

### 4. Frontend — API and types

- **`api/settings.ts:16-17`**: remove `checkGithubToken()` function.
- **`types/api.ts:19-23`**: remove `github_token: boolean` from `SettingsTokenSet`.
- **`types/api.ts:50`**: remove `github_token?: string | null` from `SettingsUpdate`.

### 5. Frontend — Store (`useSettingsStore.ts`)

- Remove `checkGithubToken` import from `api/settings`.
- Remove `githubTokenValidity` ref (line 24), `githubToken` ref (line 25).
- `hasAnyToken`: remove `tokenSet.value.github_token ||` (line 31).
- `save()`: remove the `if ('github_token' in partial)` block (lines 62-64).
- `clearToken()`: remove `'github_token'` from union type parameter; remove line 72 (`githubTokenValidity.value = null`).
- Remove `checkGithubToken()` method entirely (lines 75-78).
- Remove `githubToken`, `githubTokenValidity`, `checkGithubToken` from the return block.

### 6. Frontend — UI (`Settings.vue`)

Template:
- Remove the entire GitHub token card (`<div class="card">` for `settings.githubToken.title`, lines 117-145).
- No other card is affected.

Script:
- Remove `githubTokenValidity` from `storeToRefs` destructuring (line 347).
- Remove `const githubTokenInput = ref('')` (line 350).
- Remove `if ('github_token' in partial) githubTokenInput.value = ''` from `autoSave()` (line 376).
- Remove `onGithubTokenBlur()` function (lines 389-393).
- Remove `clearToken()` function (lines 407-413).
- Remove `onCheckGithubToken()` function (lines 415-422).

CSS: `.status-set`, `.status-not-set`, `.status-valid`, `.status-invalid`, `.validity-desc` — keep; used by other cards.

### 7. i18n

Remove GitHub-token-specific strings from `en.json` and `ru.json`:

- `settings.githubToken.*` — all 10 sub-keys (title, label, desc, genToken, genTokenHint, status, validity)
- `settings.clearToken`
- `settings.checkValidity`
- `settings.valid`
- `settings.invalid`
- `settings.tokenCheckComplete`
- `errorMessages.tokenClearFailed`
- `errorMessages.tokenCheckFailed`
- `errors.invalid_token`
- `errors.token_not_set`

Keep: `settings.set`, `settings.notSet`, `settings.clearKey`, `settings.tokenCleared` — shared with librariesio/ecosystems cards.

### 8. Tests

| File | What to change |
|------|---------------|
| `test_url_validator.py` | Remove imports of `TOKEN_INVALID`, `validate_github_token`, `validate_url_with_retry`. Remove all token-related tests (classes `TestValidateGithubToken`, `TestValidateUrlWithRetry`, individual token tests). Update non-token tests that reference removed parameters. |
| `test_vcs_check.py` | Remove `test_github_token_rewrites_url`, `test_non_github_url_no_token_injection`. |
| `test_api.py` | Remove `test_get_settings_masks_github_token`, `test_get_settings_shows_token_not_set`, `test_patch_settings_with_valid_token`, `test_patch_settings_with_invalid_token`, `test_patch_empty_string_does_not_clear_token`, `test_patch_null_clears_token`, `test_check_github_token_valid/invalid/not_set`. |
| `test_service_validation.py` | Remove assertions that check `github_token` parameter passing (lines 409, 434). |
| `test_sbom_integration.py` | Remove `validate_url_with_retry` patch references, replace with `validate_url`. |
| `Settings.test.ts` | Remove tests for GitHub token card: save on blur, clear token, validity display, check validity button. |

## Key Files Changed

**Backend:**
- `src/purl_resolver/settings_store.py` — remove `github_token` field
- `src/purl_resolver/url_validator.py` — remove TOKEN_INVALID, validate_github_token, validate_url_with_retry, token parameters/injection
- `src/purl_resolver/routes/settings.py` — remove token API handling and check endpoint
- `src/purl_resolver/validation_service.py` — remove token parameter
- `src/purl_resolver/service.py` — remove token passing
- `src/purl_resolver/sbom_enrichment.py` — remove token reading and passing

**Frontend:**
- `frontend/src/api/settings.ts` — remove checkGithubToken
- `frontend/src/types/api.ts` — remove github_token from SettingsTokenSet and SettingsUpdate
- `frontend/src/stores/useSettingsStore.ts` — remove token state and methods
- `frontend/src/views/Settings.vue` — remove GitHub token card

**i18n:**
- `frontend/src/i18n/locales/en.json`
- `frontend/src/i18n/locales/ru.json`

**Tests:**
- `tests/test_url_validator.py`
- `tests/test_vcs_check.py`
- `tests/test_api.py`
- `tests/test_service_validation.py`
- `tests/test_sbom_integration.py`
- `frontend/src/views/Settings.test.ts`
- `frontend/src/components/__tests__/` (any token-related tests if present)

## Invariants

- AppSettings must still load from old settings.json files without crashing (Pydantic `extra="ignore"`).
- All remaining URL validation must work identically without tokens.
- `token_set` in API responses must still include `librariesio_api_key` and `ecosystems_api_key`.
- libraries.io and ecosystems key UI must be unaffected by the removal.
