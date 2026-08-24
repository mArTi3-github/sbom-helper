# PURL Resolution

## Description

Core capability of the system. Accepts one or more Package URL (PURL) strings and returns the corresponding source code repository URLs with warnings and resolver attribution. Uses a two-tier strategy: first checks PostgreSQL for a cached result, and on cache miss delegates resolution to the resolver chain (purl2repo → deps.dev → ecosyste.ms → libraries.io → apk → llm), storing successful results for future lookups. Resolver composition is settings-driven — each resolver after purl2repo can be toggled; the LLM resolver, when enabled, is always last.

## Key Files

- `src/purl_resolver/router.py` — API endpoint handlers that call the Service Layer
- `src/purl_resolver/service.py` — `PurlResolutionService` class: Orchestration → validation → normalization → storage lookup → URL validation → resolver → storage store; `_resolve_concurrent()` core (semaphore + dedup by normalized key) shared by `resolve_many()` (batch endpoint, one row per input PURL) and `resolve_batch()` (SBOM flow, successful results only); `store_preexisting_references()` for SBOM pre-existing refs
- `src/purl_resolver/sbom_enrichment.py` — `SbomEnrichmentPipeline` orchestrating the full SBOM enrichment workflow: parse → collect → resolve → enrich → remove → report; used by async jobs (`routes/jobs.py`)
- `src/purl_resolver/purl_utils/` — PURL validation, normalization, and `safe_normalize()` convenience function
- `src/purl_resolver/resolver/` — Resolver abstraction (ABC, Resolution, exceptions), purl2repo wrapper, deps.dev wrapper, ecosyste.ms wrapper, libraries.io wrapper, apk wrapper, LLM wrapper, and factory module
- `src/purl_resolver/resolver/factory.py` — `build_resolvers(settings, app_settings) → list[Resolver]`: centralizes resolver initialization; always creates Purl2RepoResolver, then conditionally adds DepsdevResolver, EcosystemsResolver, LibrariesIoResolver, ApkResolver, and LlmResolver (always last) based on settings
- `src/purl_resolver/resolver/depsdev.py` — `DepsdevResolver`: fallback resolver using the deps.dev v3 API; enabled by default (settings-controlled), no API key required; supports: maven, npm, golang, pypi, nuget, cargo, gem; returns the package's SOURCE_REPO link normalized to an HTTPS URL
- `src/purl_resolver/resolver/ecosystems.py` — `EcosystemsResolver`: fallback resolver using ecosyste.ms Packages API, enabled by default (settings-controlled), no API key required (optional for higher rate limits)
- `src/purl_resolver/resolver/librariesio.py` — `LibrariesIoResolver`: fallback resolver using libraries.io API, optional (settings-controlled), supports: cargo, composer, conda, cpan, cran, gem, generic, golang, hackage, hex, maven, npm, nuget, pub, pypi, swift
- `src/purl_resolver/resolver/apk.py` — `ApkResolver`: fallback resolver for Alpine Linux APK packages (`pkg:apk/...`), returns constant URL `https://github.com/alpinelinux/aports`; purely local (no network calls), enabled by default via `apk_resolver_enabled` setting
- `src/purl_resolver/resolver/llm.py` — `LlmResolver`: last resolver in the chain; asks an OpenAI-compatible LLM (with web search) for the repository URL, validates the JSON response schema and verifies the URL via HTTP HEAD (failed checks are fed back for the next attempt); optional (settings-controlled), always placed last
- `src/purl_resolver/schemas.py` — Request and response data models
- `src/purl_resolver/storage/` — Storage Layer (interface, postgres, inmemory implementations)
- `src/purl_resolver/sbom/parser.py` — CycloneDX SBOM validation and parsing
- `src/purl_resolver/sbom/collector.py` — Recursive component collection with path tracking, `needs_enrichment` and `has_subcomponents` detection
- `src/purl_resolver/sbom/enricher.py` — Inserts VCS external references into SBOM components
- `src/purl_resolver/sbom/remover.py` — Removes unresolved components without subcomponents from SBOM
- `src/purl_resolver/sbom/reporter.py` — Builds enrichment report with found/not_found/removed counts
- `src/purl_resolver/settings_store.py` — JSON-based application settings persistence (validate_db_urls, url_validation_timeout, revalidation_cooldown_hours, resolver toggles, API keys, batch_semaphore_limit, batch_max_items, job_ttl_hours, connectivity settings)
- `src/purl_resolver/url_validator.py` — URL validation via HTTP HEAD + multi-VCS probe (`_check_vcs`: git → svn → hg → fossil) with rate limit mitigation; returns `UrlValidationOutput` dataclass capturing the final URL after 3xx redirects
- `src/purl_resolver/url_validation_cache.py` — `UrlValidationCache`: diskcache-based URL validation result cache with TTL expiry; used by `UrlValidationService`
- `src/purl_resolver/validation_service.py` — `UrlValidationService`: wraps `validate_url()` with UrlValidationCache; consumed by `PurlResolutionService` and accessed by `SbomEnrichmentPipeline` through `PurlResolutionService.validation_service` property
- `src/purl_resolver/db_admin_service.py` — `DbAdminService`: encapsulates database admin operations (list, edit, import/export CSV) between API routes and Storage Layer
- `src/purl_resolver/job_manager.py` — `JobManager`: async background job processing for SBOM enrichment; manages job queue, worker tasks, cleanup
- `src/purl_resolver/job_repository.py` — `JobRepository`: PostgreSQL persistence for job records (`JobRecord` dataclass)
- `src/purl_resolver/routes/jobs.py` — Async SBOM enrichment job endpoints (`POST /api/v1/jobs/sbom-enrich`, `GET /api/v1/jobs`, etc.)
- `tests/test_api.py` — Integration tests for resolution workflow
- `tests/test_storage.py` — Unit tests for service and in-memory cache

