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
|  |  storage.lookup() →         |                   |
|  |  resolver.resolve() →       |                   |
|  |  storage.store()            |                   |
|  +----+--------------------+---+                   |
|       |                    |                       |
|       | Python call        | Python call           |
|       v                    v                       |
|  +----------+     +------------------+             |
|  | Storage  |     |  Domain Layer    |             |
|  | Layer    |     |  purl2repo       |             |
|  |          |     |                  |             |
|  | lookup() |     |  resolve(        |             |
|  | store()  |     |   purl_str)      |             |
|  +----+-----+     +------------------+             |
|       |                                            |
|       | asyncpg                                    |
|       v                                            |
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
- **Service Layer** imports **Storage Layer** (`storage/interface.py`) and **Domain Layer** (`purl2repo`)
- **Storage Layer** is a standalone module — imports only asyncpg, no internal project imports outside `storage/`
- **Service Layer** imports **Config Layer** (settings)
- **Domain Layer** is the external purl2repo library — our code does not modify it
- **Config Layer** is a standalone module with no internal project imports
- **Web UI Layer** is served by the API Layer and communicates via HTTP (fetch → API Layer)
- Tests (`tests/`) import `main:app` and FastAPI TestClient; unit tests for storage/service import them directly

## Layer Responsibilities

### API Layer (`router.py`)
- Define HTTP endpoints (routes, methods, status codes)
- Validate request input via Pydantic schemas
- Delegate resolution to Service Layer (`service.resolve_purl()`)
- Handle error responses from Service Layer
- Serve Jinja2 template for the web UI

### Service Layer (`service.py`)
- Orchestrate resolution flow: storage lookup → resolver call → storage store
- Map purl2repo `ResolutionResult` to canonical `ResolveResponse` format
- Handle graceful degradation: if storage is unavailable, fall through to resolver
- Log errors from storage without breaking the response

### Storage Layer (`storage/`)
- **interface.py** — Abstract `Storage` protocol with `lookup(purl) → ResolveResponse | None` and `store(result) → None`
- **postgres.py** — `PostgresCache` implementation via asyncpg; handles JSONB encoding/decoding; creates table on startup
- **inmemory.py** — `InMemoryCache` implementation (dict-based) for tests and fallback when PostgreSQL is unavailable

### Domain Layer (`purl2repo`)
- Resolve PURL strings to repository URLs with confidence/evidence
- Manage internal file-based caching (independent of the Storage Layer)
- The canonical response format is independent of purl2repo's internal structure

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