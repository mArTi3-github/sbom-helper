# Manual Add Row — Design

## Problem

The "Manage Database" page (`/db-admin`) allows viewing, editing, deleting, importing (CSV), and exporting records in the `resolved_purls` table, but there is no way to manually add a single new record through the UI. Users must either import a CSV file (overkill for one row) or insert directly into the database.

## Solution

Add an "Add Row" button to the toolbar. When clicked, a new editable row appears at the top of the table with inline inputs for PURL and Repository URL. The Resolver field is auto-filled with `"import-manual"`, and Resolved At is auto-filled with the current timestamp. Saving via `POST /api/v1/db/purls` inserts the record.

## Decisions

1. **Inline new row** (not modal) — consistent with existing inline editing UX for edit/delete.
2. **Resolver = "import-manual"** — distinguishes manually added records from auto-resolved ones.
3. **PURL validation** — uses existing `purl_utils.validate()` before insert, same as the resolve flow.
4. **Duplicate check** — returns 409 Conflict if PURL already exists.
5. **No update on conflict** — strictly insert-only; conflicts must be resolved by the user (edit or delete the existing row first).

## Backend

### New schema: `PurlCreateRequest`

File: `src/purl_resolver/schemas.py`

```python
class PurlCreateRequest(BaseModel):
    purl: str = Field(..., min_length=1)
    repository_url: str = Field(..., min_length=1)
```

### New method: `DbAdminService.create_purl()`

File: `src/purl_resolver/db_admin_service.py`

```python
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

### New route: `POST /api/v1/db/purls`

File: `src/purl_resolver/routes/db_admin.py`

```python
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

## Frontend — API layer

File: `frontend/src/api/db.ts`

```typescript
export function createPurl(purl: string, repository_url: string): Promise<{ ok: boolean }> {
  return apiFetch<{ ok: boolean }>('/api/v1/db/purls', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ purl, repository_url }),
  })
}
```

## Frontend — Store

File: `frontend/src/stores/useDbAdminStore.ts`

New state:

```typescript
const addingNewRow = ref(false)
const newRowValues = ref<{ purl: string; repository_url: string }>({ purl: '', repository_url: '' })
const newRowError = ref<string | null>(null)
```

New methods:

| Method | Behavior |
|---|---|
| `startNewRow()` | Set `addingNewRow = true`, `newRowValues = { purl: '', repository_url: '' }`, `newRowError = null` |
| `cancelNewRow()` | Set `addingNewRow = false`, clear values |
| `saveNewRow()` | Call `createPurl(purl, repository_url)`. On success: `cancelNewRow()`, `fetchData()`, show success. On error: set `newRowError` with translated message. |

Error handling in `saveNewRow`:
- `ApiError` with `e.error === 'invalid_purl'` → `newRowError = t('dbAdmin.invalidPurl', { detail: e.data.detail || '' })`
- `ApiError` with `e.error === 'purl_exists'` → `newRowError = t('dbAdmin.purlExists')`
- Other errors → generic failure message

## Frontend — Template

File: `frontend/src/components/db/DbDataTable.vue`

### Toolbar change

Add button before Export CSV:

```html
<button class="btn btn-primary" @click="store.startNewRow()">+ {{ t('dbAdmin.addRow') }}</button>
```

### New row in `<tbody>`

When `store.addingNewRow` is true, render a special row at position 0 (before v-for loop using `<template>` with `v-if`):

```
┌─────────┬──────────────┬──────────────────┬───────────────┬─────────────────┬────────────┐
│ ☐ (off) │ <input> purl │ <input> repo_url │ import-manual │ <current time>  │ 💾 Cancel  │
└─────────┴──────────────┴──────────────────┴───────────────┴─────────────────┴────────────┘
```

- Checkbox column: empty/disabled
- PURL column: `<input>` with v-model
- Repository URL column: `<input>` with v-model
- Resolver column: text "import-manual"
- Resolved At column: formatted current timestamp
- Actions column: Save (checkmark) / Cancel (X) buttons

Error message shown below the new row if `store.newRowError` is set.

Validation: Save button disabled when `newRowValues.purl` or `newRowValues.repository_url` is empty.

## i18n strings

File: `frontend/src/i18n/locales/en.json`

```json
"addRow": "Add Row",
"invalidPurl": "Invalid PURL format: {detail}",
"purlExists": "This PURL already exists in the database."
```

File: `frontend/src/i18n/locales/ru.json`

```json
"addRow": "Добавить строку",
"invalidPurl": "Неверный формат PURL: {detail}",
"purlExists": "Этот PURL уже существует в базе данных."
```

## Data Flow

```
Click [+ Add Row]
  → store.startNewRow()
  → new row appears at top of table
  → user fills PURL and Repository URL
  → click Save (or Enter key)
  → store.saveNewRow()
    → validate locally (non-empty)
    → POST /api/v1/db/purls { purl, repository_url }
      → service.create_purl()
        → purl_utils.validate(purl)       ← 400 if invalid
        → storage.lookup(purl)            ← 409 if exists
        → storage.upsert_many([UpsertRow])  ← 201 inserted
    → on 201: cancelNewRow(), fetchData(), success message
    → on 400/409: set newRowError with translated message
  → click Cancel → cancelNewRow(), row disappears
```

## Files Changed

| File | Change |
|---|---|
| `src/purl_resolver/schemas.py` | Add `PurlCreateRequest` schema |
| `src/purl_resolver/db_admin_service.py` | Add `create_purl()` method |
| `src/purl_resolver/routes/db_admin.py` | Add `POST /api/v1/db/purls` route |
| `frontend/src/api/db.ts` | Add `createPurl()` function |
| `frontend/src/stores/useDbAdminStore.ts` | Add newRow state, startNewRow, cancelNewRow, saveNewRow |
| `frontend/src/components/db/DbDataTable.vue` | Add button + new row template |
| `frontend/src/i18n/locales/en.json` | Add `addRow`, `invalidPurl`, `purlExists` |
| `frontend/src/i18n/locales/ru.json` | Add `addRow`, `invalidPurl`, `purlExists` |
