# Manual Add Row Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a button to the Manage Database page that lets users manually insert a new row with editable PURL and Repository URL fields, auto-filling resolver="import-manual" and the current timestamp.

**Architecture:** Backend adds a `POST /api/v1/db/purls` endpoint that validates the PURL via `purl_utils.validate()`, checks for duplicates, then inserts via `storage.upsert_many()`. Frontend adds an inline editable row at the top of the table, consistent with the existing inline edit pattern.

**Tech Stack:** FastAPI (Python), Pydantic v2, Pinia (Vue 3), vue-i18n

## Global Constraints

- Use `purl_utils.validate()` (wraps `PackageURL.from_string()`) for PURL format validation
- Resolver value for manual inserts: `"import-manual"`
- All new i18n strings must be added to both `en.json` and `ru.json`
- Follow existing inline-edit UX patterns in `DbDataTable.vue`

---

### Task 1: Backend — schema, service method, route, and tests

**Files:**
- Modify: `src/purl_resolver/schemas.py`
- Modify: `src/purl_resolver/db_admin_service.py`
- Modify: `src/purl_resolver/routes/db_admin.py`
- Test: `tests/test_db_admin.py`

**Interfaces:**
- Consumes: `validate(purl: str) -> PurlComponents` from `purl_resolver.purl_utils`, `PurlValidationError` from same module
- Consumes: `Storage.upsert_many(rows: list[UpsertRow]) -> tuple[int, int]` — inserts row with `resolver="import-manual"`
- Consumes: `Storage.lookup(purl: str) -> ResolveResponse | None` — for duplicate check
- Produces: `PurlCreateRequest(purl: str, repository_url: str)` — Pydantic schema
- Produces: `DbAdminService.create_purl(purl: str, repository_url: str) -> tuple[bool, str | None]` — second element is error tag (`"invalid_purl:<detail>"` or `"purl_exists"`)
- Produces: `POST /api/v1/db/purls` — returns 201 `{"ok": true}` on success, 400 `{"error": "invalid_purl", "detail": "..."}` on invalid PURL, 409 `{"error": "purl_exists"}` on duplicate

- [ ] **Step 1: Add `PurlCreateRequest` schema**

Insert after `PurlUpdateRequest` (line 67) in `src/purl_resolver/schemas.py`:

```python
class PurlCreateRequest(BaseModel):
    purl: str = Field(..., min_length=1)
    repository_url: str = Field(..., min_length=1)
```

- [ ] **Step 2: Add `create_purl` method to `DbAdminService`**

Add to `src/purl_resolver/db_admin_service.py`, after `update_purl` (line 69), before `delete_purls`:

```python
from .purl_utils import validate, PurlValidationError

async def create_purl(self, purl: str, repository_url: str) -> tuple[bool, str | None]:
    try:
        validate(purl)
    except PurlValidationError as e:
        return False, f"invalid_purl:{e}"

    existing = await self._storage.lookup(purl)
    if existing is not None:
        return False, "purl_exists"

    row = UpsertRow(purl=purl, repository_url=repository_url, resolver="import-manual")
    await self._storage.upsert_many([row])
    return True, None
```

- [ ] **Step 3: Add `POST /api/v1/db/purls` route to `db_admin.py`**

Add after `update_purl_endpoint` (line 44), before `delete_purls_endpoint`:

```python
from ..schemas import PurlCreateRequest

@router.post("/api/v1/db/purls")
async def create_purl_endpoint(body: PurlCreateRequest, request: Request):
    service: DbAdminService = request.app.state.db_admin_service
    ok, error_tag = await service.create_purl(body.purl, body.repository_url)

    if error_tag == "purl_exists":
        return JSONResponse(status_code=409, content={"error": "purl_exists"})

    if error_tag and error_tag.startswith("invalid_purl:"):
        detail = error_tag.split(":", 1)[1]
        return JSONResponse(status_code=400, content={"error": "invalid_purl", "detail": detail})

    return JSONResponse(status_code=201, content={"ok": True})
```

- [ ] **Step 4: Add route-level tests**

Add to `tests/test_db_admin.py`:

```python
class TestAdminCreatePurl:
    def test_create_success(self, populated_storage, admin_client):
        response = admin_client.post(
            "/api/v1/db/purls",
            json={"purl": "pkg:pypi/newpkg", "repository_url": "https://github.com/new/pkg"},
        )
        assert response.status_code == 201
        assert response.json() == {"ok": True}
        cached = populated_storage._store.get("pkg:pypi/newpkg")
        assert cached is not None
        assert cached.repository_url == "https://github.com/new/pkg"
        assert cached.resolver == "import-manual"

    def test_create_duplicate(self, populated_storage, admin_client):
        response = admin_client.post(
            "/api/v1/db/purls",
            json={"purl": "pkg:pypi/requests", "repository_url": "https://github.com/psf/requests"},
        )
        assert response.status_code == 409
        assert response.json() == {"error": "purl_exists"}

    def test_create_invalid_purl(self, populated_storage, admin_client):
        response = admin_client.post(
            "/api/v1/db/purls",
            json={"purl": "not-a-purl", "repository_url": "https://github.com/x/y"},
        )
        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "invalid_purl"
        assert "detail" in data

    def test_create_missing_repository_url(self, populated_storage, admin_client):
        response = admin_client.post(
            "/api/v1/db/purls",
            json={"purl": "pkg:pypi/newpkg", "repository_url": ""},
        )
        assert response.status_code == 422  # Pydantic validation min_length=1
```

