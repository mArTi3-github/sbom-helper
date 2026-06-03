# Settings Page with URL Validation Toggle

## Overview

Add a Settings page to the web UI with a toggle for validating repository URLs from the local database before using them. When enabled, URLs found in the local DB are verified (HTTP HEAD + git ls-remote) before being returned. Invalid URLs are deleted from the DB, and resolution continues through the resolver chain.

## Requirements

- Settings page accessible at `/settings` with nav-bar link on all pages
- Toggle: enable/disable URL validation from local DB (default: off)
- Timeout input: seconds for validation checks (default: 5, range: 1–60)
- Settings persisted in JSON file on disk (`data/settings.json`)
- API endpoints: `GET /api/v1/settings`, `PATCH /api/v1/settings`
- Validation applies everywhere: single PURL, batch, SBOM enrichment
- Validation cooldown: skip if `resolved_at` is today (same calendar date)
- Must distinguish "repo not found" from "internet connectivity issues"
- Never crash on validation errors — always return a result

## Architecture

**Approach: Validation in Service Layer**

Validation logic lives in `service.py::resolve_purl()`, after `storage.lookup()` and before returning the cached result. A new `url_validator.py` module handles the actual checks. A new `settings_store.py` module manages the JSON config file.

```
┌─────────────┐    ┌────────────────┐    ┌─────────────────┐
│  Web UI     │───▶│  Router        │───▶│  Service Layer   │
│  /settings  │    │  GET/PATCH     │    │  resolve_purl()  │
└─────────────┘    │  /api/v1/      │    │                  │
                   │  settings      │    │  lookup → validate│
                   └────────────────┘    │  → resolver chain │
                                         └────────┬─────────┘
                                                  │
                              ┌────────────────────┼──────────────────┐
                              ▼                    ▼                  ▼
                    ┌──────────────┐    ┌──────────────────┐  ┌────────────┐
                    │ Storage      │    │ URL Validator     │  │ Resolvers  │
                    │ (PostgresCache)  │ HEAD + git ls-remote│  │ (purl2repo)│
                    └──────────────┘    └──────────────────┘  └────────────┘
                              ▲
                              │
                    ┌──────────────────┐
                    │ Settings Store    │
                    │ (JSON file)       │
                    └──────────────────┘
```

## Components

### 1. SettingsStore (`src/purl_resolver/settings_store.py`)

Pydantic model for app settings:
```python
class AppSettings(BaseModel):
    validate_db_urls: bool = False
    url_validation_timeout: int = 5  # seconds, 1–60
```

Class with methods:
- `load() -> AppSettings` — reads from JSON file, creates with defaults if missing
- `save(settings: AppSettings)` — writes to JSON file
- Path from `SETTINGS_FILE` env var (default: `./data/settings.json`)
- On corrupt JSON: log warning, return defaults

### 2. URL Validator (`src/purl_resolver/url_validator.py`)

```python
class UrlValidationResult(Enum):
    VALID = "valid"
    INVALID = "invalid"
    NETWORK_ERROR = "network_error"
    RATE_LIMITED = "rate_limited"

async def validate_url(url: str, timeout: int) -> UrlValidationResult
```

**Algorithm:**
1. HEAD `https://github.com` with 2-second timeout (connectivity probe)
2. If GitHub unreachable → return `NETWORK_ERROR`
3. If GitHub returns 429 or 403 with `X-RateLimit-Remaining: 0` → return `RATE_LIMITED`
4. HEAD `repository_url` with configured timeout:
   - 200/301/302 → proceed to git ls-remote
   - 404/405 → return `INVALID`
   - 403 **without** rate limit headers → return `INVALID` (private/not accessible)
   - 429 or 403 with `X-RateLimit-Remaining: 0` → return `RATE_LIMITED`
   - ConnectionError/Timeout/DNS error → return `INVALID` (GitHub was reachable)
