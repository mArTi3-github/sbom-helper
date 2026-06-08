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
|  |  src/purl_resolver/router   |                   |
|  |                             |                   |
|  |  POST /api/v1/resolve      |                   |
|  |  POST /api/v1/resolve/sbom |                   |
|  |  GET /health               |                   |
|  |  GET / (HTML page)         |                   |
|  |  GET /sbom-updater         |                   |
|  |  GET /db-admin             |                   |
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
|  |  Service Layer           |                   |
|  |  src/purl_resolver/service  |                   |
|  |                             |                   |
|  |  resolve_purl()             |                   |
|  |  resolve_batch()            |                   |
|  |  process_sbom()             |                   |
|  |  store_preexisting_references() |               |
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
|  |  reporter.py — result table|                   |
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
|  |  src/purl_resolver/         |                   |
|  |  templates/index.html       |                   |
|  |  templates/sbom.html        |                   |
|  |  templates/settings.html    |                   |
|  |                             |                   |
|  |  Jinja2 templates           |                   |
|  |  Vanilla JS + fetch()       |                   |
|  +-----------------------------+                   |
+---------------------------------------------------+
```

## Import Rules

- **API Layer** imports **Service Layer** (`service.py`) and **SBOM Enrichment Pipeline** (`sbom_enrichment.py`) — but not vice versa
- **API Layer** imports **csv_io** module for CSV parsing/rendering
- **API Layer** imports **Config Layer** (settings)
- **API Layer** imports **Resolver Layer** for `_rebuild_resolvers()` helper (uses `resolver.factory.build_resolvers()` to reconstruct resolver list on settings change)
- **Service Layer** imports **PURL Utils Layer** (`purl_utils/`), **Storage Layer** (`storage/interface.py`), **Resolver Layer** (`resolver/interface.py`), **URL Validator** (`url_validator.py`), and **SBOM Module** (`sbom/`); exports `store_preexisting_references` for SBOM endpoint use; accepts optional `settings_store` parameter for URL validation; accepts optional `resolver` parameter to tag stored records with their origin (e.g. `"import-sbom"`, `"import-csv"`)
- **SBOM Enrichment Pipeline** (`sbom_enrichment.py`) imports **Service Layer** (`service.py`), **SBOM Module** (`sbom/`), **PURL Utils Layer** (`purl_utils/`), **Storage Layer** (`storage/interface.py`), and **Resolver Layer** (`resolver/interface.py`); receives dependencies via constructor injection
- **SBOM Module** imports **PURL Utils Layer** for normalization; does not import Storage or Resolver directly
- **PURL Utils Layer** is a standalone module — imports only `packageurl-python`, no internal project imports
- **Storage Layer** is a standalone module — imports only asyncpg, no internal project imports outside `storage/`; exports `UpsertRow` dataclass for typed batch insert
- **Resolver Layer** (`resolver/`) defines the `Resolver` ABC (with `name` property and `resolve` method), `Resolution` dataclass, resolver-specific exceptions (`InvalidPurlError`, `UpstreamError`), and a `factory.py` module with `build_resolvers(settings, app_settings) → list[Resolver]` that centralizes resolver initialization. `Purl2RepoResolver` wraps the purl2repo library. `LibrariesIoResolver` wraps the libraries.io REST API with rate limiting and graceful degradation.
- **Resolver Layer** imports purl2repo, httpx, and `purl_utils`; internal project code does NOT import purl2repo directly
- **PURL Utils Layer** does NOT depend on any resolver — it is resolver-agnostic
- **Config Layer** is a standalone module with no internal project imports
- **Web UI Layer** is served by the API Layer and communicates via HTTP (fetch → API Layer)
- Tests (`tests/`) import `main:app` and FastAPI TestClient; unit tests for storage/service/purl_utils import them directly

## Layer Responsibilities

### API Layer (`router.py`)
- Define HTTP endpoints (routes, methods, status codes)
- Validate request input via Pydantic schemas
- Delegate single PURL resolution to Service Layer (`service.resolve_purl()`)
- Delegate SBOM enrichment to `SbomEnrichmentPipeline` (`sbom_enrichment.py`) — handles parsing, collection, deduplication, batch resolution, and enrichment
- Delegate CSV parsing/rendering to csv_io module (`csv_io.parse_csv_import()`, `csv_io.render_csv_export()`)
- Delegate DB admin operations to Storage Layer (`storage.list_purls()`, `storage.update_purl()`, etc.)
- Manage application settings via Settings Store (`GET/PATCH /api/v1/settings`); validates libraries.io API key via async `validate_librariesio_key()`; rebuilds resolver list on settings change via `_rebuild_resolvers()` using `resolver.factory.build_resolvers()`
- Handle error responses from Service Layer and Pipeline
- Serve Jinja2 templates for the web UI (`index.html`, `sbom.html`, `db-admin.html`, `settings.html`)

### Service Layer (`service.py`)
- Orchestrate single resolution flow (`resolve_purl`): validate PURL → normalize cache key → storage lookup → URL validation (if enabled) → resolver chain (iterates resolvers, first success wins) → storage store; uses `resolver.name` property to tag stored records with the actual resolver identifier (e.g. `"purl2repo"`, `"libraries.io"`)
- URL validation: when `validate_db_urls` is enabled, verify cached URLs via HEAD + git ls-remote with optional GitHub token authentication; delete invalid URLs and fall through to resolver chain; skip validation if `resolved_at` is today; remove invalid tokens from settings automatically
- Batch resolution (`resolve_batch`): resolve multiple PURLs concurrently via `asyncio.gather()` with semaphore limit of 10; returns `dict[str, str]` of normalized PURL → repository URL for successful resolutions; accepts optional `settings_store` for URL validation
- SBOM enrichment flow (`process_sbom`): accept parsed SBOM dict + components + resolved map → call `enricher.enrich_sbom()` → call `reporter.build_report()` → return combined report
- Store pre-existing references (`store_preexisting_references`): for SBOM components with `needs_enrichment=False`, extract VCS repository URL from `externalReferences` and store in database via `storage.store()`
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
- **`reporter.py`** — `build_report(components, resolved, skipped)` returns `{summary, results}`; only includes components with `needs_enrichment=True`; deduplicates by normalized PURL
- Imports `purl_utils` for PURL normalization; does not import storage or resolver modules directly

### Config Layer (`config.py`)
- Provide typed access to all runtime configuration
- Load from environment variables (set via docker-compose.yml in production, or `.env` in development)
- `Settings` class uses the `PURL2REPO_` prefix for resolver settings
- `StorageSettings` class uses the `DB_` prefix for database connection settings (`DB_URL`, etc.)
- `SbomSettings` class uses the `SBOM_` prefix for SBOM processing (`SBOM_MAX_FILE_SIZE`, default 200 MB)

### Settings Store (`settings_store.py`)
- JSON-based persistence for application settings (validate_db_urls, url_validation_timeout, github_token, librariesio_enabled, librariesio_api_key, ecosystems_enabled, ecosystems_api_key)
- `SettingsStore` class with `load() → AppSettings` and `save(settings)` methods
- `AppSettings` Pydantic model with field validation (url_validation_timeout: 1–60)
- `ServiceTokens` dataclass for extracting API tokens from settings (extensible for future services)
- `AppSettings.service_tokens() → ServiceTokens` method
- File path from `SETTINGS_FILE` env var (default: `./data/settings.json`)
- Graceful handling: missing file → create with defaults; corrupt JSON → log warning, return defaults

### Web UI Layer (`templates/`)
- `index.html` — form-based PURL input; fetch resolution results via `POST /api/v1/resolve`; display results in a readable card format with expandable details; navigation link to SBOM-updater, DB-admin, and Settings pages
- `sbom.html` — file upload form (drag-and-drop) for CycloneDX JSON; fetch results via `POST /api/v1/resolve/sbom` (multipart); display summary cards + results table; "Скачать обогащённый SBOM" triggers JSON file download; navigation link to PURL resolver, DB-admin, and Settings pages
- `db-admin.html` — database administration page: filterable table with pagination, inline editing of PURL and repository_url, CSV import/export (semicolon delimiter, BOM handling), bulk delete; column visibility controls; navigation link to PURL resolver, SBOM-updater, and Settings pages
- `settings.html` — settings page: URL validation toggle, timeout configuration, GitHub token management (set/clear), Libraries.io resolver card (enable toggle, API key input, status badge, clear button); loads settings via `GET /api/v1/settings`, saves via `PATCH /api/v1/settings`; navigation link to all other pages

### Domain Layer (`purl2repo`)
- Resolve PURL strings to repository URLs with confidence/evidence
- Manage internal file-based caching (independent of the Storage Layer)
- Our code does not import or modify purl2repo directly

### Resolver Layer (`resolver/`)
- **interface.py** — `Resolver(ABC)` with `name` property (returns resolver identifier string, e.g. `"purl2repo"`, `"libraries.io"`) and `async resolve(purl) → Resolution`; `Resolution` dataclass with `purl`, `repository_url`, `repository_type`, `repository_kind`, `confidence`, `evidence`, `warnings`, `version_reference`
- **factory.py** — `build_resolvers(settings, app_settings) → list[Resolver]` centralizes resolver initialization; creates `Purl2RepoResolver` from `Settings`, conditionally adds `EcosystemsResolver` (if `ecosystems_enabled`) and `LibrariesIoResolver` (if `librariesio_enabled` and API key present); used by both `main.py` lifespan and `_rebuild_resolvers()` in the API Layer
- **purl2repo.py** — `Purl2RepoResolver(Resolver)` wrapping purl2repo; `name` returns `"purl2repo"`; async implementation uses `asyncio.to_thread()` to offload synchronous purl2repo calls to a thread pool; `UnsupportedEcosystemError` returns `Resolution(repository_url=None)` with warning (not `InvalidPurlError`); maps `InvalidPurlError` to `InvalidPurlError`; maps `ResolutionError`/`MetadataFetchError` to `UpstreamError`; extracts `version_reference.url` from ReleaseLink objects
- **librariesio.py** — `LibrariesIoResolver(Resolver)` using libraries.io REST API; `name` returns `"libraries.io"`; async implementation uses `httpx.AsyncClient` and `asyncio.sleep()` for rate limiting; optional, settings-controlled (`librariesio_enabled` + `librariesio_api_key`); maps 16 PURL types to libraries.io platforms; rate-limited (1 req/sec via `asyncio.sleep()`); graceful degradation on errors (timeout, HTTP errors, network failures all return `Resolution` with warnings); uses `httpx.AsyncClient` and `purl_utils.validate()` for PURL parsing
- **ecosystems.py** — `EcosystemsResolver(Resolver)` using ecosyste.ms Packages API; `name` returns `"ecosyste.ms"`; async implementation uses `httpx.AsyncClient`; enabled by default via settings (`ecosystems_enabled`); no API key required (optional for higher rate limits); URL selection prioritizes GitHub URLs; graceful degradation on errors (timeout, HTTP errors, network failures all return `Resolution` with warnings); uses `httpx.AsyncClient` and `purl_utils.validate()` for PURL parsing
- Exceptions: `ResolverError`, `InvalidPurlError`, `UpstreamError`

## Anti-Patterns

- Importing purl2repo exception classes in the Web UI layer
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
- **dev stage**: editable install (`pip install -e .`), `--reload` for hot-reload development
- **prod stage**: non-editable install, `app` user (UID 1001), HEALTHCHECK configured

### Docker Compose
- `docker-compose.yml` defines app service with `${VAR:-default}` pattern for deployment-specific overrides
- `docker-compose.override.yml` (auto-merged by Compose) mounts `./src` as a volume for dev hot-reload
- Environment variables are the sole configuration mechanism (twelve-factor app). No `.env` is baked into the image.

### Security
- Production container runs as non-root user (UID 1001)
- HEALTHCHECK monitors service availability — container marked unhealthy on repeated failure

### Build Context
`.dockerignore` excludes `.git`, `.venv`, `__pycache__`, `.pytest_cache`, `.env` files to keep build context minimal. `pyproject.toml` and `src/` are copied separately to optimize Docker layer caching.