Also need to add the import at the top if not already there:
`from src.purl_resolver.schemas import PurlCreateRequest` (check existing imports in test file)

- [ ] **Step 5: Run backend tests**

Run: `cd /home/administrator/Desktop/projects/sbom-helper && .venv/bin/python -m pytest tests/test_db_admin.py -v -x`
Expected: all tests pass, including existing ones and the 4 new ones

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: add POST /api/v1/db/purls endpoint for manual row creation"
```

---

### Task 2: Frontend — API client and Pinia store methods

**Files:**
- Modify: `frontend/src/api/db.ts`
- Modify: `frontend/src/stores/useDbAdminStore.ts`

**Interfaces:**
- Consumes: `createPurl(purl, repository_url)` — new API function
- Consumes: `useDbAdminStore` — existing Pinia store
- Produces: `store.addingNewRow`, `store.newRowValues`, `store.newRowError` — reactive state
- Produces: `store.startNewRow()`, `store.cancelNewRow()`, `store.saveNewRow()` — methods consumed by template

- [ ] **Step 1: Add `createPurl` API function**

Add to `frontend/src/api/db.ts`, after `updatePurl` (line 40):

```typescript
export function createPurl(purl: string, repository_url: string): Promise<{ ok: boolean }> {
  return apiFetch<{ ok: boolean }>('/api/v1/db/purls', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ purl, repository_url }),
  })
}
```

- [ ] **Step 2: Add newRow state and methods to Pinia store**

Add to `frontend/src/stores/useDbAdminStore.ts`, after the `editingValues` ref (line 29):

```typescript
const addingNewRow = ref(false)
const newRowValues = ref<{ purl: string; repository_url: string }>({ purl: '', repository_url: '' })
const newRowError = ref<string | null>(null)
```

Add `createPurl` to the import from `../api/db` (line 3):

```typescript
import { listPurls, listResolvers, updatePurl, deletePurls, importCsv, createPurl, exportSelectedCsv as apiExportCsv } from '../api/db'
```

Add methods after `cancelEdit()` (line 125):

```typescript
import { ApiError } from '../api/client'

function startNewRow() {
  addingNewRow.value = true
  newRowValues.value = { purl: '', repository_url: '' }
  newRowError.value = null
}

function cancelNewRow() {
  addingNewRow.value = false
  newRowValues.value = { purl: '', repository_url: '' }
  newRowError.value = null
}

async function saveNewRow() {
  newRowError.value = null
  try {
    await createPurl(newRowValues.value.purl, newRowValues.value.repository_url)
    cancelNewRow()
    showSuccess('Record created successfully')
    await fetchData()
  } catch (e: unknown) {
    if (e instanceof ApiError) {
      if (e.error === 'invalid_purl') {
        newRowError.value = t('dbAdmin.invalidPurl', { detail: (e.data.detail as string) || '' })
      } else if (e.error === 'purl_exists') {
        newRowError.value = t('dbAdmin.purlExists')
      } else {
        errorMessage.value = 'Failed to create record'
      }
    } else if (e instanceof Error) {
      errorMessage.value = 'Network error: could not reach the server.'
    } else {
      errorMessage.value = 'An unexpected error occurred.'
    }
  }
}
```

Note: `t` is the i18n function — it needs to be imported. Add to the import line at the top:

```typescript
import { useI18n } from 'vue-i18n'
```

And at the top of the setup function body (before the first `const`), add:

```typescript
const { t } = useI18n()
```

Add to the `return` block:

```typescript
addingNewRow, newRowValues, newRowError,
startNewRow, cancelNewRow, saveNewRow,
```

- [ ] **Step 3: Build frontend to verify no TypeScript errors**

Run: `cd /home/administrator/Desktop/projects/sbom-helper/frontend && npm run build`
Expected: clean build with no errors

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "feat: add createPurl API client and store methods for manual add row"
```

---

### Task 3: Frontend — template (button + new row) and i18n strings

**Files:**
- Modify: `frontend/src/components/db/DbDataTable.vue`
- Modify: `frontend/src/i18n/locales/en.json`
- Modify: `frontend/src/i18n/locales/ru.json`

