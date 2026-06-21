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
|  |  POST /api/v1/resolve      |                   |
|  |  POST /api/v1/resolve/sbom |                   |
|  |  GET /health               |                   |
|  |  GET / (HTML page)         |                   |
|  |  GET /sbom-updater         |                   |
|  |  GET /db-admin             |                   |
|  |  GET /images-list-converter |
|  |  GET /settings             |                   |
|  |  GET /api/v1/db/purls      |                   |
|  |  PATCH /api/v1/db/purls/   |                   |
|  |  DELETE /api/v1/db/purls   |                   |
|  |  POST /api/v1/db/import    |                   |
|  |  GET /api/v1/db/export     |                   |
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
|  |  validate_github_token()    |                   |
|  |  ensure_connectivity()      |                   |
|  |  HEAD + git ls-remote       |                   |
|  |  Rate limit mitigation      |                   |
|  |  Token authentication       |                   |
|  +-----------------------------+                   |
|                                                    |
|  +-----------------------------+                   |
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
|  |     Config Layer            |                   |
|  |  src/purl_resolver/config   |                   |
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

- **API Layer** (`router.py` includes sub-routers from `routes/resolve.py`, `routes/db_admin.py`, `routes/settings.py`, `routes/images_list.py`, `routes/ignore_patterns.py`)
- **API Layer (routes/)** imports **Service Layer** (`service.py`) and **SBOM Enrichment Pipeline** (`sbom_enrichment.py`) — but not vice versa
- **API Layer (routes/)** imports **csv_io** module for CSV parsing/rendering
- **API Layer (routes/settings.py)** imports **Config Layer** (settings) and **Resolver Layer** for `_rebuild_resolvers()` helper (uses `resolver.factory.build_resolvers()` to reconstruct resolver list on settings change)
- **API Layer (routes/)** imports **SBOM Module** (`sbom/images_list_converter.py`) for the images list conversion endpoint
- **Service Layer** imports **PURL Utils Layer** (`purl_utils/`), **Storage Layer** (`storage/interface.py`), **Resolver Layer** (`resolver/interface.py`), **URL Validator** (`url_validator.py`), and **SBOM Module** (`sbom/`); exports `PurlResolutionService` class with constructor injection (`storage`, `resolvers`, `settings_store`); dependencies are declared once in `__init__` instead of passed to every method; methods accept optional `resolver` parameter to tag stored records with their origin (e.g. `"import-sbom"`, `"import-csv"`)
- **SBOM Enrichment Pipeline** (`sbom_enrichment.py`) imports **Service Layer** (`PurlResolutionService`), **SBOM Module** (`sbom/`), **PURL Utils Layer** (`purl_utils/`), **Storage Layer** (`storage/interface.py`), and **Resolver Layer** (`resolver/interface.py`); receives dependencies including `PurlResolutionService` via constructor injection
- **SBOM Module** imports **PURL Utils Layer** for normalization; does not import Storage or Resolver directly
- **PURL Utils Layer** is a standalone module — imports only `packageurl-python`, no internal project imports
- **Storage Layer** is a standalone module — imports only asyncpg, no internal project imports outside `storage/`; exports `UpsertRow` dataclass for typed batch insert
- **Resolver Layer** (`resolver/`) defines the `Resolver` ABC (with `name` property and `resolve` method), `Resolution` dataclass, resolver-specific exceptions (`InvalidPurlError`, `UpstreamError`), and a `factory.py` module with `build_resolvers(settings, app_settings) → list[Resolver]` that centralizes resolver initialization. `Purl2RepoResolver` wraps the purl2repo library. `LibrariesIoResolver` wraps the libraries.io REST API with rate limiting and graceful degradation.
- **Resolver Layer** imports purl2repo, httpx, and `purl_utils`; internal project code does NOT import purl2repo directly
- **PURL Utils Layer** does NOT depend on any resolver — it is resolver-agnostic
- **Config Layer** is a standalone module with no internal project imports
- **Web UI Layer** (`frontend/`) is a standalone Vue 3 SPA; communicates with the API Layer via HTTP (`fetch` → API endpoints); FastAPI serves the built SPA via `SPAStaticFiles` (custom `StaticFiles` subclass with `index.html` fallback for client-side routing); SPA is mounted after all API routes
- Tests (`tests/`) import `main:app` and FastAPI TestClient; unit tests for storage/service/purl_utils import them directly

