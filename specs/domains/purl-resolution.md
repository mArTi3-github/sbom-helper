# PURL Resolution

## Description

Core capability of the system. Accepts a single Package URL (PURL) string and returns the corresponding source code repository URL with confidence, evidence, and metadata. Uses a two-tier strategy: first checks PostgreSQL for a cached result, and on cache miss delegates resolution to the resolver chain (purl2repo → ecosyste.ms → libraries.io), storing successful results for future lookups.

## Key Files

- `src/purl_resolver/router.py` — API endpoint handlers that call the Service Layer
- `src/purl_resolver/service.py` — `PurlResolutionService` class: Orchestration → validation → normalization → storage lookup → URL validation → resolver → storage store; `resolve_batch()` for concurrent resolution; `store_preexisting_references()` for SBOM pre-existing refs
- `src/purl_resolver/sbom_enrichment.py` — `SbomEnrichmentPipeline` orchestrating the full SBOM enrichment workflow: parse → collect → resolve → enrich → remove → report
- `src/purl_resolver/purl_utils/` — PURL validation, normalization, and `safe_normalize()` convenience function
- `src/purl_resolver/resolver/` — Resolver abstraction (ABC, Resolution, exceptions), purl2repo wrapper, ecosyste.ms wrapper, libraries.io wrapper, and factory module
- `src/purl_resolver/resolver/factory.py` — `build_resolvers(settings, app_settings) → list[Resolver]`: centralizes resolver initialization; creates Purl2RepoResolver, conditionally adds EcosystemsResolver and LibrariesIoResolver based on settings
- `src/purl_resolver/resolver/ecosystems.py` — `EcosystemsResolver`: fallback resolver using ecosyste.ms Packages API, enabled by default (settings-controlled), no API key required (optional for higher rate limits)
- `src/purl_resolver/resolver/librariesio.py` — `LibrariesIoResolver`: fallback resolver using libraries.io API, optional (settings-controlled), supports: cargo, composer, conda, cpan, cran, gem, generic, golang, hackage, hex, maven, npm, nuget, pub, pypi, swift
- `src/purl_resolver/schemas.py` — Request and response data models
- `src/purl_resolver/storage/` — Storage Layer (interface, postgres, inmemory implementations)
- `src/purl_resolver/sbom/parser.py` — CycloneDX SBOM validation and parsing
- `src/purl_resolver/sbom/collector.py` — Recursive component collection with path tracking, `needs_enrichment` and `has_subcomponents` detection
- `src/purl_resolver/sbom/enricher.py` — Inserts VCS external references into SBOM components
- `src/purl_resolver/sbom/remover.py` — Removes unresolved components without subcomponents from SBOM
- `src/purl_resolver/sbom/reporter.py` — Builds enrichment report with found/not_found/removed counts
- `src/purl_resolver/settings_store.py` — JSON-based application settings persistence (validate_db_urls, url_validation_timeout, revalidation_cooldown_hours, resolver toggles, API keys)
- `src/purl_resolver/url_validator.py` — URL validation via HTTP HEAD + git ls-remote with rate limit mitigation; returns `UrlValidationOutput` dataclass capturing the final URL after 3xx redirects
- `tests/test_api.py` — Integration tests for resolution workflow
- `tests/test_storage.py` — Unit tests for service and in-memory cache

## Core Types

```python
class ResolveRequest(BaseModel):
    purl: str = Field(..., min_length=1, description="Package URL to resolve")

class ResolveResponse(BaseModel):
    purl: str  # normalized form: scheme:type/namespace/name
    repository_url: str | None = None
    repository_type: str | None = None
    repository_kind: str | None = None
    confidence: str | None = None
    evidence: list[str] = []
    warnings: list[str] = []
    version_reference: str | None = None
    resolver: str = ""
    found_by: str = ""
    resolved_at: str = ""

class ErrorResponse(BaseModel):
    error: str
    message: str

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
    TOKEN_INVALID = "token_invalid"

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
  | POST /api/v1/resolve     |                          |                        |                |                |
  | {"purl": "pkg:..."}      |                          |                        |                |                |
  |------------------------->|                          |                        |                |                |
  |                          | service.resolve_purl()   |                        |                |                |
  |                          |------------------------->|                        |                |                |
  |                          |                          | validate(purl_str)     |                |                |
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
  |                          |                          | validate_url_with_retry(url, timeout)   |                |                |
   |                          |                          | ------+               |                |                |
   |                          |                          |        | HEAD + git   |                |                |
   |                          |                          | <------+               |                |                |
   |                          |                          |                        |                |                |
   |                          |                          | VALID → store(cached)  |                |                |
   |                          |                          |  (при отличии output.  |                |                |
   |                          |                          |   final_url URL в кэше |                |                |
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
   |                          |                          | validate_url_with_retry(url, timeout)   |                |                |
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
  |                          | 200 {normalized purl}    |                        |                |                |
  |<-------------------------|--------------------------|                        |                |                |
```

