# Layer Architecture

## Layer Diagram

```
+---------------------------------------------------+
|  Docker Container                                  |
|  +-----------------------------+                   |
|  |     HTTP Client             |                   |
|  |  (Browser, curl, scripts)   |                   |
|  +-------------+---------------+                   |
|                |                                   |
|                | HTTP JSON / multipart              |
|                v                                   |
|  +-----------------------------+                   |
|  |     API Layer               |                   |
|  |  src/purl_resolver           |                   |
|  |  router.py (sub-routers in  |                   |
|  |  routes/ subpackage)        |                   |
|  |                             |                   |
|  |  POST /api/v1/resolve/batch |                |
|  |  GET /health               |                   |
|  |  GET / (HTML page)         |                   |
|  |  GET /sbom-updater         |                   |
|  |  GET /db-admin             |                   |
|  |  GET /images-list-converter |
|  |  GET /settings             |                   |
|  |  GET /api/v1/db/purls      |                   |
|  |  GET /api/v1/db/resolvers  |                   |
|  |  PATCH /api/v1/db/purls/   |                   |
|  |  DELETE /api/v1/db/purls   |                   |
|  |  POST /api/v1/db/import    |                   |
|  |  POST /api/v1/db/export    |                   |
|  |  GET /api/v1/settings      |                   |
|  |  PATCH /api/v1/settings    |                   |
|  +-------------+---------------+                   |
|                |                                   |
|                | Python call                       |
|                v                                   |
|  +-----------------------------+                   |
|  |  Service Layer                |                   |
|  |  src/purl_resolver/service  |                   |
|  |                             |                   |
|  |  PurlResolutionService      |                   |
|  |    .resolve_purl()          |                   |
|  |    .resolve_batch()         |                   |
|  |    .store_preexisting_refs()|                   |
|  +----+--------------------+---+                   |
|       |                    |                       |
|       | Python call        | Python call           |
|       v                    v                       |
|  +----------+     +------------------+             |
|  | PURL     |     |  Storage Layer   |             |
|  | Utils    |     |  storage/        |             |
|  | Layer    |     |                  |             |
|  |          |     |  lookup()        |             |
|  | validate |     |  store()         |             |
|  | normalize|     +----+-------------+             |
|  | safe_    |          |                           |
|  | normalize|          | asyncpg                   |
|  +----------+          v                           |
|       |         +----------+                       |
|       v         |PostgreSQL|                       |
|  +-----------------------------+                   |
|  |   Resolver Layer            |                   |
|  |  resolver/                  |                   |
|  |                             |                   |
|  |  Resolver (ABC)             |                   |
|  |  Resolution dataclass       |                   |
|  |  build_resolvers() factory  |                   |
 |  |  Purl2RepoResolver          |                   |
 |  |  EcosystemsResolver         |                   |
 |  |  LibrariesIoResolver        |                   |
 |  |  ApkResolver                |                   |
 |  |  (future: LLM, purl2src)   |                   |
|  +----+------------------------+                   |
|       |                                            |
|       | Python call                                |
|       v                                            |
|  +-----------------------------+                   |
|  |     Domain Layer            |                   |
|  |  (purl2repo, future LLM)    |                   |
|  |  resolve(original_purl)     |                   |
|  +-----------------------------+                   |
|                                                    |
|  +-----------------------------+                   |
|  |     URL Validator           |                   |
|  |  url_validator.py           |                   |
|  |                             |                   |
|  |  validate_url()             |                   |
|  |  ensure_connectivity()      |                   |
|  |  HEAD + multi-VCS probe    |                   |
|  |  Rate limit mitigation      |                   |
|  |  Redirect resolution        |                   |
|  |    follows 3xx, captures    |                   |
|  |    final URL, returns       |                   |
|  |    UrlValidationOutput      |                   |
|  |    with final_url field     |                   |
|  +----+------------------------+                   |
|       |                                            |
|       | diskcache                                  |
|       v                                            |
|  +-----------------------------+                   |
|  |  URL Validation Cache       |                   |
|  |  url_validation_cache.py    |                   |
|  |                             |                   |
|  |  UrlValidationCache         |                   |
|  |    .get(url, max_age)       |                   |
|  |    .put(url)                |                   |
|  |    .expire(max_age)         |                   |
|  |    .clear()                 |                   |
|  |  diskcache-based            |                   |
|  +-----------------------------+                   |
|                                                    |
|  |     Settings Store          |                   |
|  |  settings_store.py          |                   |
|  |                             |                   |
|  |  SettingsStore              |                   |
|  |  load() / save()            |                   |
|  |  JSON file persistence      |                   |
|  +-----------------------------+                   |
|                                                    |
|  +-----------------------------+                   |
|  |     Ignore Patterns Store   |                   |
|  |  ignore_patterns_store.py   |                   |
|  |                             |                   |
|  |  IgnorePatternsStore        |                   |
|  |  load() / save()            |                   |
|  |  JSON file persistence      |                   |
|  +-----------------------------+                   |
|                                                    |
|  +-----------------------------+                   |
|  |  SBOM Enrichment Pipeline   |                   |
|  |  sbom_enrichment.py         |                   |
|  |                             |                   |
|  |  SbomEnrichmentPipeline     |                   |
|  |    .process(sbom_data)      |                   |
|  |  SbomEnrichmentResult       |                   |
|  +----+------------------------+                   |
|       |                                            |
|       | uses                                        |
|       v                                            |
|  +-----------------------------+                   |
|  |     SBOM Module             |                   |
|  |  src/purl_resolver/sbom/    |                   |
|  |                             |                   |
|  |  parser.py — CycloneDX     |                   |
|  |             validation      |                   |
|  |  collector.py — recursive   |                   |
|  |             PURL collection |                   |
|  |  enricher.py — insert VCS  |                   |
|  |             refs            |                   |
|  |  remover.py — remove       |                   |
|  |             unresolved     |                   |
|  |  reporter.py — result table|                   |
|  |  images_list_converter.py  |                   |
|  |             — container     |                   |
|  |               promotion     |                   |
|  +-----------------------------+                   |
|                                                    |
|  +-----------------------------+                   |
|  |  DB Admin Service           |                   |
|  |  db_admin_service.py        |                   |
|  |                             |                   |
|  |  DbAdminService             |                   |
|  |    .list_purls()            |                   |
|  |    .update_purl()           |                   |
|  |    .delete_purls()          |                   |
|  |    .import_csv()            |                   |
|  |    .export_csv()            |                   |
|  |  wraps csv_io + Storage     |                   |
|  +-----------------------------+                   |
|                                                    |
|  +-----------------------------+                   |
|  |  Job Manager                |                   |
|  |  job_manager.py             |                   |
|  |  job_repository.py          |                   |
|  |                             |                   |
|  |  JobManager                 |                   |
|  |    .create_job()            |                   |
|  |    .get_job() / .list_jobs()|                   |
|  |    .cancel_job()            |                   |
|  |    .delete_job()            |                   |
|  |  JobRecord dataclass        |                   |
|  |  Async queue + workers      |                   |
|  |  PostgreSQL-backed          |                   |
|  |  TTL-based cleanup          |                   |
|  +-----------------------------+                   |
|                                                    |
|  |  src/purl_resolver/config.py|                   |
|  |                             |                   |
|  |  Pydantic Settings          |                   |
|  |  PURL2REPO_* prefix         |                   |
|  |  DB_* prefix                |                   |
|  |  SBOM_* prefix              |                   |
|  +-----------------------------+                   |
|                                                    |
|  +-----------------------------+                   |
|  |     Web UI Layer            |                   |
|  |  frontend/                  |                   |
|  |  src/views/*.vue            |                   |
|  |  src/components/*.vue       |                   |
|  |  src/api/*.ts               |                   |
|  |  src/composables/*.ts       |                   |
|  |  src/types/api.ts           |                   |
|  |  src/router/index.ts        |                   |
|  |                             |                   |
|  |  Vue 3 SPA                  |                   |
|  |  Vue Router                 |                   |
|  |  TypeScript                 |                   |
|  |  Vite build → dist/         |                   |
|  |  SPAStaticFiles mount       |                   |
|  +-----------------------------+                   |
+---------------------------------------------------+
```