## Core Types

```python
class BatchResolveRequest(BaseModel):
    purls: list[str]  # one PURL per list item

class BatchResolveItem(BaseModel):  # one row per input PURL, in input order
    purl: str            # original input string (with version)
    repository_url: str | None = None
    warnings: list[str] = []
    resolver: str = ""
    found_by: str = ""
    resolved_at: str = ""
    error: str | None = None  # invalid_purl / upstream_error for this row

class BatchResolveResponse(BaseModel):
    results: list[BatchResolveItem]

class ResolveResponse(BaseModel):  # stored canonical form, purl is normalized
    purl: str  # normalized form: scheme:type/namespace/name
    repository_url: str | None = None
    warnings: list[str] = []
    resolver: str = ""
    found_by: str = ""
    resolved_at: str = ""

class PurlComponents:
    scheme: str       # always "pkg"
    type: str
    namespace: str | None
    name: str
    version: str | None
    qualifiers: dict[str, str] | None
    subpath: str | None

class UrlValidationResult(Enum):
    VALID = "valid"
    INVALID = "invalid"
    NETWORK_ERROR = "network_error"
    RATE_LIMITED = "rate_limited"

@dataclass
class UrlValidationOutput:
    result: UrlValidationResult
    final_url: str | None = None
    # final_url is str(resp.url) from httpx with follow_redirects=True
    # final_url is None only when HEAD request did not execute
    # (scheme error, rate-limit cooldown, connectivity failure, HEAD exception)
```

## Flow