## Invariants

- Every valid PURL returns HTTP 200 (with `repository_url: null` if unresolved)
- Invalid PURL format is caught at the application level (purl_utils) before any resolver or storage call — HTTP 400
- Unsupported ecosystems return HTTP 200 with `repository_url: null` and a warning (purl2repo returns `Resolution(None)`, resolver chain continues)
- Upstream errors (registry timeout, network failure) always return HTTP 502
- The response format is canonical — it does not expose purl2repo's internal structure
- Empty purl strings are rejected at the Pydantic validation level (HTTP 422)
- `version_reference` is a URL string (not the purl2repo ReleaseLink object)
- **Normalized cache keys**: storage uses `scheme:type/namespace/name` form — version/qualifiers/subpath are stripped
- **Resolver receives original PURL**: the full string (with version, qualifiers, subpath) is passed unmodified to resolvers
- **DB cache hit**: if a result is found in PostgreSQL, the resolver is NOT called (unless URL validation is enabled and the entry is outside the cooldown window — for trusted resolvers, cooldown is `revalidation_cooldown_hours`; for untrusted resolvers, cooldown is always bypassed)
- **Only successful results are stored**: `repository_url = null` results are never persisted
- **Graceful degradation**: if PostgreSQL is unavailable, the resolver still works (without caching)
- **Store is best-effort**: a failure to store does not break the response to the client
- **URL validation is optional**: controlled by `validate_db_urls` setting (default: off). When enabled, validation applies to both cached entries and freshly resolved URLs. For cached entries, uses resolver-based cooldown; for fresh entries, validation runs synchronously before storing/returning.
- **Fresh URL validation skips invalid results**: when `validate_db_urls=true`, a freshly resolved URL returning `INVALID` via `validate_url()` causes the resolver chain to continue to the next resolver. The invalid result is neither stored nor returned. `NETWORK_ERROR` and `RATE_LIMITED` results keep the current resolver's result (store + return) to avoid discarding potentially valid URLs due to transient errors.
- **Fresh validation with TOKEN_INVALID retries without token**: same retry logic as cached validation — if `TOKEN_INVALID` is returned, the token is cleared and validation retried without authentication.
- **Resolver-based cooldown**: Trusted resolvers (`purl2repo`, `ecosyste.ms`, `libraries.io`) respect `revalidation_cooldown_hours` setting; entries from other resolvers (e.g. `import-sbom`, `import-csv`) always trigger validation regardless of cooldown
- **Cooldown disabled at zero**: Setting `revalidation_cooldown_hours=0` disables cooldown entirely — every cached entry triggers validation when `validate_db_urls=true`
- **Rate-limit cooldown no longer masks invalid URLs**: During rate-limit cooldown, `validate_url()` returns `RATE_LIMITED` instead of `VALID` — cache is preserved but `resolved_at` is not updated, so the next request after cooldown performs real validation
- **SBOM existing-ref validation**: Optional checkbox `validate_existing_refs` in SBOM Updater validates existing VCS references via HEAD + git ls-remote; `INVALID` results mark the component for re-resolution (`needs_enrichment=True`)
- **Connection errors preserve cache**: network errors during validation return `NETWORK_ERROR`, preserving the cached URL
- **Rate limit protection**: after 5 consecutive rate-limited responses, all validation is skipped for 60 seconds, returning `RATE_LIMITED`
- **Validation never crashes**: `validate_url()` and `validate_url_with_retry()` always return a `UrlValidationOutput`, never raise exceptions
- **Non-http/https URLs are invalid immediately**: `validate_url()` returns `UrlValidationOutput(INVALID)` for any URL that does not start with `http://` or `https://` without making any network request
- **revalidation_cooldown_hours bounds**: validated server-side with `ge=0, le=720` in both `AppSettings` and `SettingsUpdate`
- **Resolver field tracks origin**: every stored record has a `resolver` field indicating how it was added — `"purl2repo"` when purl2repo found the result, `"ecosyste.ms"` when ecosyste.ms found the result, `"libraries.io"` when libraries.io found the result, `"import-sbom"` for SBOM enrichment, `"import-csv"` for CSV import
- **URL redirects are resolved on validation**: `validate_url()` and `validate_url_with_retry()` return `UrlValidationOutput` containing the final URL after all 3xx redirects; `final_url` is `str(resp.url)` from httpx with `follow_redirects=True`
- **`git ls-remote` uses the resolved final URL**: `_git_ls_remote()` receives the final redirect target, not the original URL
- **Cache entries updated with final URL on VALID**: `_validate_cached_url()` updates `cached.repository_url` when `final_url` differs from the stored URL on `VALID` result only
- **Fresh resolver results use final URL**: `resolve_purl()` stores and returns the resolved final URL for any non-INVALID validation result (including `NETWORK_ERROR`/`RATE_LIMITED`)
- **SBOM refs updated on any non-INVALID result**: `sbom_enrichment.py` updates `ref["url"]` with `final_url` when the ref redirected, regardless of whether validation result was `VALID`, `NETWORK_ERROR`, or `RATE_LIMITED`
- **Canonical repository_kind values**: `repository_kind` uses `"vcs"` for VCS repository URLs (GitHub, GitLab, etc.) and `"source-distribution"` for source distribution/tarball URLs; the `REPOSITORY_KINDS` constant in `schemas.py` defines the valid set; `collector.py` uses the same values to identify existing source references
- **SBOM enrichment uses resolver="import-sbom"**: both `PurlResolutionService.resolve_batch()` and `PurlResolutionService.store_preexisting_references()` in the SBOM flow store records with `resolver: "import-sbom"`
- **SBOM deduplication validates each PURL explicitly**: the deduplication loop calls `validate()` then `normalize()` on every component PURL; unversioned valid PURLs (e.g. `pkg:pypi/ptaf-task-manager`) are correctly normalized and added to the resolution queue — only truly invalid PURLs are counted as skipped
- **CSV import uses resolver="import-csv"**: when the `resolver` column is absent from the imported CSV, the value `"import-csv"` is used as default
- **SBOM enrichment enriches before removing**: `enrich_sbom()` is called before `remove_unresolved_components()` to avoid stale component paths after in-place removal
- **Removed components excluded from not_found**: components with `status: "removed"` do not appear as `status: "not_found"` in the report

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
| `url_validation_timeout` | `5` | Timeout in seconds for HEAD and git ls-remote checks (1–60) |
| `github_token` | `null` | GitHub Personal Access Token for authenticated requests (git ls-remote, HTTP HEAD) |
| `librariesio_enabled` | `false` | Enable libraries.io as a fallback resolver after purl2repo |
| `librariesio_api_key` | `null` | Libraries.io API key for higher rate limits (60 req/min vs 10 req/min) |
| `revalidation_cooldown_hours` | `24` | Re-validation cooldown in hours for trusted resolvers (0 = no cooldown, max 720) |
| `ecosystems_enabled` | `true` | Enable ecosyste.ms as a fallback resolver after purl2repo |
| `ecosystems_api_key` | `null` | Optional API key for ecosyste.ms (higher rate limits) |
| `ecosystems_max_requests_per_second` | `2.0` | Rate limit for ecosyste.ms API requests (0.1–100) |
| `retry_max_attempts` | `3` | Maximum HTTP request attempts per resolver (1–10). Applied to ecosyste.ms and libraries.io on timeout, 429, and 5xx errors. |
| `retry_base_cooldown_seconds` | `5.0` | Base wait time between retries; actual wait = cooldown × (attempt − 1). Range: 0.5–120. |
| `log_level` | `"INFO"` | Application log level (DEBUG, INFO, WARNING, ERROR, CRITICAL) |

## Database Schema

The `resolved_purls` table stores resolution results:

| Column | Type | Constraints |
|---|---|---|
| `purl` | `TEXT` | `PRIMARY KEY` |
| `repository_url` | `TEXT` | `NOT NULL` |
| `repository_type` | `TEXT` | nullable |
| `repository_kind` | `TEXT` | nullable |
| `confidence` | `TEXT` | nullable |
| `evidence` | `JSONB` | `DEFAULT '[]'` |
| `warnings` | `JSONB` | `DEFAULT '[]'` |
| `version_reference` | `TEXT` | nullable |
| `resolver` | `TEXT` | `NOT NULL DEFAULT 'purl2repo'` |
| `resolved_at` | `TIMESTAMPTZ` | `NOT NULL DEFAULT NOW()` |

Created on startup via `CREATE TABLE IF NOT EXISTS`. All new columns must be nullable or have a DEFAULT value to ensure backward compatibility.