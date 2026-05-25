## 1. Dependencies and Configuration

- [x] 1.1 Add `asyncpg` to `pyproject.toml` dependencies
- [x] 1.2 Add `StorageSettings` class to `config.py` with `DB_` prefix and `url` field
- [x] 1.3 Add `DB_URL` environment variable to `docker-compose.yml` app service

## 2. Storage Layer

- [x] 2.1 Create `storage/__init__.py`
- [x] 2.2 Create `storage/interface.py` with abstract protocol: `lookup(purl) → ResolveResponse | None` and `store(result) → None`
- [x] 2.3 Create `storage/postgres.py` with `PostgresCache` class implementing the protocol via asyncpg
- [x] 2.4 Create `storage/schema.sql` with `CREATE TABLE resolved_purls` DDL (purl TEXT PK, repository_url TEXT NOT NULL, repository_type TEXT, repository_kind TEXT, confidence TEXT, evidence JSONB DEFAULT '[]', warnings JSONB DEFAULT '[]', version_reference TEXT, resolver TEXT NOT NULL DEFAULT 'purl2repo', resolved_at TIMESTAMPTZ NOT NULL DEFAULT NOW())
- [x] 2.5 Create `storage/inmemory.py` with `InMemoryCache` class (dict-based, for tests)

## 3. Service Layer

- [x] 3.1 Create `service.py` with `resolve_purl(purl, storage, settings) → ResolveResponse` function implementing the orchestration flow: lookup → resolver → store
- [x] 3.2 Integrate graceful degradation: wrap storage calls in try/except, log errors, fall through to resolver

## 4. Application Wiring

- [x] 4.1 Add FastAPI `lifespan` to `main.py`: create asyncpg pool on startup, close on shutdown, store in `app.state`
- [x] 4.2 Update `router.py`: replace direct `purl2repo.resolve()` call with `service.resolve_purl()`, inject storage from `app.state`
- [x] 4.3 Implement `create_table_if_not_exists` in `postgres.py` and call it during pool initialization

## 5. Docker Compose

- [x] 5.1 Add `db` service (postgres:16-alpine) to `docker-compose.yml` with healthcheck, volume, env vars
- [x] 5.2 Update `app` service with `depends_on: db: condition: service_healthy`
- [x] 5.3 Add `pgdata` named volume to `docker-compose.yml`

## 6. Testing

- [x] 6.1 Write unit tests for `service.py` using `InMemoryCache`: test cache hit, cache miss → resolve → store, DB unavailable → fall through
- [x] 6.2 Write unit tests for `InMemoryCache`: test lookup, store, idempotent store
- [x] 6.3 Update existing API integration tests (`test_api.py`) to inject `InMemoryCache` and verify that repeat requests return cached results
- [x] 6.4 Write one smoke integration test with real PostgreSQL (via testcontainers or local container): verify that table is created, result is stored and retrievable