```
Client                    API Layer (router)         Service Layer             purl_utils        Storage          Resolver
  |                          |                          |                        |                |                |
  | POST /api/v1/resolve/batch |                        |                        |                |                |
  | {"purls": ["pkg:...", ...]} |                       |                        |                |                |
  |------------------------->|                          |                        |                |                |
  |                          | service.resolve_many()   |                        |                |                |
  |                          |------------------------->|                        |                |                |
  |                          |   per unique PURL:      |                        |                |                |
  |                          |   service.resolve_purl() |                        |                |                |
  |                          |   validate(purl_str)     |                        |                |                |
  |                          |                          |----------------------->|                |                |
  |                          |                          | PurlComponents         |                |                |
  |                          |                          |<-----------------------|                |                |
  |                          |                          |                        |                |                |
  |                          |                          | (если ошибка)          |                |                |
  |                          |                          | HTTP 400               |                |                |
  |                          |                          |                        |                |                |
  |                          |                          | normalize(components)  |                |                |
  |                          |                          |----------------------->|                |                |
  |                          |                          | purl_key               |                |                |
  |                          |                          |<-----------------------|                |                |
  |                          |                          |                        |                |                |
  |                          |                          | storage.lookup(purl_key)|                |                |
  |                          |                          |--------------------------------------->|                |
  |                          |                          |                        |                |                |
  |                          |                          | (если найдено)         |                |                |
  |                          |                          | ResolveResponse        |                |                |
  |                          |                          |<---------------------------------------|                |
  |                          |                          |                        |                |                |
  |                          |                          | [если validate_db_urls |                |                |
  |                          |                          |  и resolved_at != сегодня]             |                |                |
   |                          |                          | validate_url(url, timeout)   |                |                |
    |                          |                          | ------+               |                |                |
    |                          |                          |        | HEAD + git   |                |                |
    |                          |                          | <------+               |                |                |
    |                          |                          |                        |                |                |
    |                          |                          | VALID → store(cached)  |                |                |
    |                          |                          |  (при отличии output.  |                |                |
    |                          |                          |   final_url URL в кеше |                |                |
    |                          |                          |   обновляется)         |                |                |
    |                          |                          | INVALID → delete, fall |                |                |
    |                          |                          | NETWORK_ERROR → return |                |                |
   |                          |                          |                        |                |                |
   |                          |                          | (если не найдено или  |                |                |
   |                          |                          |  cache deleted)        |                |                |
   |                          |                          | resolve(original_purl) |                |                |
   |                          |                          |------------------------------------------------------>|
   |                          |                          |                        |                |                |
   |                          |                          | ResolutionResult       |                |                |
   |                          |                          |<------------------------------------------------------|
   |                          |                          |                        |                |                |
   |                          |                          | (если success)         |                |                |
   |                          |                          | [если validate_db_urls  |                |                |
   |                          |                          |  включена]              |                |                |
    |                          |                          | validate_url(url, timeout)   |                |                |
    |                          |                          | ------+                |                |                |
    |                          |                          |        | HEAD + git    |                |                |
    |                          |                          | <------+                |                |                |
    |                          |                          |                        |                |                |
    |                          |                          | VALID → store + return |                |                |
   |                          |                          |  (используется output. |                |                |
   |                          |                          |   final_url для repo_url)               |                |                |
   |                          |                          | INVALID → continue to  |                |                |
   |                          |                          |           next resolver|                |                |
   |                          |                          | NETWORK_ERROR → store  |                |                |
   |                          |                          |           + return     |                |                |
   |                          |                          |                        |                |                |
   |                          |                          | [если validate_db_urls |                |                |
   |                          |                          |  выключена]            |                |                |
   |                          |                          | storage.store(result)  |                |                |
   |                          |                          |--------------------------------------->|                |
  |                          |                          |                        |                |                |
  |                          | 200 {results: [...]}     |                        |                |                |
  |<-------------------------|--------------------------|                        |                |                |
```

## URL Validator

### URL Validator (`url_validator.py`)
- Validates repository URLs via HTTP HEAD + multi-VCS probe to verify the URL exists and is reachable
- `validate_url(url, timeout) → UrlValidationOutput` — performs HEAD (with `follow_redirects=True`), captures the final URL after all 3xx redirects via `str(resp.url)`, then runs `_check_vcs()` against the final URL; returns `UrlValidationOutput(result, final_url)`
- `ensure_connectivity(url=None, timeout=None) → bool` — connectivity probe against configurable URL (default `https://github.com`); raises `ConnectionError` on failure
- `_check_vcs(url, timeout) → bool | None` — unified multi-VCS probe; runs git → svn → hg → fossil sequentially with early-exit on first success; aggregation: `True` if any probe is `True`, else `False` if any is `False`, else `None`; called with the resolved final URL by `validate_url()`
- `_git_probe(url, timeout) → bool | None` — internal helper: `git ls-remote --exit-code <url>`
- `_svn_probe(url, timeout) → bool | None` — internal helper: `svn ls <url>`; exit 0 → True, exit ≠0 → False
- `_hg_probe(url, timeout) → bool | None` — internal helper: `hg identify <url>`; exit 0 → True, exit ≠0 → False
- `_fossil_probe(url, timeout) → bool | None` — combined probe: tries the authoritative /xfer protocol probe first (`_fossil_probe_xfer`), falls back to HTML footer regex (`_fossil_probe_footer`) when the xfer probe is uncertain (None)
- `_fossil_probe_xfer(url, timeout) → bool | None` — internal helper: minimal POST to `<url>/xfer` with `Content-Type: application/x-fossil-debug`; checks response Content-Type for `application/x-fossil` / `application/x-fossil-debug` → True; 401/403 → None (uncertain — auth required); other non-fossil response → False; transport error → None
- `_fossil_probe_footer(url, timeout) → bool | None` — internal helper (fallback): HTTP GET with `follow_redirects=True`; status 200 + footer regex match → True; status 200 without footer → False; non-200 → False; transport error → None
- `UrlValidationResult` enum — `VALID`, `INVALID`, `NETWORK_ERROR`, `RATE_LIMITED`
- `UrlValidationOutput` dataclass — `result: UrlValidationResult`, `final_url: str | None = None`; `final_url` is `str(resp.url)` after redirects, `None` when HEAD did not execute (scheme error, cooldown, connectivity failure, HEAD exception)

