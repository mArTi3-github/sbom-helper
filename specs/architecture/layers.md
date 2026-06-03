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
|  |  Purl2RepoResolver          |                   |
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
|  |  HEAD + git ls-remote       |                   |
|  |  Rate limit mitigation      |                   |
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

- **API Layer** imports **Service Layer** (`service.py`) — but not vice versa
- **API Layer** imports **csv_io** module for CSV parsing/rendering
- **API Layer** imports **Config Layer** (settings)
- **Service Layer** imports **PURL Utils Layer** (`purl_utils/`), **Storage Layer** (`storage/interface.py`), **Resolver Layer** (`resolver/interface.py`), **URL Validator** (`url_validator.py`), and **SBOM Module** (`sbom/`); exports `store_preexisting_references` for SBOM endpoint use; accepts optional `settings_store` parameter for URL validation
- **SBOM Module** imports **PURL Utils Layer** for normalization; does not import Storage or Resolver directly
- **PURL Utils Layer** is a standalone module — imports only `packageurl-python`, no internal project imports
- **Storage Layer** is a standalone module — imports only asyncpg, no internal project imports outside `storage/`; exports `UpsertRow` dataclass for typed batch insert
- **Resolver Layer** (`resolver/`) defines the `Resolver` ABC, `Resolution` dataclass, and resolver-specific exceptions (`InvalidPurlError`, `UpstreamError`). `Purl2RepoResolver` wraps the purl2repo library.
- **Resolver Layer** imports purl2repo; internal project code does NOT import purl2repo directly
- **PURL Utils Layer** does NOT depend on any resolver — it is resolver-agnostic
- **Config Layer** is a standalone module with no internal project imports
- **Web UI Layer** is served by the API Layer and communicates via HTTP (fetch → API Layer)
- Tests (`tests/`) import `main:app` and FastAPI TestClient; unit tests for storage/service/purl_utils import them directly

## Layer Responsibilities

### API Layer (`router.py`)
- Define HTTP endpoints (routes, methods, status codes)
- Validate request input via Pydantic schemas
- Delegate single PURL resolution to Service Layer (`service.resolve_purl()`)
- Delegate SBOM enrichment to Service Layer (`service.resolve_batch()` + `service.process_sbom()`)
- Delegate CSV parsing/rendering to csv_io module (`csv_io.parse_csv_import()`, `csv_io.render_csv_export()`)
- Delegate DB admin operations to Storage Layer (`storage.list_purls()`, `storage.update_purl()`, etc.)
- Manage application settings via Settings Store (`GET/PATCH /api/v1/settings`)
- Handle error responses from Service Layer
- Serve Jinja2 templates for the web UI (`index.html`, `sbom.html`, `db-admin.html`, `settings.html`)

### Service Layer (`service.py`)
- Orchestrate single resolution flow (`resolve_purl`): validate PURL → normalize cache key → storage lookup → URL validation (if enabled) → resolver call → storage store
- URL validation: when `validate_db_urls` is enabled, verify cached URLs via HEAD + git ls-remote; delete invalid URLs and fall through to resolver chain; skip validation if `resolved_at` is today
- Batch resolution (`resolve_batch`): resolve multiple PURLs concurrently via `asyncio.gather()` with semaphore limit of 10; returns `dict[str, str]` of normalized PURL → repository URL for successful resolutions; accepts optional `settings_store` for URL validation
- SBOM enrichment flow (`process_sbom`): accept parsed SBOM dict + components + resolved map → call `enricher.enrich_sbom()` → call `reporter.build_report()` → return combined report
- Store pre-existing references (`store_preexisting_references`): for SBOM components with `needs_enrichment=False`, extract VCS repository URL from `externalReferences` and store in database via `storage.store()`
- Map purl2repo `ResolutionResult` to canonical `ResolveResponse` format
- Handle graceful degradation: if storage is unavailable, fall through to resolver
- Log errors from storage without breaking the response

### CSV I/O Module (`csv_io.py`)
- Pure functions for CSV parsing and rendering, no HTTP or Storage dependencies
- `detect_delimiter(text) → str` — detects semicolon or comma delimiter from header line
- `parse_csv_import(text) → tuple[list[UpsertRow], list[dict]]` — parses CSV into typed UpsertRow objects and error list; handles BOM, semicolon delimiter, required column validation
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
- JSON-based persistence for application settings (validate_db_urls, url_validation_timeout)
- `SettingsStore` class with `load() → AppSettings` and `save(settings)` methods
- `AppSettings` Pydantic model with field validation (url_validation_timeout: 1–60)
- File path from `SETTINGS_FILE` env var (default: `./data/settings.json`)
- Graceful handling: missing file → create with defaults; corrupt JSON → log warning, return defaults

### Web UI Layer (`templates/`)
- `index.html` — form-based PURL input; fetch resolution results via `POST /api/v1/resolve`; display results in a readable card format with expandable details; navigation link to SBOM-updater, DB-admin, and Settings pages
- `sbom.html` — file upload form (drag-and-drop) for CycloneDX JSON; fetch results via `POST /api/v1/resolve/sbom` (multipart); display summary cards + results table; "Скачать обогащённый SBOM" triggers JSON file download; navigation link to PURL resolver, DB-admin, and Settings pages
- `db-admin.html` — database administration page: filterable table with pagination, inline editing of PURL and repository_url, CSV import/export (semicolon delimiter, BOM handling), bulk delete; column visibility controls; navigation link to PURL resolver, SBOM-updater, and Settings pages
- `settings.html` — settings page: URL validation toggle, timeout configuration; loads settings via `GET /api/v1/settings`, saves via `PATCH /api/v1/settings`; navigation link to all other pages

### Domain Layer (`purl2repo`)
- Resolve PURL strings to repository URLs with confidence/evidence
- Manage internal file-based caching (independent of the Storage Layer)
- Our code does not import or modify purl2repo directly

### Resolver Layer (`resolver/`)
- **interface.py** — `Resolver(ABC)` with `resolve(purl) → Resolution`; `Resolution` dataclass with `purl`, `repository_url`, `repository_type`, `repository_kind`, `confidence`, `evidence`, `warnings`, `version_reference`
- **purl2repo.py** — `Purl2RepoResolver(Resolver)` wrapping purl2repo; `UnsupportedEcosystemError` returns `Resolution(repository_url=None)` with warning (not `InvalidPurlError`); maps `InvalidPurlError` to `InvalidPurlError`; maps `ResolutionError`/`MetadataFetchError` to `UpstreamError`; extracts `version_reference.url` from ReleaseLink objects
- Exceptions: `ResolverError`, `InvalidPurlError`, `UpstreamError`

## Anti-Patterns

- Importing purl2repo exception classes in the Web UI layer
- Bypassing the API Layer — direct calls to purl2repo from the test client
- Calling purl2repo directly from the API Layer (must go through Service Layer)
- Bypassing Service Layer for SBOM enrichment orchestration — all enrichment logic lives in `service.py`, not `router.py`
- Storing state in the API Layer (the service is stateless by design)
- Changing the canonical response format without updating contracts/api-contract.md
- Running outside Docker for production deployment (development-only bare uvicorn)