## Import Rules

- **API Layer** (`router.py` includes sub-routers from `routes/resolve.py`, `routes/db_admin.py`, `routes/settings.py`, `routes/images_list.py`, `routes/ignore_patterns.py`, `routes/jobs.py`)
- **API Layer (routes/)** accesses **Service Layer** and **SBOM Enrichment Pipeline** through `request.app.state` — but not vice versa
- **API Layer (routes/)** imports **csv_io** module for CSV parsing/rendering
- **API Layer (routes/settings.py)** imports **Config Layer** (settings) and **Resolver Layer** for `_rebuild_resolvers()` helper (uses `resolver.factory.build_resolvers()` to reconstruct resolver list on settings change)
- **API Layer (routes/)** imports **SBOM Module** (`sbom/images_list_converter.py`) for the images list conversion endpoint
- **Service Layer** imports **PURL Utils Layer** (`purl_utils/`), **Storage Layer** (`storage/interface.py`), **Resolver Layer** (`resolver/interface.py`), **URL Validator** (`url_validator.py`), **Validation Service** (`validation_service.py`), and **SBOM Module** (`sbom/`); exports `PurlResolutionService` class with constructor injection (`storage`, `resolvers`, `settings_store`, `validation_service`); exposes `settings_store` and `validation_service` as read-only properties for downstream consumers; dependencies are declared once in `__init__` instead of passed to every method; methods accept optional `resolver` parameter to tag stored records with their origin (e.g. `"import-sbom"`, `"import-csv"`); `resolve_batch()` uses `batch_semaphore_limit` from `AppSettings` for concurrency control
- **SBOM Enrichment Pipeline** (`sbom_enrichment.py`) imports **Service Layer** (`PurlResolutionService`), **SBOM Module** (`sbom/`), and **PURL Utils Layer** (`purl_utils/`); receives only `PurlResolutionService` via constructor injection, accessing `settings_store` and `validation_service` through its properties
- **SBOM Module** imports **PURL Utils Layer** for normalization; does not import Storage or Resolver directly
- **PURL Utils Layer** is a standalone module — imports only `packageurl-python`, no internal project imports
- **Storage Layer** is a standalone module — imports only asyncpg, no internal project imports outside `storage/`; exports `UpsertRow` dataclass for typed batch insert
- **Resolver Layer** (`resolver/`) defines the `Resolver` ABC (with `name` property and `resolve` method), `Resolution` dataclass, resolver-specific exceptions (`InvalidPurlError`, `UpstreamError`), and a `factory.py` module with `build_resolvers(settings, app_settings) → list[Resolver]` that centralizes resolver initialization. `Purl2RepoResolver` wraps the purl2repo library. `LibrariesIoResolver` wraps the libraries.io REST API with rate limiting and graceful degradation. `ApkResolver` is a local-only fallback for Alpine Linux APK packages.
- **Resolver Layer** imports purl2repo, httpx, and `purl_utils`; internal project code does NOT import purl2repo directly
- **PURL Utils Layer** does NOT depend on any resolver — it is resolver-agnostic
- **Config Layer** is a standalone module with no internal project imports
- **Web UI Layer** (`frontend/`) is a standalone Vue 3 SPA; communicates with the API Layer via HTTP (`fetch` → API endpoints); FastAPI serves the built SPA via `SPAStaticFiles` (custom `StaticFiles` subclass with `index.html` fallback for client-side routing); SPA is mounted after all API routes
- **API Layer (routes/jobs.py)** imports **Job Manager** (`job_manager.py`) for async SBOM enrichment; job endpoints are available only when PostgreSQL is available
- **Service Layer** depends on **DbAdminService** (`db_admin_service.py`) for database admin operations that wrap CSV I/O and Storage
- **Job Manager** (`job_manager.py`) imports **Job Repository** (`job_repository.py`), **SBOM Enrichment Pipeline** (`sbom_enrichment.py`), and **Service Layer** (`PurlResolutionService`)
- Tests (`tests/`) import `main:app` and FastAPI TestClient; unit tests for storage/service/purl_utils/resolvers/url_validator/sbom import them directly

