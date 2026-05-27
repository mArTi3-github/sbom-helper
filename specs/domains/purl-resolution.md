# PURL Resolution

## Description

Core capability of the system. Accepts a single Package URL (PURL) string and returns the corresponding source code repository URL with confidence, evidence, and metadata. Uses a two-tier strategy: first checks PostgreSQL for a cached result, and on cache miss delegates resolution to the purl2repo library, storing successful results for future lookups.

## Key Files

- `src/purl_resolver/router.py` — API endpoint handler that calls the Service Layer
- `src/purl_resolver/service.py` — Orchestration: validation → normalization → storage lookup → resolver → storage store
- `src/purl_resolver/purl_utils/` — PURL validation and normalization layer
- `src/purl_resolver/resolver/` — Resolver abstraction (ABC, Resolution, exceptions) and purl2repo wrapper
- `src/purl_resolver/schemas.py` — Request and response data models
- `src/purl_resolver/storage/` — Storage Layer (interface, postgres, inmemory implementations)
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
  |                          |                          | (если не найдено)      |                |                |
  |                          |                          | resolve(original_purl) |                |                |
  |                          |                          |------------------------------------------------------>|
  |                          |                          |                        |                |                |
  |                          |                          | ResolutionResult       |                |                |
  |                          |                          |<------------------------------------------------------|
  |                          |                          |                        |                |                |
  |                          |                          | (если success)         |                |                |
  |                          |                          | storage.store(result)  |                |                |
  |                          |                          |--------------------------------------->|                |
  |                          |                          |                        |                |                |
  |                          | 200 {normalized purl}    |                        |                |                |
  |<-------------------------|--------------------------|                        |                |                |
```

## Invariants

- Every valid PURL returns HTTP 200 (with `repository_url: null` if unresolved)
- Invalid PURL format is caught at the application level (purl_utils) before any resolver or storage call — HTTP 400
- Unsupported ecosystems still raise HTTP 400 (from purl2repo after format validation passes)
- Upstream errors (registry timeout, network failure) always return HTTP 502
- The response format is canonical — it does not expose purl2repo's internal structure
- Empty purl strings are rejected at the Pydantic validation level (HTTP 422)
- `version_reference` is a URL string (not the purl2repo ReleaseLink object)
- **Normalized cache keys**: storage uses `scheme:type/namespace/name` form — version/qualifiers/subpath are stripped
- **Resolver receives original PURL**: the full string (with version, qualifiers, subpath) is passed unmodified to resolvers
- **DB cache hit**: if a result is found in PostgreSQL, the resolver is NOT called
- **Only successful results are stored**: `repository_url = null` results are never persisted
- **Graceful degradation**: if PostgreSQL is unavailable, the resolver still works (without caching)
- **Store is best-effort**: a failure to store does not break the response to the client

## Configuration

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