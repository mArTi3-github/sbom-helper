# Dynamic Resolver Filter — Design Spec

## Description

Replace the hardcoded resolver filter dropdown in the Database Admin page with a dynamically populated list from the database. Changes span the backend (index, storage, route) and frontend (API client, store, component).

## Key Files

- `src/purl_resolver/storage/postgres.py` — index creation in `create_pool()`, new `list_resolvers()` method
- `src/purl_resolver/storage/interface.py` — new abstract `list_resolvers()` on `Storage`
- `src/purl_resolver/storage/inmemory.py` — InMemoryCache implementation of `list_resolvers()`
- `src/purl_resolver/db_admin_service.py` — new `list_resolvers()` service method
- `src/purl_resolver/routes/db_admin.py` — new `GET /api/v1/db/resolvers` endpoint
- `frontend/src/api/db.ts` — new `listResolvers()` function
- `frontend/src/stores/useDbAdminStore.ts` — `resolvers` state + `fetchResolvers()` action
- `frontend/src/components/db/DbFilterPanel.vue` — dynamic `<option>` rendering

## Approach

`SELECT DISTINCT resolver` via a dedicated endpoint, backed by an index on the `resolver` column. With an index-only scan, the query returns in <1ms regardless of table size (cardinality of distinct values is tiny).

## Changes

### Index on Startup

In `create_pool()` (`postgres.py:206`), immediately after `_load_schema()`:

```python
await conn.execute(
    "CREATE INDEX IF NOT EXISTS idx_resolved_purls_resolver ON resolved_purls (resolver)"
)
```

Keeps DDL initialisation in one place, follows the existing `CREATE TABLE IF NOT EXISTS` pattern.

### Storage Interface

New abstract method on `Storage`:

```python
@abstractmethod
async def list_resolvers(self) -> list[str]: ...
```

### PostgresCache Implementation

```python
async def list_resolvers(self) -> list[str]:
    async with self._pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT DISTINCT resolver FROM resolved_purls ORDER BY resolver"
        )
        return [r["resolver"] for r in rows]
```

### InMemoryCache Implementation

Returns distinct resolver values from the in-memory `_store`.

### Service Layer

New method on `DbAdminService`:

```python
async def list_resolvers(self) -> list[str]:
    return await self._storage.list_resolvers()
```

### API Route

```python
@router.get("/api/v1/db/resolvers")
async def list_resolvers_endpoint(request: Request):
    service: DbAdminService = request.app.state.db_admin_service
    resolvers = await service.list_resolvers()
    return JSONResponse(status_code=200, content=resolvers)
```

Response: flat JSON array of strings, e.g. `["ecosyste.ms", "import-csv", "libraries.io", "purl2repo"]`.

### Frontend — API Client

```typescript
export function listResolvers(): Promise<string[]> {
  return apiFetch<string[]>('/api/v1/db/resolvers')
}
```

### Frontend — Store

- New `resolvers` ref (`string[]`, initial `[]`)
- New `fetchResolvers()` action — calls `listResolvers()` and sets the ref
- Expose both in the store's return

### Frontend — Filter Panel

- Call `store.fetchResolvers()` in `onMounted()`
- Replace hardcoded `<option>` with `v-for` over `store.resolvers`
- On fetch failure: dropdown shows only «Any» (graceful degradation)

## Constraints

- No caching layer (premature for 6 values)
- No separate migration mechanism — index creation piggybacks on existing startup DDL