## UrlValidationService

### Service Wrapper (`validation_service.py`)
- `UrlValidationService` wraps `validate_url()` with UrlValidationCache
- `UrlValidationService.__init__(settings_store: SettingsStore, cache: UrlValidationCache)` — receives `SettingsStore` for cooldown/retry config and `UrlValidationCache` for caching validation results
- `UrlValidationService.validate_url(url, timeout) → UrlValidationOutput` — checks cache first (within cooldown window), then delegates to `validate_url()`; caches VALID results
- `UrlValidationService.clear_cache() → None` — clears the entire validation cache
- Consumed by `PurlResolutionService` as an optional dependency. `SbomEnrichmentPipeline` accesses `validation_service` through `PurlResolutionService.validation_service` property.
- Decouples URL validation setup from resolution orchestration; single point for validation configuration changes

## Invariants

- `POST /api/v1/resolve/batch` always returns HTTP 200 with one result row per input PURL, in input order
- Every valid PURL row: `repository_url: null` if unresolved, `error: null`
- Invalid PURL format is caught at the application level (purl_utils) before any resolver or storage call — the row carries `error: "invalid_purl"` instead of failing the whole request
- Unsupported ecosystems return a row with `repository_url: null` and a warning (purl2repo returns `Resolution(None)`, resolver chain continues)
- Upstream errors (registry timeout, network failure) produce a row with `error: "upstream_error"`
- More than `batch_max_items` PURLs in one request → HTTP 400 `batch_too_large`
- Network connectivity probe failure → HTTP 503 `network_unavailable`
- The response format is canonical — it does not expose purl2repo's internal structure
- Empty purl strings are rejected at the Pydantic validation level (HTTP 422)
- **Normalized cache keys**: storage uses `scheme:type/namespace/name` form — version/qualifiers/subpath are stripped
- **Resolver receives original PURL**: the full string (with version, qualifiers, subpath) is passed unmodified to resolvers
- **DB cache hit**: if a result is found in PostgreSQL, the resolver is NOT called; when `validate_db_urls` is enabled, the cached URL is re-validated unless it is still within the validation cooldown window (`revalidation_cooldown_hours`)
- **Only successful results are stored**: `repository_url = null` results are never persisted
- **Graceful degradation**: if PostgreSQL is unavailable, the resolver still works (without caching)
- **Store is best-effort**: a failure to store does not break the response to the client
- **URL validation is optional**: controlled by `validate_db_urls` setting (default: off). When enabled, validation applies to both cached entries and freshly resolved URLs. For cached entries, cooldown (`revalidation_cooldown_hours`) skips re-validation; for fresh entries, validation runs synchronously before storing/returning.
- **Fresh URL validation skips invalid results**: when `validate_db_urls=true`, a freshly resolved URL returning `INVALID` via `validate_url()` causes the resolver chain to continue to the next resolver. The invalid result is neither stored nor returned. `NETWORK_ERROR` and `RATE_LIMITED` results keep the current resolver's result (store + return) to avoid discarding potentially valid URLs due to transient errors.
- **Validation cooldown applies uniformly**: the `revalidation_cooldown_hours` window is enforced per URL via the URL validation cache (diskcache) for all cached entries, regardless of the resolver that produced them
- **Cooldown disabled at zero**: Setting `revalidation_cooldown_hours=0` disables cooldown entirely — every cached entry triggers validation when `validate_db_urls=true`
- **SBOM existing-ref validation**: Optional checkbox `validate_existing_refs` in SBOM Updater validates existing VCS references via HEAD + multi-VCS probe (`_check_vcs`); `INVALID` results mark the component for re-resolution (`needs_enrichment=True`)
- **Connection errors preserve cache**: network errors during validation return `NETWORK_ERROR`, preserving the cached URL
- **Validation never crashes**: `validate_url()` always returns a `UrlValidationOutput`, never raises exceptions
- **Non-HTTP/HTTPS URLs skip redirect resolution**: URLs are validated by syntax (non-empty hostname) and SSRF guard (non-private IP) before VCS probes. HTTP/HTTPS URLs additionally undergo HEAD redirect resolution. Non-HTTP/HTTPS URLs skip redirect resolution and go directly to VCS probes.
- **revalidation_cooldown_hours bounds**: validated server-side with `ge=0, le=720` in both `AppSettings` and `SettingsUpdate`
- **Resolver field tracks origin**: every stored record has a `resolver` field indicating how it was added — `"purl2repo"`, `"depsdev"`, `"ecosyste.ms"`, `"libraries.io"`, `"apk"`, or `"llm"` when the corresponding resolver found the result, `"import-sbom"` for SBOM enrichment, `"import-csv"` for CSV import, `"import-manual"` for manual DB admin creation
- **Four-column table**: `resolved_purls` stores only `purl`, `repository_url`, `resolver`, `resolved_at` — all other fields from earlier schema versions have been removed
- **Warnings are runtime-only**: `warnings` is retained in `Resolution` dataclass, `ResolveResponse` model, and API response but is never persisted to the database, CSV export, or in-memory storage
- **Index on resolver**: `idx_resolved_purls_resolver` is created on startup in `create_pool()` to accelerate `SELECT DISTINCT resolver` queries for the dynamic resolver filter
- **URL redirects are resolved on validation**: `validate_url()` returns `UrlValidationOutput` containing the final URL after all 3xx redirects; `final_url` is `str(resp.url)` from httpx with `follow_redirects=True`
- **VCS probe uses the resolved final URL**: `_check_vcs()` receives the final redirect target, not the original URL
- **Cache entries updated with final URL on VALID**: `_validate_cached_url()` updates `cached.repository_url` when `final_url` differs from the stored URL on `VALID` result only
- **Fresh resolver results use final URL**: `resolve_purl()` stores and returns the resolved final URL for any non-INVALID validation result (including `NETWORK_ERROR`/`RATE_LIMITED`)
- **SBOM refs updated on any non-INVALID result**: `sbom_enrichment.py` updates `ref["url"]` with `final_url` when the ref redirected, regardless of whether validation result was `VALID`, `NETWORK_ERROR`, or `RATE_LIMITED`
- **SBOM enrichment uses resolver="import-sbom"**: both `PurlResolutionService.resolve_batch()` and `PurlResolutionService.store_preexisting_references()` in the SBOM flow store records with `resolver: "import-sbom"`
- **SBOM deduplication validates each PURL explicitly**: the deduplication loop calls `validate()` then `normalize()` on every component PURL; unversioned valid PURLs (e.g. `pkg:pypi/ptaf-task-manager`) are correctly normalized and added to the resolution queue — only truly invalid PURLs are counted as skipped
- **CSV import uses resolver="import-csv"**: when the `resolver` column is absent from the imported CSV, the value `"import-csv"` is used as default
- **SBOM enrichment enriches before removing**: `enrich_sbom()` is called before `remove_unresolved_components()` to avoid stale component paths after in-place removal
- **Removed components excluded from not_found**: components with `status: "removed"` do not appear as `status: "not_found"` in the report
- **Multi-VCS validation**: `_check_vcs()` probes git (via `git ls-remote --exit-code`), svn (via `svn ls`), hg (via `hg identify`), fossil (via HTTP GET + footer regex) sequentially with early-exit on first success
- **VCS aggregation rule**: if any probe returns `True` → result `True`; else if any probe returns `False` → result `False`; else (all probes uncertain) → result `None`
- **Docker provides VCS tools**: `git`, `subversion`, `mercurial` are installed in both `dev` and `prod` stages of the Dockerfile; fossil uses HTTP (httpx) and requires no binary
- **VCS subprocess timeouts are non-fatal**: `asyncio.TimeoutError` from any subprocess call is treated as `None` (uncertain) and logged as a warning; never raised to the caller
- **UrlValidationService is optional**: `PurlResolutionService` accepts an optional `validation_service: UrlValidationService | None` parameter; when `None`, callers fall back to direct `validate_url()` calls. `SbomEnrichmentPipeline` accesses `validation_service` through `PurlResolutionService.validation_service` property