## Layer Responsibilities

### API Layer (`routes/`)
- Define HTTP endpoints (routes, methods, status codes) — split across `routes/resolve.py`, `routes/db_admin.py`, `routes/settings.py`, `routes/images_list.py`, `routes/ignore_patterns.py`
- Validate request input via Pydantic schemas
- Delegate single PURL resolution to Service Layer (`service.resolve_purl()`)
- Delegate SBOM enrichment to `SbomEnrichmentPipeline` (`sbom_enrichment.py`) — handles parsing, collection, deduplication, batch resolution, and enrichment
- Delegate CSV parsing/rendering to csv_io module (`csv_io.parse_csv_import()`, `csv_io.render_csv_export()`)
- Delegate DB admin operations to Storage Layer (`storage.list_purls()`, `storage.update_purl()`, etc.)
- Delegate SBOM-to-images-list conversion to `ImagesListConverter` (`sbom/images_list_converter.py`) — validates SBOM format, promotes container components, returns conversion result with completeness flags
- Manage application settings via Settings Store (`GET/PATCH /api/v1/settings`); validates libraries.io API key via async `validate_librariesio_key()`; rebuilds resolver list on settings change via `_rebuild_resolvers()` using `resolver.factory.build_resolvers()`
- Handle error responses from Service Layer and Pipeline
- Serve the Vue 3 SPA via `SPAStaticFiles` mounted at `/` in `main.py` (after all API routes); `SPAStaticFiles` falls back to `index.html` for any unmatched path, enabling Vue Router client-side routing

### Service Layer (`service.py`)
- `PurlResolutionService` class with constructor injection (`storage: Storage`, `resolvers: list[Resolver]`, `settings_store: SettingsStore | None = None`)
- Orchestrate single resolution flow (`resolve_purl`): validate PURL → normalize cache key → storage lookup → URL validation (if enabled) → resolver chain (iterates resolvers, first success wins) → storage store; uses `resolver.name` property to tag stored records with the actual resolver identifier (e.g. `"purl2repo"`, `"libraries.io"`)
- URL validation: when `validate_db_urls` is enabled, verify cached URLs via HEAD + git ls-remote with optional GitHub token authentication; delete invalid URLs and fall through to resolver chain; skip validation if `resolved_at` is today; remove invalid tokens from settings automatically
- Batch resolution (`resolve_batch`): resolve multiple PURLs concurrently via `asyncio.gather()` with semaphore limit of 10; returns `dict[str, str]` of normalized PURL → repository URL for successful resolutions; uses `self._settings_store` for URL validation (no longer accepts it per-call)
- Store pre-existing references (`store_preexisting_references`): for SBOM components with `needs_enrichment=False`, extract VCS repository URL from `externalReferences` and store in database via `self._storage.store()`
- Map purl2repo `ResolutionResult` to canonical `ResolveResponse` format; tag stored records with `resolver.name` (e.g. `"purl2repo"`, `"libraries.io"`)
- Handle graceful degradation: if storage is unavailable, fall through to resolver
- Log errors from storage without breaking the response

### SBOM Enrichment Pipeline (`sbom_enrichment.py`)
- Orchestrate the complete CycloneDX SBOM enrichment workflow in a single class
- `SbomEnrichmentPipeline.__init__(storage, resolvers, settings_store)` — receives dependencies via constructor
- `SbomEnrichmentPipeline.process(sbom_data) → SbomEnrichmentResult` — executes the pipeline: validate SBOM format → collect components → deduplicate PURLs → batch resolve → store pre-existing references → enrich SBOM → build report
- Decouples HTTP layer (router) from domain orchestration logic
- Testable without FastAPI TestClient — can be instantiated with mock storage and resolvers
- Returns `SbomEnrichmentResult` dataclass with `report` and `enriched_sbom` fields