## Layer Responsibilities

### API Layer (`routes/`)
- Define HTTP endpoints (routes, methods, status codes) — split across `routes/resolve.py`, `routes/db_admin.py`, `routes/settings.py`, `routes/images_list.py`, `routes/ignore_patterns.py`, `routes/jobs.py`
- Validate request input via Pydantic schemas
- Delegate single PURL resolution to Service Layer (`service.resolve_purl()`)
- Delegate SBOM enrichment to `SbomEnrichmentPipeline` (`sbom_enrichment.py`) via async jobs (routes/jobs.py) — handles parsing, collection, deduplication, batch resolution, and enrichment
- Delegate CSV parsing/rendering to csv_io module (`csv_io.parse_csv_import()`, `csv_io.render_csv_export()`)
- Delegate DB admin operations to `DbAdminService` (`db_admin_service.list_purls()`, `db_admin_service.update_purl()`, `db_admin_service.list_resolvers()`, etc.) which wraps Storage Layer and CSV I/O
- Delegate async SBOM enrichment to Job Manager via `routes/jobs.py` — creates background jobs (`POST /api/v1/jobs/sbom-enrich`), queries status (`GET /api/v1/jobs/{job_id}`), downloads results (`GET /api/v1/jobs/{job_id}/result`), cancels (`POST /api/v1/jobs/{job_id}/cancel`), deletes (`DELETE /api/v1/jobs/{job_id}`), lists (`GET /api/v1/jobs`)
- Delegate SBOM-to-images-list conversion to `ImagesListConverter` (`sbom/images_list_converter.py`) — validates SBOM format, promotes container components, deduplicates by `purl`, returns conversion result with completeness flags and duplicate counts
- Manage application settings via Settings Store (`GET/PATCH /api/v1/settings`); validates libraries.io API key via async `validate_librariesio_key()`; rebuilds resolver list on settings change via `_rebuild_resolvers()` using `resolver.factory.build_resolvers()`; clear validation cache via `POST /api/v1/settings/clear-validation-cache`
- Handle error responses from Service Layer and Pipeline
- Serve the Vue 3 SPA via `SPAStaticFiles` mounted at `/` in `main.py` (after all API routes); `SPAStaticFiles` falls back to `index.html` for any unmatched path, enabling Vue Router client-side routing