## Configuration

### Environment Variables

| Key | Default | Description |
|---|---|---|
| `PURL2REPO_TIMEOUT` | `15.0` | Timeout for purl2repo HTTP requests (seconds) |
| `PURL2REPO_USE_CACHE` | `true` | Enable purl2repo file-based caching |
| `PURL2REPO_STRICT` | `false` | Strict mode — purl2repo raises instead of returning warnings |
| `PURL2REPO_NO_NETWORK` | `false` | Disable network access for purl2repo |
| `PURL2REPO_CACHE_DIR` | `None` | Custom cache directory path for purl2repo |
| `DB_URL` | `postgresql://sbom:sbom@localhost:5432/sbom` | PostgreSQL connection string |
| `DB_POOL_MIN_SIZE` | `2` | Minimum asyncpg pool connections |
| `DB_POOL_MAX_SIZE` | `10` | Maximum asyncpg pool connections |
| `SBOM_MAX_FILE_SIZE` | `209715200` (200 MB) | Maximum uploaded SBOM file size (bytes) |
| `SETTINGS_FILE` | `./data/settings.json` | Path to JSON settings file |

### JSON Settings (`data/settings.json`)

| Key | Default | Description |
|---|---|---|
| `validate_db_urls` | `false` | Enable URL validation for cached repository URLs |
| `validate_sbom_refs` | `false` | Enable URL validation for existing VCS references in SBOM files |
| `sbom_multiple_vcs_behavior` | `"keep-first"` | Behavior when SBOM component has multiple VCS refs (`"keep-first"` or `"keep-all"`) |
| `url_validation_timeout` | `5` | Timeout in seconds for HEAD and multi-VCS probe checks (1–60) |
| `librariesio_enabled` | `false` | Enable libraries.io as a fallback resolver after purl2repo |
| `librariesio_api_key` | `null` | Libraries.io API key for higher rate limits (60 req/min vs 10 req/min) |
| `depsdev_enabled` | `true` | Enable deps.dev as a fallback resolver after purl2repo (no API key required) |
| `revalidation_cooldown_hours` | `24` | Re-validation cooldown in hours (0 = no cooldown, max 720) |
| `ecosystems_enabled` | `true` | Enable ecosyste.ms as a fallback resolver |
| `apk_resolver_enabled` | `true` | Enable APK resolver (Alpine Linux) fallback — returns `https://github.com/alpinelinux/aports` for any `pkg:apk/...` PURL |
| `ecosystems_api_key` | `null` | Optional API key for ecosyste.ms (higher rate limits) |
| `ecosystems_max_requests_per_second` | `2.0` | Rate limit for ecosyste.ms API requests (0.1–100) |
| `retry_max_attempts` | `3` | Maximum HTTP request attempts per resolver (1–10). Applied to ecosyste.ms and libraries.io on timeout, 429, and 5xx errors. |
| `retry_base_cooldown_seconds` | `5.0` | Base wait time between retries; actual wait = cooldown × (attempt − 1). Range: 0.5–120. |
| `batch_semaphore_limit` | `10` | Maximum concurrent resolution requests in batch mode (1–100) |
| `batch_max_items` | `100` | Maximum PURLs per batch request (1–1000) |
| `job_ttl_hours` | `24` | Time-to-live in hours for async job records (1–720) |
| `connectivity_url` | `"https://github.com"` | URL used for connectivity probes |
| `connectivity_timeout` | `2` | Timeout in seconds for connectivity probes (1–30) |
| `log_level` | `"INFO"` | Application log level (DEBUG, INFO, WARNING, ERROR, CRITICAL) |
| `language` | `"en"` | UI language (`"en"` or `"ru"`) |
| `json_indent` | `4` | Number of spaces for JSON indentation in downloaded files (1, 2, or 4) |
| `llm_resolver_enabled` | `false` | Enable the LLM resolver as the last resolver in the chain |
| `llm_resolver_base_url` | `null` | OpenAI-compatible API base URL (`^https?://`) |
| `llm_resolver_api_key` | `null` | LLM API key |
| `llm_resolver_model` | `null` | LLM model name |
| `llm_resolver_attempts_count` | `2` | Total LLM attempts per PURL (1–10) |
| `llm_resolver_timeout` | `60` | LLM request timeout in seconds (1–600) |

## Database Schema

The `resolved_purls` table stores resolution results:

| Column | Type | Constraints |
|---|---|---|
| `purl` | `TEXT` | `PRIMARY KEY` |
| `repository_url` | `TEXT` | `NOT NULL` |
| `resolver` | `TEXT` | `NOT NULL` |
| `resolved_at` | `TIMESTAMPTZ` | `NOT NULL DEFAULT NOW()` |

Created on startup via `CREATE TABLE IF NOT EXISTS`. Schema is defined in `storage/schema.sql` alongside the `jobs` table. An index on `resolver` column (`idx_resolved_purls_resolver`) is created after the table to accelerate `SELECT DISTINCT resolver` queries.