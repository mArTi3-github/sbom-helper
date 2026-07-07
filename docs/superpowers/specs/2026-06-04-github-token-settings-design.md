# GitHub API Token in Settings

**Date:** 2026-06-04
**Status:** Approved
**Scope:** url_validator.py only (no resolver changes)

## Problem

Current resolvers use unauthenticated `git ls-remote` and HTTP HEAD requests. GitHub rate limits anonymous requests to 60/hr (API) and ~1200/hr (git ls-remote). This is insufficient for batch processing of large SBOMs.

## Solution

Add a `github_token` field to the application settings, persisted in `data/settings.json`. The token is used for authenticated `git ls-remote` and HTTP requests in `url_validator.py`, increasing rate limits to 5000/hr (API) and unlimited (git operations).

## Design Decisions

### 1. ServiceTokens dataclass

Create a `ServiceTokens` dataclass to hold API tokens. This is extensible for future tokens (libraries.io, ecosyste.ms) without changing function signatures.

```python
@dataclass
class ServiceTokens:
    github_token: str | None = None
```

`AppSettings` gains a `service_tokens()` method that extracts tokens into this dataclass.

### 2. Token usage scope

Token is used **only** in `url_validator.py`:
- `_git_ls_remote()`: authenticated git URL (`https://oauth2:TOKEN@github.com/...`)
- `_head_request()`: `Authorization: Bearer TOKEN` header
- `_check_connectivity()`: authenticated connectivity probe

Future resolvers (libraries.io, ecosyste.ms) will use their own tokens through the same `ServiceTokens` mechanism.

### 3. Token validation on save

When `PATCH /api/v1/settings` receives a `github_token`:
1. Make a test request to `GET https://api.github.com/rate_limit` with the token
2. HTTP 200 → token is valid, save to settings
3. HTTP 401/403 → return error `invalid_token`, do not save

### 4. Token invalidation on use

If a token fails during URL validation:
1. `validate_url()` returns `UrlValidationResult.TOKEN_INVALID`
2. `service.py` deletes the token from settings
3. Retries the validation without the token
4. Logs the event

### 5. API response masking

`GET /api/v1/settings` returns `token_set: { github_token: true/false }` — never the actual token value. The token is only stored in `data/settings.json`.

### 6. UI behavior

- Password input field (`type="password"`) with placeholder `ghp_...`
- Badge showing "set" / "not set" status
- Mini-instruction with link to GitHub token creation page
- Empty field on save → token deleted
- Validation feedback (success/error messages)

## Files to Modify

| File | Change |
|------|--------|
| `src/purl_resolver/settings_store.py` | Add `ServiceTokens`, `github_token` to `AppSettings`, `service_tokens()` method |
| `src/purl_resolver/url_validator.py` | Add `github_token` parameter to `validate_url()`, `_git_ls_remote()`, `_head_request()`, `_check_connectivity()`. Add `TOKEN_INVALID` to `UrlValidationResult` |
| `src/purl_resolver/service.py` | Read token from settings, pass to `validate_url()`, handle `TOKEN_INVALID` |
| `src/purl_resolver/router.py` | Update `SettingsUpdate` model, add token validation in `update_settings()`, mask token in `get_settings()` response |
| `src/purl_resolver/templates/settings.html` | Add GitHub token section with input, badge, instructions |
| `tests/test_settings_store.py` | Tests for `github_token` field, `service_tokens()`, roundtrip |
| `tests/test_url_validator.py` | Tests for authenticated requests |

## API Changes

### GET /api/v1/settings

```json
{
  "validate_db_urls": false,
  "url_validation_timeout": 5,
  "token_set": {
    "github_token": false
  }
}
```

### PATCH /api/v1/settings

Request:
```json
{
  "github_token": "ghp_..."
}
```

Empty string or `null` → token deleted.
Invalid token → `400 { "error": "invalid_token", "message": "..." }`

## Authentication Mechanisms

- **git ls-remote:** `https://oauth2:TOKEN@github.com/owner/repo`
- **HTTP HEAD:** `Authorization: Bearer TOKEN` header

Both are standard GitHub authentication methods for Personal Access Tokens.

## Testing

- Unit tests for `ServiceTokens`, `AppSettings.github_token`, `service_tokens()`
- Unit tests for `_git_ls_remote()` and `_head_request()` with/without token
- Integration tests for settings API with token validation
- Token masking verification (token never appears in GET response)