### Service Layer (`service.py`)
- `PurlResolutionService` class with constructor injection (`storage: Storage`, `resolvers: list[Resolver]`, `settings_store: SettingsStore | None = None`, `validation_service: UrlValidationService | None = None`)
- Orchestrate single resolution flow (`resolve_purl`): validate PURL → normalize cache key → storage lookup → URL validation (if enabled) → resolver chain (iterates resolvers, first success wins) → storage store; uses `resolver.name` property to tag stored records with the actual resolver identifier (e.g. `"purl2repo"`, `"libraries.io"`)
- URL validation: when `validate_db_urls` is enabled, verify cached URLs via HEAD + multi-VCS probe (`_check_vcs`: git → svn → hg → fossil); delete invalid URLs and fall through to resolver chain; skip validation if within cooldown window (trusted resolvers respect `revalidation_cooldown_hours`). Cache entries are updated with the resolved final URL when `_validate_cached_url()` receives a `UrlValidationOutput` whose `final_url` differs from the stored URL on `VALID` result. Fresh resolver results use `final_url` for any non-INVALID validation result. URL validation delegates to `UrlValidationService` when provided, otherwise calls `validate_url()` directly.
- Batch resolution (`resolve_batch`): resolve multiple PURLs concurrently via `asyncio.gather()` with semaphore limit from `AppSettings.batch_semaphore_limit` (default: 10); returns `dict[str, str]` of normalized PURL → repository URL for successful resolutions; uses `self._settings_store` for URL validation (no longer accepts it per-call)
- Store pre-existing references (`store_preexisting_references`): for SBOM components with `needs_enrichment=False`, extract VCS repository URL from `externalReferences` and store in database via `self._storage.store()`
- Map resolver `Resolution` to canonical `ResolveResponse` format (purl, repository_url, warnings, resolver, found_by, resolved_at); tag stored records with `resolver.name` (e.g. `"purl2repo"`, `"libraries.io"`)
- Handle graceful degradation: if storage is unavailable, fall through to resolver
- Log errors from storage without breaking the response

### SBOM Enrichment Pipeline (`sbom_enrichment.py`)
- Orchestrate the complete CycloneDX SBOM enrichment workflow in a single class
- `SbomEnrichmentPipeline.__init__(resolution_service: PurlResolutionService)` — receives dependencies via constructor; `settings_store` and `validation_service` are accessed through `resolution_service` properties
- `SbomEnrichmentPipeline.process(sbom_data) → SbomEnrichmentResult` — executes the pipeline: validate SBOM format → collect components → deduplicate PURLs → batch resolve → store pre-existing references → enrich SBOM → build report
- Decouples HTTP layer (router) from domain orchestration logic
- Testable without FastAPI TestClient — can be instantiated with mock storage and resolvers
- Returns `SbomEnrichmentResult` dataclass with `report` and `enriched_sbom` fields

