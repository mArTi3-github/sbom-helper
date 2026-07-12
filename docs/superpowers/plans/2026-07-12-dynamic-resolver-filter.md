# Dynamic Resolver Filter — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hardcoded resolver filter dropdown (`purl2repo` only) with a dynamic list fetched from the database.

**Architecture:** Backend exposes `GET /api/v1/db/resolvers` returning `SELECT DISTINCT resolver` from `resolved_purls`. A new B-tree index on the `resolver` column guarantees <1ms queries at 7M rows. Frontend loads this list on mount and renders `<option>` elements via `v-for`.

**Tech Stack:** FastAPI (Python), asyncpg, Vue 3 (Pinia), Vitest

## Global Constraints

- The table has ~7M rows on prod; all DB queries must be index-backed where possible
- All DDL (index creation) runs in `create_pool()`, alongside the existing `CREATE TABLE IF NOT EXISTS`
- The new API endpoint must use only parameterised queries (no string interpolation of user data) — though `SELECT DISTINCT resolver` has no user input by design
- InMemoryCache must also implement `list_resolvers()` for testability
- Frontend graceful degradation: if `fetchResolvers()` fails, dropdown shows only "Any"

---

### Task 1: Storage Layer — Interface + Implementations + Index

**Files:**
- Modify: `src/purl_resolver/storage/interface.py:50-82`
- Modify: `src/purl_resolver/storage/postgres.py:26-214`
- Modify: `src/purl_resolver/storage/inmemory.py:9-119`
- Test: `tests/test_storage.py`
- Test: `tests/test_db_admin_service.py`

**Interfaces:**
- Consumes: existing `Storage` ABC, `PostgresCache`, `InMemoryCache`, `create_pool()`
- Produces: `Storage.list_resolvers() -> list[str]` abstract method

- [ ] **Step 1: Add abstract method to Storage interface**

Edit `src/purl_resolver/storage/interface.py`, add to `Storage` class between `upsert_many` and the final newline:

```python
@abstractmethod
async def list_resolvers(self) -> list[str]: ...
```

- [ ] **Step 2: Add index creation to `create_pool()`**

Edit `src/purl_resolver/storage/postgres.py`, in `create_pool()`, after line 213 (`await conn.execute(_load_schema())`):

```python
await conn.execute(
    "CREATE INDEX IF NOT EXISTS idx_resolved_purls_resolver ON resolved_purls (resolver)"
)
```

- [ ] **Step 3: Implement `list_resolvers()` in PostgresCache**

Edit `src/purl_resolver/storage/postgres.py`, add method to `PostgresCache` class (before `_SORTABLE_COLUMNS` or after `store()`):

```python
async def list_resolvers(self) -> list[str]:
    async with self._pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT DISTINCT resolver FROM resolved_purls ORDER BY resolver"
        )
        return [r["resolver"] for r in rows]
```

- [ ] **Step 4: Implement `list_resolvers()` in InMemoryCache**

Edit `src/purl_resolver/storage/inmemory.py`, add method to `InMemoryCache` class:

```python
async def list_resolvers(self) -> list[str]:
    resolvers: set[str] = set()
    for r in self._store.values():
        if r.resolver:
            resolvers.add(r.resolver)
    return sorted(resolvers)
```

- [ ] **Step 5: Add test for InMemoryCache.list_resolvers()**

Edit `tests/test_storage.py`, add to `class TestInMemoryCache`:

```python
@pytest.mark.asyncio
async def test_list_resolvers(self, storage: InMemoryCache) -> None:
    r1 = ResolveResponse(purl="pkg:pypi/a", repository_url="https://example.com/a", resolver="purl2repo")
    r2 = ResolveResponse(purl="pkg:pypi/b", repository_url="https://example.com/b", resolver="import-csv")
    r3 = ResolveResponse(purl="pkg:pypi/c", repository_url="https://example.com/c", resolver="purl2repo")
    await storage.store(r1)
    await storage.store(r2)
    await storage.store(r3)
    result = await storage.list_resolvers()
    assert result == ["import-csv", "purl2repo"]

@pytest.mark.asyncio
async def test_list_resolvers_empty(self, storage: InMemoryCache) -> None:
    result = await storage.list_resolvers()
    assert result == []
```

- [ ] **Step 6: Add test for DbAdminService.list_resolvers()**

Edit `tests/test_db_admin_service.py`, add new class:

```python
class TestDbAdminServiceListResolvers:
    @pytest.mark.asyncio
    async def test_list_resolvers(self, populated_storage, service):
        result = await service.list_resolvers()
        assert result == []  # populated_storage entries have no resolver set, so default ""

    @pytest.mark.asyncio
    async def test_list_resolvers_with_data(self, storage, service):
        entries = [
            ResolveResponse(purl="pkg:pypi/a", repository_url="https://a.com", resolver="purl2repo"),
            ResolveResponse(purl="pkg:pypi/b", repository_url="https://b.com", resolver="import-csv"),
        ]
        for e in entries:
            storage._store[e.purl] = e
        result = await service.list_resolvers()
        assert "purl2repo" in result
        assert "import-csv" in result
```

- [ ] **Step 7: Run backend tests**

```bash
cd /home/administrator/Desktop/projects/sbom-helper
source .venv/bin/activate
pytest tests/test_storage.py::TestInMemoryCache::test_list_resolvers tests/test_storage.py::TestInMemoryCache::test_list_resolvers_empty tests/test_db_admin_service.py::TestDbAdminServiceListResolvers -v
```

Expected: all 3 tests PASS

