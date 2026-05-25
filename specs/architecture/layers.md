# Layer Architecture

## Layer Diagram

```
+-----------------------------------------------+
|  Docker Container                              |
|  +---------------------------+                 |
|  |     HTTP Client           |                 |
|  |  (Browser, curl, scripts) |                 |
|  +------------+--------------+                 |
|               |                                |
|               | HTTP JSON                      |
|               v                                |
|  +---------------------------+                 |
|  |     API Layer             |                 |
|  |  src/purl_resolver/router |                 |
|  |                           |                 |
|  |  POST /api/v1/resolve     |                 |
|  |  GET /health              |                 |
|  |  GET / (HTML page)        |                 |
|  +------------+--------------+                 |
|               |                                |
|               | Python call                    |
|               v                                |
|  +---------------------------+                 |
|  |     Domain Layer          |                 |
|  |  purl2repo library        |                 |
|  |                           |                 |
|  |  resolve(purl_str)        |                 |
|  +---------------------------+                 |
|                                                |
|  +---------------------------+                 |
|  |     Config Layer          |                 |
|  |  src/purl_resolver/config |                 |
|  |                           |                 |
|  |  Pydantic Settings        |                 |
|  |  env vars from container  |                 |
|  +---------------------------+                 |
|                                                |
|  +---------------------------+                 |
|  |     Web UI Layer          |                 |
|  |  src/purl_resolver/       |                 |
|  |  templates/index.html     |                 |
|  |                           |                 |
|  |  Jinja2 template          |                 |
|  |  Vanilla JS + fetch()     |                 |
|  +---------------------------+                 |
+-----------------------------------------------+
```

## Import Rules

- **API Layer** imports **Domain Layer** (purl2repo.resolve) — but not vice versa
- **API Layer** imports **Config Layer** (settings)
- **Domain Layer** is the external purl2repo library — our code does not modify it
- **Config Layer** is a standalone module with no internal project imports
- **Web UI Layer** is served by the API Layer and communicates via HTTP (fetch → API Layer)
- Tests (`tests/`) import only `main:app` and FastAPI TestClient

## Layer Responsibilities

### API Layer (`router.py`)
- Define HTTP endpoints (routes, methods, status codes)
- Validate request input via Pydantic schemas
- Call purl2repo.resolve() and map results to canonical response format
- Handle error mapping: purl2repo exceptions → HTTP error responses
- Serve Jinja2 template for the web UI

### Domain Layer (`purl2repo`)
- Resolve PURL strings to repository URLs with confidence/evidence
- Manage internal file-based caching
- The canonical response format is independent of purl2repo's internal structure

### Config Layer (`config.py`)
- Provide typed access to all runtime configuration
- Load from environment variables (set via docker-compose.yml in production, or `.env` in development)
- All env vars use the `PURL2REPO_` prefix

### Web UI Layer (`templates/index.html`)
- Provide form-based PURL input
- Fetch resolution results via `POST /api/v1/resolve`
- Display results in a readable card format with expandable details

## Anti-Patterns

- Importing purl2repo exception classes in the Web UI layer
- Bypassing the API Layer — direct calls to purl2repo from the test client (tests use HTTP through TestClient)
- Storing state in the API Layer (the service is stateless by design)
- Changing the canonical response format without updating contracts/api-contract.md
- Running outside Docker for production deployment (development-only bare uvicorn)