### DB Admin Service (`db_admin_service.py`)
- `DbAdminService` class with constructor injection (`storage: Storage`)
- Encapsulates database admin operations between API routes and Storage Layer
- `list_purls(params: PurlListParams) → PurlListResponse` — paginated listing with search/filter/sort
- `update_purl(purl_key: str, update: PurlUpdateRequest)` — inline edit of a PURL row
- `delete_purls(purls: list[str]) → int` — bulk delete
- `list_resolvers() → list[str]` — returns distinct resolver values from storage; consumed by `GET /api/v1/db/resolvers`
- `import_csv(text, strategy) → ImportResponse` — delegates to `csv_io.parse_csv_import()` then bulk-stores via Storage Layer
- `export_csv(purls: list[str]) → str` — fetches from Storage Layer, delegates to `csv_io.render_csv_export()`
- Testable without FastAPI TestClient — pure service with injectable Storage dependency

### Job Manager (`job_manager.py`, `job_repository.py`)
- `JobManager` class with constructor injection (`pool: asyncpg.Pool`, `resolution_service: PurlResolutionService`, `job_ttl_hours: int`)
- Async background job processing for SBOM enrichment; available only when PostgreSQL is connected
- `create_job(raw_input, filename, params) → JobRecord` — saves SBOM file to disk, creates job record with `status: queued`, enqueues job for async processing
- Background worker processes jobs: runs `SbomEnrichmentPipeline.process()` with the uploaded SBOM data, stores enriched result to disk, updates progress
- `get_job(job_id) → JobRecord | None` — returns current job status and results
- `list_jobs(limit, offset) → list[JobRecord]` — paginated job listing
- `cancel_job(job_id) → bool` — sets `cancel_requested` flag; worker checks flag between processing steps
- `delete_job(job_id) → bool` — removes job record and associated result file
- TTL-based cleanup: expired jobs are cleaned up by a periodic background task
- `JobRepository` provides PostgreSQL persistence for `JobRecord` dataclass (id, type, status, progress, params, result paths, timestamps)
- Job status lifecycle: `queued` → `running` → `completed` | `failed` | `cancelled`

### CSV I/O Module (`csv_io.py`)
- Pure functions for CSV parsing and rendering, no HTTP or Storage dependencies
- `parse_csv_import(text) → tuple[list[UpsertRow], list[dict]]` — parses CSV into typed UpsertRow objects and error list; handles BOM, comma delimiter, required column validation (`purl`, `repository_url`), RFC 4180 quoting; when `resolver` column is absent, defaults to `"import-csv"`
- `render_csv_export(rows: list[PurlRow]) → str` — renders PurlRow objects as comma-delimited CSV string with four columns (`purl`, `repository_url`, `resolver`, `resolved_at`) and automatic RFC 4180 quoting
- Dependencies: only `csv`, `io`, `json` from stdlib

### PURL Utils Layer (`purl_utils/`)
- **`__init__.py`** — `validate(purl) → PurlComponents` (raises `PurlValidationError`), `normalize(components) → str`, `safe_normalize(purl) → str`
- `safe_normalize` wraps `validate` + `normalize` with exception handling — returns the original purl string on any error
- Validate PURL format using the official `packageurl-python` library
- Normalize PURL to `scheme:type/namespace/name` form (namespace only if present)
- `PurlValidationError` — resolver-agnostic exception for invalid PURLs
- Has zero dependency on any resolver implementation

### SBOM Module (`sbom/`)
- **`__init__.py`** — Public exports: `SbomComponent`, `CycloneDXParser`, `SbomParseError`, `collect_components`, `enrich_sbom`, `build_report`
- **`parser.py`** — `CycloneDXParser.parse(data) → dict` validates `bomFormat: CycloneDX`; raises `SbomParseError` on violation
- **`collector.py`** — `collect_components(sbom) → list[SbomComponent]` recursively walks `components[]` arrays; `SbomComponent` dataclass tracks purl, path tuple, needs_enrichment flag, and existing references; components with `vcs` or `source-distribution` external references are marked as not needing enrichment
- **`enricher.py`** — `enrich_sbom(sbom, components, resolved)` inserts `{"type": "vcs", "url": "..."}` into component `externalReferences` arrays at the correct paths; preserves existing references; increments `version` field by 1
- **`remover.py`** — `remove_unresolved_components(sbom, components, resolved) → list[dict]` removes components that need enrichment, have no subcomponents, and were not resolved; returns list of removed component dicts
- **`reporter.py`** — `build_report(components, resolved, skipped)` returns `{summary, results}`; only includes components with `needs_enrichment=True`; deduplicates by normalized PURL; removed components are excluded from `not_found` counts
- **`images_list_converter.py`** — `ImagesListConverter.convert(data) → ImagesListConversionResult` validates SBOM format via `CycloneDXParser`, checks if all top-level components are `type=container`, recursively collects container components from all nesting levels, promotes them to top-level, removes non-container components, deduplicates remaining containers by `purl` field (first-wins, components without `purl` treated as unique); returns `ImagesListConversionResult` with `was_transformed` flag, `images` list (with completeness flags and per-image duplicate count), and the resulting `images_list` dict
- Imports `purl_utils` for PURL normalization; does not import storage or resolver modules directly