### CSV I/O Module (`csv_io.py`)
- Pure functions for CSV parsing and rendering, no HTTP or Storage dependencies
- `detect_delimiter(text) → str` — detects semicolon or comma delimiter from header line
- `parse_csv_import(text) → tuple[list[UpsertRow], list[dict]]` — parses CSV into typed UpsertRow objects and error list; handles BOM, semicolon delimiter, required column validation; when `resolver` column is absent, defaults to `"import-csv"`
- `render_csv_export(rows: list[PurlRow]) → str` — renders PurlRow objects as semicolon-delimited CSV string
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
- **`parser.py`** — `CycloneDXParser.parse(data) → dict` validates `bomFormat: CycloneDX` and `specVersion: 1.6`; raises `SbomParseError` on violation
- **`collector.py`** — `collect_components(sbom) → list[SbomComponent]` recursively walks `components[]` arrays; `SbomComponent` dataclass tracks purl, path tuple, needs_enrichment flag, and existing references; components with `vcs` or `source-distribution` external references are marked as not needing enrichment
- **`enricher.py`** — `enrich_sbom(sbom, components, resolved)` inserts `{"type": "vcs", "url": "..."}` into component `externalReferences` arrays at the correct paths; preserves existing references; increments `version` field by 1
- **`remover.py`** — `remove_unresolved_components(sbom, components, resolved) → list[dict]` removes components that need enrichment, have no subcomponents, and were not resolved; returns list of removed component dicts
- **`reporter.py`** — `build_report(components, resolved, skipped)` returns `{summary, results}`; only includes components with `needs_enrichment=True`; deduplicates by normalized PURL; removed components are excluded from `not_found` counts
- **`images_list_converter.py`** — `ImagesListConverter.convert(data) → ImagesListConversionResult` validates SBOM format via `CycloneDXParser`, checks if all top-level components are `type=container`, recursively collects container components from all nesting levels, promotes them to top-level, removes non-container components; returns `ImagesListConversionResult` with `was_transformed` flag, `images` list (with completeness flags), and the resulting `images_list` dict
- Imports `purl_utils` for PURL normalization; does not import storage or resolver modules directly

### Config Layer (`config.py`)
- Provide typed access to all runtime configuration
- Load from environment variables (set via docker-compose.yml in production, or `.env` in development)
- `Settings` class uses the `PURL2REPO_` prefix for resolver settings
- `StorageSettings` class uses the `DB_` prefix for database connection settings (`DB_URL`, etc.)
- `SbomSettings` class uses the `SBOM_` prefix for SBOM processing (`SBOM_MAX_FILE_SIZE`, default 200 MB)

### Settings Store (`settings_store.py`)
- JSON-based persistence for application settings (validate_db_urls, url_validation_timeout, github_token, librariesio_enabled, librariesio_api_key, ecosystems_enabled, ecosystems_api_key, retry_max_attempts, retry_base_cooldown_seconds, log_level, ecosystems_max_requests_per_second)
- `SettingsStore` class with `load() → AppSettings` and `save(settings)` methods
- `AppSettings` Pydantic model with field validation (url_validation_timeout: 1–60, retry_max_attempts: 1–10, retry_base_cooldown_seconds: 0.5–120)
- `ServiceTokens` dataclass for extracting API tokens from settings (extensible for future services)
- `AppSettings.service_tokens() → ServiceTokens` method
- File path from `SETTINGS_FILE` env var (default: `./data/settings.json`)
- Graceful handling: missing file → create with defaults; corrupt JSON → log warning, return defaults

### Ignore Patterns Store (`ignore_patterns_store.py`)
- JSON-based persistence for SBOM component ignore patterns (field/pattern pairs used to exclude components from enrichment)
- `IgnorePatternsStore` class with `load() → list[dict]` and `save(patterns)` methods
- File path default: `./data/sbom_components_ignore_patterns.json`
- Graceful handling: missing file → return empty list; corrupt JSON → log warning, return empty list
- Exposed via API endpoints `GET/POST /api/v1/sbom/ignore-patterns` in `routes/ignore_patterns.py`