**Interfaces:**
- Consumes: `store.addingNewRow`, `store.newRowValues`, `store.newRowError` and methods from Task 2
- Consumes: `handleEdit(row)` → `store.saveEdit(row)` — existing save on Enter pattern for reuse

- [ ] **Step 1: Add i18n strings to `en.json`**

Add after `"errors": "Errors:"` (line 137) in `frontend/src/i18n/locales/en.json`:

```json
"addRow": "Add Row",
"saveNewRow": "Save",
"cancelNewRow": "Cancel",
"invalidPurl": "Invalid PURL format: {detail}",
"purlExists": "This PURL already exists in the database."
```

- [ ] **Step 2: Add i18n strings to `ru.json`**

Add after `"errors": "Ошибок:"` (line 137) in `frontend/src/i18n/locales/ru.json`:

```json
"addRow": "Добавить строку",
"saveNewRow": "Сохранить",
"cancelNewRow": "Отмена",
"invalidPurl": "Неверный формат PURL: {detail}",
"purlExists": "Этот PURL уже существует в базе данных."
```

- [ ] **Step 3: Add "Add Row" button to toolbar**

In `frontend/src/components/db/DbDataTable.vue`, add the button as the first element in `.toolbar` (before Export CSV):

```html
<button class="btn btn-primary" :disabled="store.addingNewRow" @click="store.startNewRow()">{{ t('dbAdmin.addRow') }}</button>
```

- [ ] **Step 4: Add new row template in `<tbody>`**

In `frontend/src/components/db/DbDataTable.vue`, add a new row before the `v-for` row (after the opening `<tbody>` tag, before `<tr v-for="row in store.rows">`):

```html
<tr v-if="store.addingNewRow" class="new-row">
  <td class="col-check"></td>
  <td>
    <input v-model="store.newRowValues.purl" class="inline-edit" placeholder="pkg:type/name" @keydown="handleNewRowKeydown">
  </td>
  <td>
    <input v-model="store.newRowValues.repository_url" class="inline-edit" placeholder="https://github.com/..." @keydown="handleNewRowKeydown">
  </td>
  <td><span class="auto-field">import-manual</span></td>
  <td class="cell-nowrap"><span class="auto-field">{{ currentTimestamp }}</span></td>
  <td class="col-actions">
    <button class="btn btn-sm btn-primary" :disabled="!store.newRowValues.purl || !store.newRowValues.repository_url" @click="store.saveNewRow()">{{ t('dbAdmin.saveNewRow') }}</button>
    <button class="btn btn-sm btn-secondary" @click="store.cancelNewRow()">{{ t('dbAdmin.cancelNewRow') }}</button>
  </td>
</tr>
<tr v-if="store.addingNewRow && store.newRowError" class="new-row-error">
  <td colspan="7"><span class="error-text">{{ store.newRowError }}</span></td>
</tr>
```

Add `currentTimestamp` computed property in the `<script setup>` block:

```typescript
const currentTimestamp = computed(() => {
  const d = new Date()
  const pad = (n: number) => n.toString().padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
})
```

Add `handleNewRowKeydown` function:

```typescript
function handleNewRowKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && store.newRowValues.purl && store.newRowValues.repository_url) {
    store.saveNewRow()
  } else if (event.key === 'Escape') {
    store.cancelNewRow()
  }
}
```

- [ ] **Step 5: Add CSS styles for new-row highlighting**

Add to the `<style scoped>` block in `DbDataTable.vue`:

```css
.new-row {
  background: var(--color-primary-bg, rgba(59, 130, 246, 0.05));
}

.new-row td {
  border-top: 2px solid var(--color-primary);
}

.new-row-error td {
  padding-top: 0;
  padding-bottom: 0.75rem;
  border-bottom: none;
}

.error-text {
  color: var(--color-error);
  font-size: 0.82rem;
}

.auto-field {
  color: var(--color-muted);
  font-style: italic;
}
```

- [ ] **Step 6: Build frontend to verify**

Run: `cd /home/administrator/Desktop/projects/sbom-helper/frontend && npm run build`
Expected: clean build with no errors

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat: add UI for manual row creation in DbDataTable"
```

---

### Task 4: Full integration test — end-to-end verification

- [ ] **Step 1: Rebuild frontend with production build**

Run: `cd /home/administrator/Desktop/projects/sbom-helper/frontend && npm run build`

- [ ] **Step 2: Run all backend tests**

Run: `cd /home/administrator/Desktop/projects/sbom-helper && .venv/bin/python -m pytest -v -x`
Expected: all tests pass, including the new create_purl tests

- [ ] **Step 3: Run lint/typecheck if available**

Run: check if `.venv/bin/ruff` or `npm run lint` / `npm run typecheck` exist and run them
Expected: clean run

- [ ] **Step 4: Commit final verification**

```bash
git add -A
git commit -m "chore: final verification of manual add row feature"
```