### Config Layer (`config.py`)
- Provide typed access to all runtime configuration
- Load from environment variables (set via docker-compose.yml in production, or `.env` in development)
- `Settings` class uses the `PURL2REPO_` prefix for resolver settings
- `StorageSettings` class uses the `DB_` prefix for database connection settings (`DB_URL`, etc.)
- `SbomSettings` class uses the `SBOM_` prefix for SBOM processing (`SBOM_MAX_FILE_SIZE`, default 200 MB)

### Settings Store (`settings_store.py`)
- JSON-based persistence for application settings (validate_db_urls, validate_sbom_refs, sbom_multiple_vcs_behavior, url_validation_timeout, librariesio_enabled, librariesio_api_key, ecosystems_enabled, ecosystems_api_key, apk_resolver_enabled, retry_max_attempts, retry_base_cooldown_seconds, log_level, ecosystems_max_requests_per_second, batch_semaphore_limit, job_ttl_hours, connectivity_url, connectivity_timeout, language, json_indent)
- `SettingsStore` class with `load() → AppSettings` and `save(settings)` methods
- `AppSettings` Pydantic model with field validation (url_validation_timeout: 1–60, retry_max_attempts: 1–10, retry_base_cooldown_seconds: 0.5–120, batch_semaphore_limit: 1–100, job_ttl_hours: 1–720, connectivity_timeout: 1–30)
- File path from `SETTINGS_FILE` env var (default: `./data/settings.json`)
- Graceful handling: missing file → create with defaults; corrupt JSON → log warning, return defaults

### Ignore Patterns Store (`ignore_patterns_store.py`)
- JSON-based persistence for SBOM component ignore patterns (field/pattern pairs used to exclude components from enrichment)
- `IgnorePatternsStore` class with `load() → list[dict]` and `save(patterns)` methods
- File path default: `./data/sbom_components_ignore_patterns.json`
- Graceful handling: missing file → return empty list; corrupt JSON → log warning, return empty list
- Exposed via API endpoints `GET/POST /api/v1/sbom/ignore-patterns` in `routes/ignore_patterns.py`

### URL Validation Cache (`url_validation_cache.py`)
- `UrlValidationCache` class wrapping `diskcache.Cache` for persistent URL validation result caching
- `get(url, max_age_seconds) → str | None` — returns cached URL if within TTL, `None` otherwise
- `put(url)` — records current timestamp for the URL
- `expire(max_age_seconds)` — removes entries older than max age
- `clear()` — clears the entire cache
- Used by `UrlValidationService` to avoid re-validating recently validated URLs within the cooldown window
- A background task in `main.py` calls `expire()` daily with `revalidation_cooldown_hours` setting as TTL

### URL Validator (`url_validator.py`)
- Validates repository URLs via HTTP HEAD + multi-VCS probe to verify the URL exists and is reachable
- `validate_url(url, timeout) → UrlValidationOutput` — performs HEAD (with `follow_redirects=True`), captures the final URL after all 3xx redirects via `str(resp.url)`, then runs `_check_vcs()` against the final URL; returns `UrlValidationOutput(result, final_url)`
- `ensure_connectivity(url=None, timeout=None) → bool` — connectivity probe against configurable URL (default `https://github.com`); raises `ConnectionError` on failure
- `_check_vcs(url, timeout) → bool | None` — unified multi-VCS probe; runs git → svn → hg → fossil sequentially with early-exit on first success; aggregation: `True` if any probe is `True`, else `False` if any is `False`, else `None`; called with the resolved final URL by `validate_url()`
- `_git_probe(url, timeout) → bool | None` — internal helper: `git ls-remote --exit-code <url>`
- `_svn_probe(url, timeout) → bool | None` — internal helper: `svn ls <url>`; exit 0 → True, exit ≠0 → False
- `_hg_probe(url, timeout) → bool | None` — internal helper: `hg identify <url>`; exit 0 → True, exit ≠0 → False
- `_fossil_probe(url, timeout) → bool | None` — combined probe: tries the authoritative /xfer protocol probe first (`_fossil_probe_xfer`), falls back to HTML footer regex (`_fossil_probe_footer`) when the xfer probe is uncertain (None)
- `_fossil_probe_xfer(url, timeout) → bool | None` — internal helper: minimal POST to `<url>/xfer` with `Content-Type: application/x-fossil-debug`; checks response Content-Type for `application/x-fossil` / `application/x-fossil-debug`; 401/403 → None; other → False; transport error → None
- `_fossil_probe_footer(url, timeout) → bool | None` — internal helper (fallback): HTTP GET with `follow_redirects=True`; status 200 + footer regex match → True; status 200 without footer → False; non-200 → False; transport error → None
- `UrlValidationResult` enum — `VALID`, `INVALID`, `NETWORK_ERROR`, `RATE_LIMITED`
- `UrlValidationOutput` dataclass — `result: UrlValidationResult`, `final_url: str | None = None`; `final_url` is `str(resp.url)` after redirects, `None` when HEAD did not execute (scheme error, cooldown, connectivity failure, HEAD exception)