### Web UI Layer (`frontend/`)
- Vue 3 SPA built with Vite + TypeScript, source in `frontend/src/`
- **Views** (`src/views/`): `PurlResolver.vue`, `SbomUpdater.vue`, `DatabaseAdmin.vue`, `Settings.vue`, `ImagesListConverter.vue`, `NotFound.vue`
- **Components** (`src/components/`): `AppNav.vue` (navigation bar), `FileUploadZone.vue` (drag-and-drop upload), `ModalDialog.vue` (reusable modal)
- **Composables** (`src/composables/`): `usePagination.ts` (pagination state), `useDownload.ts` (file download helper)
- **API client** (`src/api/`): typed fetch wrappers per domain — `client.ts` (base `request<T>()` + `ApiError`), `purl.ts`, `sbom.ts`, `db.ts`, `settings.ts`, `images.ts`
- **Types** (`src/types/api.ts`): TypeScript interfaces mirroring backend `schemas.py`
- **Router** (`src/router/index.ts`): Vue Router with `createWebHistory()`, 5 page routes + catch-all `/:pathMatch(.*)*` → `NotFound.vue`
- FastAPI serves the built SPA via `SPAStaticFiles` (custom `StaticFiles` subclass) mounted at `/` in `main.py`; `SPAStaticFiles` falls back to `index.html` for unmatched paths, enabling client-side routing
- Each `.vue` component uses `<style scoped>` for CSS isolation; global CSS variables in `src/assets/main.css`
- No CSS framework — design system uses CSS custom properties
- Build output: `frontend/dist/` (copied into Docker image via multi-stage build)

### Domain Layer (`purl2repo`)
- Resolve PURL strings to repository URLs with confidence/evidence
- Manage internal file-based caching (independent of the Storage Layer)
- Our code does not import or modify purl2repo directly

### Resolver Layer (`resolver/`)
- **interface.py** — `Resolver(ABC)` with `name` property (returns resolver identifier string, e.g. `"purl2repo"`, `"libraries.io"`) and `async resolve(purl) → Resolution`; `Resolution` dataclass with `purl`, `repository_url`, `repository_type`, `repository_kind`, `confidence`, `evidence`, `warnings`, `version_reference`
- **factory.py** — `build_resolvers(settings, app_settings) → list[Resolver]` centralizes resolver initialization; creates `Purl2RepoResolver` from `Settings`, conditionally adds `EcosystemsResolver` (if `ecosystems_enabled`) and `LibrariesIoResolver` (if `librariesio_enabled` and API key present); used by both `main.py` lifespan and `_rebuild_resolvers()` in the API Layer
- **purl2repo.py** — `Purl2RepoResolver(Resolver)` wrapping purl2repo; `name` returns `"purl2repo"`; async implementation uses `asyncio.to_thread()` to offload synchronous purl2repo calls to a thread pool; `UnsupportedEcosystemError` returns `Resolution(repository_url=None)` with warning (not `InvalidPurlError`); maps `InvalidPurlError` to `InvalidPurlError`; maps `ResolutionError`/`MetadataFetchError` to `UpstreamError`; extracts `version_reference.url` from ReleaseLink objects
- **librariesio.py** — `LibrariesIoResolver(Resolver)` using libraries.io REST API; `name` returns `"libraries.io"`; async implementation uses `httpx.AsyncClient` and `asyncio.sleep()` for rate limiting; optional, settings-controlled (`librariesio_enabled` + `librariesio_api_key`); maps 16 PURL types to libraries.io platforms; rate-limited (1 req/sec via `asyncio.sleep()`); graceful degradation on errors (timeout, HTTP errors, network failures all return `Resolution` with warnings); uses `httpx.AsyncClient` and `purl_utils.validate()` for PURL parsing, now with configurable retry for HTTP 429, timeout, and 5xx
- **ecosystems.py** — `EcosystemsResolver(Resolver)` using ecosyste.ms Packages API; `name` returns `"ecosyste.ms"`; async implementation uses `httpx.AsyncClient`; enabled by default via settings (`ecosystems_enabled`); no API key required (optional for higher rate limits); configurable rate limiting via `ecosystems_max_requests_per_second` app setting; URL selection prioritizes GitHub URLs; graceful degradation on errors (timeout, HTTP errors, network failures all return `Resolution` with warnings); uses `httpx.AsyncClient` and `purl_utils.validate()` for PURL parsing, now with configurable retry for HTTP 429, timeout, and 5xx
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