5. `git ls-remote --exit-code <url>` with configured timeout:
   - Exit 0 → return `VALID`
   - "repository not found" / "does not exist" → return `INVALID`
   - Timeout/connection error → return `INVALID` (GitHub was reachable)

**Rate limit detection:** Check for HTTP 429 status, or HTTP 403 with response header `X-RateLimit-Remaining: 0`. Both indicate the service is temporarily rejecting requests due to too many calls — not that the URL is invalid.

**Error handling:** Never raises exceptions. If aiohttp or git is unavailable, logs warning and returns `NETWORK_ERROR`.

**Rate limit mitigation:**
- Global in-memory counter tracks consecutive `RATE_LIMITED` results across all validations
- If counter exceeds a threshold (default: 5), skip all validation for 60 seconds (cooldown period)
- Counter resets on any non-RATE_LIMITED result or after cooldown expires
- Log a warning when entering/exiting cooldown

### 3. Service Layer Integration (`src/purl_resolver/service.py`)

In `resolve_purl()`, after `storage.lookup()`:
1. If `settings_store` is None or `validate_db_urls` is False → skip (current behavior)
2. If `resolved_at` date equals today → skip validation
3. Call `validate_url(cached.repository_url, timeout)`
4. `VALID` → call `storage.store(cached)` (ON CONFLICT updates `resolved_at` to NOW()), return cached
5. `INVALID` → `storage.delete_purls([purl_key])`, set `cached = None`, fall through to resolver chain
6. `NETWORK_ERROR` → return cached as-is (don't update `resolved_at`)
7. `RATE_LIMITED` → return cached as-is (don't update `resolved_at`, don't delete)

`settings_store` is an optional parameter (backward compatible).

### 4. API Endpoints (`src/purl_resolver/router.py`)

- `GET /api/v1/settings` → returns `AppSettings` as JSON
- `PATCH /api/v1/settings` → partial update, validates input, returns updated settings

### 5. Web UI (`src/purl_resolver/templates/settings.html`)

- Route: `GET /settings`
- Nav-bar: add "Settings" link to all four templates
- Form: toggle for `validate_db_urls`, number input for `url_validation_timeout`
- JS: fetch current settings on load, save on button click, show confirmation

## Data Flow

### Single PURL Resolution (with validation enabled)

```
POST /api/v1/resolve { "purl": "pkg:pypi/requests" }
  → validate(purl) → normalize → purl_key
  → storage.lookup(purl_key) → found (resolved_at: 3 days ago)
  → validate_url("https://github.com/psf/requests", 5)
    → HEAD github.com → OK
    → HEAD github.com/psf/requests → 200
    → git ls-remote https://github.com/psf/requests → exit 0
    → VALID
  → update resolved_at → NOW()
  → return cached result
```

### Invalid URL Flow

```
POST /api/v1/resolve { "purl": "pkg:pypi/old-package" }
  → storage.lookup(purl_key) → found (resolved_at: 5 days ago)
  → validate_url("https://github.com/deleted/repo", 5)
    → HEAD github.com → OK
    → HEAD github.com/deleted/repo → 404
    → INVALID
  → storage.delete_purls([purl_key])
  → fall through to resolver chain
  → Purl2RepoResolver.resolve(purl) → new URL found
  → storage.store(new_result)
  → return new result
```

### Network Error Flow

```
POST /api/v1/resolve { "purl": "pkg:pypi/requests" }
  → storage.lookup(purl_key) → found
  → validate_url("https://github.com/psf/requests", 5)
    → HEAD github.com → ConnectionError (no internet)
    → NETWORK_ERROR
  → return cached as-is
```

### Rate Limit Flow

```
POST /api/v1/resolve { "purl": "pkg:pypi/requests" }
  → storage.lookup(purl_key) → found
  → validate_url("https://github.com/psf/requests", 5)
    → HEAD github.com → 403 with X-RateLimit-Remaining: 0
    → RATE_LIMITED
  → return cached as-is
  → global counter incremented (consecutive rate limits: 3)
```

After 5 consecutive RATE_LIMITED results → enter 60-second cooldown:
```
POST /api/v1/resolve { "purl": "pkg:pypi/flask" }
  → storage.lookup(purl_key) → found
  → validate_url skipped (cooldown active, 42s remaining)
  → return cached as-is
```

## Files to Create/Modify

| File | Action |
|------|--------|
| `src/purl_resolver/settings_store.py` | **Create** — SettingsStore class |
| `src/purl_resolver/url_validator.py` | **Create** — validate_url function |
| `src/purl_resolver/templates/settings.html` | **Create** — Settings page |
| `src/purl_resolver/service.py` | **Modify** — add validation after lookup |
| `src/purl_resolver/router.py` | **Modify** — add /settings route + API endpoints |
| `src/purl_resolver/templates/index.html` | **Modify** — add Settings nav link |
| `src/purl_resolver/templates/sbom.html` | **Modify** — add Settings nav link |
| `src/purl_resolver/templates/db-admin.html` | **Modify** — add Settings nav link |
| `tests/test_url_validator.py` | **Create** — URL validator tests |
| `tests/test_settings_store.py` | **Create** — Settings store tests |
| `tests/test_service_validation.py` | **Create** — Service layer validation tests |

## Error Handling

- `validate_url()` never raises exceptions — always returns `UrlValidationResult`
- If `git ls-remote` is not installed → log warning, return `NETWORK_ERROR`
- If `aiohttp` is not installed → log warning, skip HEAD check, proceed to git ls-remote only
- Settings file not found → create with defaults
- Settings file corrupt → log warning, use defaults

## Tests

### `tests/test_url_validator.py`
- Mock HEAD github.com: 200, HEAD target: 200, git ls-remote: exit 0 → VALID
- Mock HEAD github.com: 200, HEAD target: 404 → INVALID
- Mock HEAD github.com: 200, HEAD target: 403 (no rate limit headers) → INVALID
- Mock HEAD github.com: 200, HEAD target: 403 with X-RateLimit-Remaining: 0 → RATE_LIMITED
- Mock HEAD github.com: 200, HEAD target: 429 → RATE_LIMITED
- Mock HEAD github.com: 200, HEAD target: ConnectionError → INVALID
- Mock HEAD github.com: ConnectionError → NETWORK_ERROR
- Mock git ls-remote: "repository not found" → INVALID
- Mock git ls-remote: timeout + GitHub reachable → INVALID
- resolved_at is today → skip validation (return None or sentinel)
- 5 consecutive RATE_LIMITED → cooldown active, skip validation

### `tests/test_settings_store.py`
- File does not exist → creates with defaults
- File exists with valid JSON → loads correctly
- File is corrupt JSON → returns defaults + logs warning
- save/load roundtrip works

### `tests/test_service_validation.py`
- lookup returns result + validate_db_urls=True + resolved_at not today → validation runs
- VALID → store called (updates resolved_at), returns cached
- INVALID → delete called, falls through to resolver chain
- NETWORK_ERROR → returns cached as-is
- RATE_LIMITED → returns cached as-is
- validate_db_urls=False → no validation
- resolved_at is today → no validation
- settings_store is None → no validation (backward compatible)

## Invariants

- `validate_url()` never raises exceptions — always returns `UrlValidationResult`
- Settings file is created with defaults if missing or corrupt
- Validation is skipped if `resolved_at` is today (same calendar date)
- Network errors never cause URL deletion
- Rate limits never cause URL deletion — return cached as-is
- After 5 consecutive rate limits, skip all validation for 60 seconds
- `settings_store` parameter is optional — backward compatible
- Batch and SBOM enrichment inherit validation automatically (they call `resolve_purl()`)

## Configuration

| Key | Source | Default | Description |
|-----|--------|---------|-------------|
| `SETTINGS_FILE` | env var | `./data/settings.json` | Path to settings JSON file |
| `validate_db_urls` | JSON file | `false` | Enable URL validation |
| `url_validation_timeout` | JSON file | `5` | Timeout in seconds (1–60) |