### Web UI Layer (`frontend/`)
- Vue 3 SPA built with Vite + TypeScript, source in `frontend/src/`
- **Views** (`src/views/`): `PurlResolver.vue`, `SbomUpdater.vue`, `DatabaseAdmin.vue`, `Settings.vue`, `ImagesListConverter.vue`, `NotFound.vue`
- **Components** (`src/components/`): `AppNav.vue` (navigation bar), `FileUploadZone.vue` (drag-and-drop upload), `ModalDialog.vue` (reusable modal)
- **Composables** (`src/composables/`): `useDownload.ts` (file download helper)
- **Stores** (`src/stores/`): `useSettingsStore.ts` (Pinia store for settings), `useDbAdminStore.ts` (Pinia store for database admin state — includes pagination logic via `goToPage`, `changePageSize`, `totalPages`)
- **i18n** (`src/i18n/`): `index.ts` (vue-i18n configuration with `legacy: false`), `locales/en.json` (English), `locales/ru.json` (Russian); `@intlify/unplugin-vue-i18n` Vite plugin for compile-time message compilation
- **API client** (`src/api/`): typed fetch wrappers per domain — `client.ts` (base `request<T>()` + `ApiError`), `purl.ts`, `sbom.ts`, `db.ts`, `settings.ts`, `images.ts`
- **Types** (`src/types/api.ts`): TypeScript interfaces mirroring backend `schemas.py`
- **Router** (`src/router/index.ts`): Vue Router with `createWebHistory()`, 5 page routes + catch-all `/:pathMatch(.*)*` → `NotFound.vue`
- FastAPI serves the built SPA via `SPAStaticFiles` (custom `StaticFiles` subclass) mounted at `/` in `main.py`; `SPAStaticFiles` falls back to `index.html` for unmatched paths, enabling client-side routing
- Each `.vue` component uses `<style scoped>` for CSS isolation; global CSS variables in `src/assets/main.css`
- No CSS framework — design system uses CSS custom properties
- Build output: `frontend/dist/` (copied into Docker image via multi-stage build)

### Domain Layer (`purl2repo`)
- Resolve PURL strings to repository URLs with warnings and resolver attribution
- Manage internal file-based caching (independent of the Storage Layer)
- Our code does not import or modify purl2repo directly

