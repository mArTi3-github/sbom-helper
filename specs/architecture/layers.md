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
|                | HTTP JSON                         |
|                v                                   |
|  +-----------------------------+                   |
|  |     API Layer               |                   |
|  |  src/purl_resolver/router   |                   |
|  |                             |                   |
|  |  POST /api/v1/resolve      |                   |
|  |  GET /health               |                   |
|  |  GET / (HTML page)         |                   |
|  +-------------+---------------+                   |
|                |                                   |
|                | Python call                       |
|                v                                   |
|  +-----------------------------+                   |
|  |     Service Layer           |                   |
|  |  src/purl_resolver/service  |                   |
|  |                             |                   |
|  |  Orchestrates:              |                   |
|  |  purl_utils.validate() →    |                   |
|  |  purl_utils.normalize() →   |                   |
|  |  storage.lookup() →         |                   |
|  |  resolver.resolve() →       |                   |
|  |  storage.store()            |                   |
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
|  +----------+          |                           |
|       |                | asyncpg                   |
|       v                v                           |
|  +-----------------------------+                   |
|  |   Resolver Layer            |                   |
|  |  resolver/                  |                   |
|  |                             |                   |
|  |  Resolver (ABC)             |                   |
|  |  Resolution dataclass       |                   |
|  |  InvalidPurlError           |                   |
|  |  UpstreamError              |                   |
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
|  +----------+                                      |
|  |PostgreSQL|                                      |
|  +----------+                                      |
|                                                    |
|  +-----------------------------+                   |
|  |     Config Layer            |                   |
|  |  src/purl_resolver/config   |                   |
|  |                             |                   |
|  |  Pydantic Settings          |                   |
|  |  PURL2REPO_* prefix         |                   |
|  |  DB_* prefix                |                   |
|  +-----------------------------+                   |
|                                                    |
|  +-----------------------------+                   |
|  |     Web UI Layer            |                   |
|  |  src/purl_resolver/         |                   |
|  |  templates/index.html       |                   |
|  |                             |                   |
|  |  Jinja2 template            |                   |
|  |  Vanilla JS + fetch()       |                   |
|  +-----------------------------+                   |
+---------------------------------------------------+
```

## Import Rules

- **API Layer** imports **Service Layer** (`service.py`) — but not vice versa
- **API Layer** imports **Config Layer** (settings)
- **Service Layer** imports **PURL Utils Layer** (`purl_utils/`), **Storage Layer** (`storage/interface.py`), and **Resolver Layer** (`resolver/interface.py`)
- **PURL Utils Layer** is a standalone module — imports only `packageurl-python`, no internal project imports
- **Storage Layer** is a standalone module — imports only asyncpg, no internal project imports outside `storage/`
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
- Delegate resolution to Service Layer (`service.resolve_purl()`)
- Handle error responses from Service Layer
- Serve Jinja2 template for the web UI

### Service Layer (`service.py`)
- Orchestrate resolution flow: validate PURL → normalize cache key → storage lookup → resolver call → storage store
- Map purl2repo `ResolutionResult` to canonical `ResolveResponse` format
- Handle graceful degradation: if storage is unavailable, fall through to resolver
- Log errors from storage without breaking the response

### PURL Utils Layer (`purl_utils/`)
- **`__init__.py`** — `validate(purl) → PurlComponents` (raises `PurlValidationError`), `normalize(components) → str`
- Validate PURL format using the official `packageurl-python` library
- Normalize PURL to `scheme:type/namespace/name` form (namespace only if present)
- `PurlValidationError` — resolver-agnostic exception for invalid PURLs
- Has zero dependency on any resolver implementation

### Storage Layer (`storage/`)
- **interface.py** — Abstract `Storage` ABC with `lookup(purl) → ResolveResponse | None` and `store(result) → None`
- **postgres.py** — `PostgresCache` implementation via asyncpg; handles JSONB encoding/decoding; creates table on startup
- **inmemory.py** — `InMemoryCache` implementation (dict-based) for tests and fallback when PostgreSQL is unavailable

### Domain Layer (`purl2repo`)
- Resolve PURL strings to repository URLs with confidence/evidence
- Manage internal file-based caching (independent of the Storage Layer)
- Our code does not import or modify purl2repo directly

### Resolver Layer (`resolver/`)
- **interface.py** — `Resolver(ABC)` with `resolve(purl) → Resolution`; `Resolution` dataclass with `purl`, `repository_url`, `repository_type`, `repository_kind`, `confidence`, `evidence`, `warnings`, `version_reference`
- **purl2repo.py** — `Purl2RepoResolver(Resolver)` wrapping purl2repo; maps `InvalidPurlError`/`UnsupportedEcosystemError` to `InvalidPurlError`; maps `ResolutionError`/`MetadataFetchError` to `UpstreamError`; extracts `version_reference.url` from ReleaseLink objects
- Exceptions: `ResolverError`, `InvalidPurlError`, `UpstreamError`

### Config Layer (`config.py`)
- Provide typed access to all runtime configuration
- Load from environment variables (set via docker-compose.yml in production, or `.env` in development)
- `Settings` class uses the `PURL2REPO_` prefix for resolver settings
- `StorageSettings` class uses the `DB_` prefix for database connection settings (`DB_URL`, etc.)

### Web UI Layer (`templates/index.html`)
- Provide form-based PURL input
- Fetch resolution results via `POST /api/v1/resolve`
- Display results in a readable card format with expandable details

## Anti-Patterns

- Importing purl2repo exception classes in the Web UI layer
- Bypassing the API Layer — direct calls to purl2repo from the test client
- Calling purl2repo directly from the API Layer (must go through Service Layer)
- Storing state in the API Layer (the service is stateless by design)
- Changing the canonical response format without updating contracts/api-contract.md
- Running outside Docker for production deployment (development-only bare uvicorn)