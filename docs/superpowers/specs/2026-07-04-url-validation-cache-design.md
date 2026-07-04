# URL Validation Cache Design

## Problem

URL validation (`validate_url()` → HTTP HEAD + multi-VCS probe) is invoked repeatedly for the same URL across different contexts:

1. **Local DB cache miss + re-validation**: every PURL cache entry has its URL re-validated independently based on `resolved_at` — the same URL may be checked N times if it's associated with N different PURLs.
2. **SBOM existing references**: same URL may appear in multiple components' `externalReferences`, triggering N independent validations.
3. **Fresh resolver results**: URL returned by a resolver for one PURL may be the same URL already validated for another PURL in the same batch.

There is no deduplication of validation work across these contexts.

## Solution

Introduce a `UrlValidationCache` that stores `url → validated_at` mappings using the `diskcache` library (SQLite-backed file cache). Before performing full validation, the cache is consulted; if the URL was validated within `revalidation_cooldown_hours`, it's considered valid without a network request.

## Modules

### 1. `UrlValidationCache` (`src/purl_resolver/url_validation_cache.py`)

```python
class UrlValidationCache:
    def __init__(self, cache_dir: str) -> None: ...
    def get(self, url: str, max_age_seconds: int) -> str | None: ...
    def put(self, url: str) -> None: ...
    def expire(self, max_age_seconds: int) -> None: ...
    def clear(self) -> None: ...
```

**Storage format**: DiskCache key-value store. Key = URL (string), Value = `time.time()` float (validated_at timestamp).

**`get(url, max_age_seconds)`**: returns `url` if cached and `current_time - validated_at <= max_age_seconds`, else `None`.

**`put(url)`**: stores `url → time.time()` in DiskCache (no DiskCache-native expire).

**`expire(max_age_seconds)`**: iterates all keys, deletes those where `validated_at < current_time - max_age_seconds`. Called by background task once per day using the current `revalidation_cooldown_hours` value.

**`clear()`**: deletes all entries. Called via Settings UI button.

### 2. `UrlValidationService` — updated (`src/purl_resolver/validation_service.py`)

```python
class UrlValidationService:
    def __init__(self, settings_store: SettingsStore, cache: UrlValidationCache) -> None: ...
    async def validate_url(self, url: str, timeout: int, github_token: str | None = None) -> UrlValidationOutput: ...
    def clear_cache(self) -> None: ...
```

**`validate_url()` logic**:
1. If `validate_db_urls` setting is enabled, consult cache: `cache.get(url, revalidation_cooldown_hours * 3600)`. On hit → return `VALID` immediately.
2. Otherwise, run full validation via `validate_url_with_retry()`.
3. On `VALID` result and `validate_db_urls` enabled, store in cache: `cache.put(url)`.

**`clear_cache()`**: delegates to `cache.clear()`.

### 3. `AppSettings` — new field (`src/purl_resolver/settings_store.py`)

```python
validate_sbom_refs: bool = False
```

Replaces the per-request `validate_existing_refs` flag from the SBOM form. When enabled, existing VCS/source-distribution references in SBOM components are validated before enrichment.

### 4. Removed logic

- **`PurlResolutionService._is_within_cooldown()`** — removed. The cache replaces resolver-based cooldown. `resolve_purl()` no longer checks cooldown; it delegates URL validation entirely to `UrlValidationService.validate_url()`.
- **`PurlResolutionService._validate_cached_url()`** — removed. `resolve_purl()` now calls `UrlValidationService.validate_url()` directly after cache lookup. On VALID + redirect → `storage.store()` to update `repository_url`. On INVALID → `storage.delete_purls()` + fall through to resolvers.
- **`validate_existing_refs` form parameter** — removed from `POST /api/v1/resolve/sbom`. Pipeline reads `validate_sbom_refs` from settings store.

## API Changes

### `POST /api/v1/resolve/sbom`

Remove `validate_existing_refs: bool = Form(False)`. Pipeline uses `settings_store.load().validate_sbom_refs`.

### `POST /api/v1/settings/clear-validation-cache` (new)

Calls `request.app.state.validation_service.clear_cache()`. Returns 200 OK.

### `PATCH /api/v1/settings` and `GET /api/v1/settings`

Add `validate_sbom_refs: bool` to request/response schema.

## UI Changes

### `Settings.vue` — "URL Validation" card

| Element | Type | Change |
|---|---|---|
| Validate URLs from local database | toggle | unchanged |
| Validate pre-existing URLs from SBOM | toggle | **new** — moved from SbomUpdater |
| Validation timeout | number | unchanged |
| Re-validation cooldown (hours) | number | unchanged (now also cache TTL) |
| Info text: "URLs returned by resolvers are always validated before being returned" | text | **new** |
| Clear validation cache | button | **new** |

### `SbomUpdater.vue`

Remove checkbox "Проверять существующие VCS-ссылки в SBOM" (lines 13-16).

## Background Task

In `main.py` lifespan, an asyncio task runs once per day:

```python
async def _expire_url_cache(cache: UrlValidationCache, settings_store: SettingsStore):
    while True:
        await asyncio.sleep(86400)  # 24h
        max_age = settings_store.load().revalidation_cooldown_hours * 3600
        cache.expire(max_age)
```

## Docker Volume

Add to `docker-compose.yml`:

```yaml
volumes:
  - ./data/url_cache/:/app/data/url_cache/
```

## Example Flow

### Cache hit (URL validated < revalidation_cooldown_hours ago)

1. `resolve_purl("pkg:pypi/requests@2.31.0")` → cache miss in local DB
2. purl2repo returns `https://github.com/psf/requests`
3. `UrlValidationService.validate_url("https://github.com/psf/requests")` → cache miss → full validation → VALID → `cache.put("https://github.com/psf/requests")`
4. Result stored in DB

### Cache hit for same URL, different PURL

1. `resolve_purl("pkg:pypi/requests@2.28.0")` → cache miss in local DB
2. purl2repo returns `https://github.com/psf/requests`
3. `UrlValidationService.validate_url("https://github.com/psf/requests")` → cache hit → return VALID immediately

### SBOM enrichment with cached URL

1. SBOM component has `externalReferences: [{type: "vcs", url: "https://github.com/psf/requests"}]`
2. `validate_existing_refs = true`
3. `cache.get("https://github.com/psf/requests", max_age)` → hit → VALID, component unchanged

## Avoiding `resolved_at` Update on Simple Validation

When `_validate_cached_url()` confirms a URL is valid via cache hit or via actual validation, it no longer calls `storage.store()` to update `resolved_at`. The only case `storage.store()` is called is when:
- The final URL differs from the stored URL (redirect detected)

## Key Principles

- Cache is **append-only**: only successfully validated URLs are stored.
- Cache is **permissive**: expired entries are not deleted on `get()` — only ignored. Physical cleanup via `expire()`.
- `revalidation_cooldown_hours` is the **single source of truth** for both cache TTL and cleanup threshold.
- Setting `revalidation_cooldown_hours = 0` disables cache entirely — every validation hits the network.