### Resolver Layer (`resolver/`)
- **interface.py** — `Resolver(ABC)` with `name` property (returns resolver identifier string, e.g. `"purl2repo"`, `"libraries.io"`) and `async resolve(purl) → Resolution`; `Resolution` dataclass with `purl`, `repository_url`, `warnings`
- **factory.py** — `build_resolvers(settings, app_settings) → list[Resolver]` centralizes resolver initialization; creates `Purl2RepoResolver` from `Settings`, conditionally adds `EcosystemsResolver` (if `ecosystems_enabled`), `LibrariesIoResolver` (if `librariesio_enabled` and API key present), and `ApkResolver` (if `apk_resolver_enabled`); ApkResolver is always added last; used by both `main.py` lifespan and `_rebuild_resolvers()` in the API Layer
- **purl2repo.py** — `Purl2RepoResolver(Resolver)` wrapping purl2repo; `name` returns `"purl2repo"`; async implementation uses `asyncio.to_thread()` to offload synchronous purl2repo calls to a thread pool; `UnsupportedEcosystemError` returns `Resolution(repository_url=None)` with warning (not `InvalidPurlError`); maps `InvalidPurlError` to `InvalidPurlError`; maps `ResolutionError`/`MetadataFetchError` to `UpstreamError`
- **librariesio.py** — `LibrariesIoResolver(Resolver)` using libraries.io REST API; `name` returns `"libraries.io"`; async implementation uses `httpx.AsyncClient` and `asyncio.sleep()` for rate limiting; optional, settings-controlled (`librariesio_enabled` + `librariesio_api_key`); maps 16 PURL types to libraries.io platforms; rate-limited (1 req/sec via `asyncio.sleep()`); graceful degradation on errors (timeout, HTTP errors, network failures all return `Resolution` with warnings); uses `httpx.AsyncClient` and `purl_utils.validate()` for PURL parsing, now with configurable retry for HTTP 429, timeout, and 5xx
- **ecosystems.py** — `EcosystemsResolver(Resolver)` using ecosyste.ms Packages API; `name` returns `"ecosyste.ms"`; async implementation uses `httpx.AsyncClient`; enabled by default via settings (`ecosystems_enabled`); no API key required (optional for higher rate limits); configurable rate limiting via `ecosystems_max_requests_per_second` app setting; URL selection prioritizes GitHub URLs; graceful degradation on errors (timeout, HTTP errors, network failures all return `Resolution` with warnings); uses `httpx.AsyncClient` and `purl_utils.validate()` for PURL parsing, now with configurable retry for HTTP 429, timeout, and 5xx
- **apk.py** — `ApkResolver(Resolver)` for Alpine Linux APK packages; `name` returns `"apk"`; purely local — checks `validate().type == "apk"` and returns constant URL `https://github.com/alpinelinux/aports`; no network calls, no API key; enabled by default via `apk_resolver_enabled` setting; always placed last in the resolver chain
- **retry.py** — `RetryConfig` dataclass, `RetryableErrorPolicy` (retryable error classification), `RetryHelper` (async retry loop with linear backoff)
- Exceptions: `ResolverError`, `InvalidPurlError`, `UpstreamError`

## Anti-Patterns

- Importing purl2repo exception classes in the Web UI layer (Vue SPA communicates via HTTP only)
- Bypassing the API Layer — direct calls to purl2repo from the test client
- Calling purl2repo directly from the API Layer (must go through Service Layer)
- Putting SBOM enrichment orchestration logic in `router.py` — use `SbomEnrichmentPipeline` instead
- Storing state in the API Layer (the service is stateless by design)
- Changing the canonical response format without updating contracts/api-contract.md
- Running outside Docker for production deployment (development-only bare uvicorn)

## Container Deployment

### Base Image
`python:3.12-slim` — glibc compatibility for purl2repo's native dependencies. Alpine (musl) is rejected due to incompatibility risk; distroless is premature for the current stage.

### Build Strategy
Multi-stage Dockerfile:
- **frontend-build stage**: `node:20-alpine` — `npm ci` + `npm run build` to produce `frontend/dist/`
- **dev stage**: `python:3.12-slim`, editable install (`pip install -e .`), `--reload` for hot-reload development; copies built frontend from `frontend-build` stage
- **prod stage**: `python:3.12-slim`, non-editable install, `app` user (UID 1001), HEALTHCHECK configured; copies built frontend from `frontend-build` stage

### Docker Compose
- `docker-compose.yml` defines app service with `${VAR:-default}` pattern for deployment-specific overrides
- `docker-compose.override.yml` (auto-merged by Compose) mounts `./src` for Python hot-reload and `./frontend/dist` so frontend build output is available without rebuilding the image
- Frontend development: `cd frontend && npm run build -- --watch` for auto-rebuild on changes; the volume mount `./frontend/dist:/app/frontend/dist` in the override picks up rebuilt files without `docker compose up --build`
- Environment variables are the sole configuration mechanism (twelve-factor app). No `.env` is baked into the image.

### Security
- Production container runs as non-root user (UID 1001)
- HEALTHCHECK monitors service availability — container marked unhealthy on repeated failure

### Build Context
`.dockerignore` excludes `.git`, `.venv`, `__pycache__`, `.pytest_cache`, `.env` files to keep build context minimal. `pyproject.toml`, `src/`, and `frontend/` are copied separately to optimize Docker layer caching. `frontend/node_modules/` is not copied — `npm ci` in the `frontend-build` stage installs dependencies fresh.