---

### Task 2: Backend — Service + Route

**Files:**
- Modify: `src/purl_resolver/db_admin_service.py`
- Modify: `src/purl_resolver/routes/db_admin.py`

**Interfaces:**
- Produces: `DbAdminService.list_resolvers() -> list[str]`
- Produces: `GET /api/v1/db/resolvers` endpoint returning `JSONResponse(content=list[str])`

- [ ] **Step 1: Add `list_resolvers()` to DbAdminService**

Edit `src/purl_resolver/db_admin_service.py`, add method to `DbAdminService` class:

```python
async def list_resolvers(self) -> list[str]:
    return await self._storage.list_resolvers()
```

- [ ] **Step 2: Add route `GET /api/v1/db/resolvers`**

Edit `src/purl_resolver/routes/db_admin.py`, add new route function:

```python
@router.get("/api/v1/db/resolvers")
async def list_resolvers_endpoint(request: Request):
    service: DbAdminService = request.app.state.db_admin_service
    resolvers = await service.list_resolvers()
    return JSONResponse(status_code=200, content=resolvers)
```

- [ ] **Step 3: Run existing backend tests to confirm no regressions**

```bash
pytest tests/test_db_admin_service.py -v
```

Expected: all existing tests PASS

---

### Task 3: Frontend — API Client + Store

**Files:**
- Modify: `frontend/src/api/db.ts`
- Modify: `frontend/src/stores/useDbAdminStore.ts`

**Interfaces:**
- Produces: `listResolvers() -> Promise<string[]>`
- Produces: `store.resolvers` (ref), `store.fetchResolvers()` (action)

- [ ] **Step 1: Add `listResolvers()` to API client**

Edit `frontend/src/api/db.ts`, add after `exportSelectedCsv`:

```typescript
export function listResolvers(): Promise<string[]> {
  return apiFetch<string[]>('/api/v1/db/resolvers')
}
```

- [ ] **Step 2: Add resolvers state + fetchResolvers() to store**

Edit `frontend/src/stores/useDbAdminStore.ts`:

1. Add import:
```typescript
import { listPurls, listResolvers, updatePurl, deletePurls, importCsv, exportSelectedCsv as apiExportCsv } from '../api/db'
```

2. Add ref after line 10 (`const resolver = ref('')`):
```typescript
const resolvers = ref<string[]>([])
```

3. Add action method (after `resetFilters()` or at any suitable place in the action section):
```typescript
async function fetchResolvers() {
  try {
    resolvers.value = await listResolvers()
  } catch {
    resolvers.value = []
  }
}
```

4. Add to return block:
```typescript
resolvers, fetchResolvers,
```

- [ ] **Step 3: Run frontend type check**

```bash
cd /home/administrator/Desktop/projects/sbom-helper/frontend
npx vue-tsc --noEmit
```

Expected: no type errors

---

### Task 4: Frontend — Dynamic Dropdown in Filter Panel

**Files:**
- Modify: `frontend/src/components/db/DbFilterPanel.vue`
- Test: `frontend/src/views/DatabaseAdmin.test.ts`

**Interfaces:**
- Consumes: `store.resolvers`, `store.fetchResolvers()`

- [ ] **Step 1: Update DbFilterPanel template**

Edit `frontend/src/components/db/DbFilterPanel.vue`, replace the hardcoded `<option value="purl2repo">purl2repo</option>` with:

```vue
<option v-for="r in store.resolvers" :key="r" :value="r">{{ r }}</option>
```

- [ ] **Step 2: Fetch resolvers on mount**

Edit `frontend/src/components/db/DbFilterPanel.vue` `<script setup>` block, after `const store = useDbAdminStore()`:

```typescript
import { onMounted } from 'vue'
onMounted(() => { store.fetchResolvers() })
```

- [ ] **Step 3: Update frontend mock + test for new API**

Edit `frontend/src/views/DatabaseAdmin.test.ts`:

1. Add `listResolversMock`:
```typescript
const listResolversMock = vi.fn()
```

2. Add to the `vi.mock` block:
```typescript
listResolvers: () => listResolversMock(),
```

3. Add default mock in `beforeEach`:
```typescript
listResolversMock.mockResolvedValue(['purl2repo', 'import-csv', 'libraries.io'])
```

4. Add a test (inside the `describe` block):
```typescript
it('loads resolvers on mount and populates the filter dropdown', async () => {
  const wrapper = mountAdmin()
  await flushPromises()
  expect(listResolversMock).toHaveBeenCalledTimes(1)
  const fp = wrapper.findComponent(DbFilterPanel)
  const options = fp.findAll('#resolver option')
  const optionTexts = options.map((o) => o.text())
  expect(optionTexts[0]).toBe('Any')   // first option
  expect(optionTexts).toContain('purl2repo')
  expect(optionTexts).toContain('import-csv')
  expect(optionTexts).toContain('libraries.io')
})

it('shows only "Any" when fetchResolvers fails', async () => {
  listResolversMock.mockRejectedValueOnce(new Error('network'))
  const wrapper = mountAdmin()
  await flushPromises()
  const fp = wrapper.findComponent(DbFilterPanel)
  const options = fp.findAll('#resolver option')
  expect(options.length).toBe(1) // just "Any"
  expect(options[0].text()).toBe('Any')
})
```

- [ ] **Step 4: Run frontend tests**

```bash
cd /home/administrator/Desktop/projects/sbom-helper/frontend
npx vitest run src/views/DatabaseAdmin.test.ts
```

Expected: all tests PASS
