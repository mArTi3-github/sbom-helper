# Frontend State Management Refactoring — Design Document

**Date:** 2026-06-29
**Source:** Architecture analysis session (frontend: state management, DatabaseAdmin.vue size, client.ts duplication)

## Overview

Three interconnected frontend architecture issues: (1) no unified state management leading to scattered `ref`/`computed` across views, (2) `DatabaseAdmin.vue` at 964 lines (~370 CSS) — 3x the size of other views, (3) duplicated error handling in `client.ts` (`request` vs `requestBlob`). All three are addressed in a single refactoring pass.

---

## Fix #1: Unified API client — `client.ts`

### Problem
`request<T>()` and `requestBlob()` in `frontend/src/api/client.ts` share an identical error-handling block (lines 23-33 vs 46-56). Two functions with the same logic are a code smell.

### Solution
Replace both with a single `apiFetch<T>()` accepting an optional `format` parameter:

```ts
type ResponseFormat = 'json' | 'blob'

export async function apiFetch<T>(
  url: string,
  options?: RequestInit,
  format: ResponseFormat = 'json',
): Promise<T> {
  const res = await fetch(url, options)
  if (!res.ok) {
    let errorData: { error?: string; message?: string } = {}
    try { errorData = await res.json() } catch { /* ignore */ }
    throw new ApiError(
      res.status,
      errorData.error || 'unknown_error',
      errorData.message || `HTTP ${res.status}`,
    )
  }
  return (format === 'blob' ? res.blob() : res.json()) as Promise<T>
}
```

### Call-site changes

| File | Change |
|---|---|
| `api/purl.ts` | `request<T>` → `apiFetch<T>` |
| `api/sbom.ts` | `request<T>` → `apiFetch<T>` |
| `api/settings.ts` | `request<T>` → `apiFetch<T>` |
| `api/images.ts` | `request<T>` → `apiFetch<T>` |
| `api/db.ts` | `request<T>` → `apiFetch<T>` (7 calls), `requestBlob(...)` → `apiFetch<Blob>(..., 'blob')` (1 call) |

### Files affected
- `frontend/src/api/client.ts` — rewrite
- `frontend/src/api/db.ts` — update imports and one `requestBlob` call
- `frontend/src/api/purl.ts`, `sbom.ts`, `settings.ts`, `images.ts` — update imports

---

## Fix #2: Pinia state management

### Problem
Each view manages its own state via local `ref`/`computed`. `Settings.vue` has ~15 `ref` for settings fields + debounce + save + toast timer. `DatabaseAdmin.vue` has ~20 `ref` for filters, sort, pagination, selection, editing, import. No centralised state makes future cross-component sharing impossible.

### Solution
Install Pinia (`npm install pinia`), register in `main.ts`, create two stores.

### Store: `useSettingsStore`

```ts
// stores/useSettingsStore.ts
export const useSettingsStore = defineStore('settings', () => {
  const validateDbUrls = ref(false)
  const urlValidationTimeout = ref(10)
  // ... all 15 fields from SettingsResponse

  const tokenSet = computed(() => ({
    github_token: !!githubToken.value,
    librariesio_api_key: !!librariesioApiKey.value,
    ecosystems_api_key: !!ecosystemsApiKey.value,
  }))

  let saveTimer: ReturnType<typeof setTimeout> | null = null

  async function load() { /* GET /api/v1/settings → populate refs */ }
  async function save() { /* debounced PATCH /api/v1/settings */ }
  function clearToken(key: 'github' | 'librariesio' | 'ecosystems') { /* nullify + save */ }

  return { validateDbUrls, /* ... */ tokenSet, load, save, clearToken }
})
```

Migrates from `Settings.vue`:
- 15 `ref` → store state
- `load()` action
- `save()` with debounce timer
- `clearToken()` for 3 token types
- Toast timer stays in `Settings.vue` (UI-only concern)

### Store: `useDbAdminStore`

```ts
// stores/useDbAdminStore.ts
export const useDbAdminStore = defineStore('dbAdmin', () => {
  // Filters
  const search = ref('')
  const resolver = ref('')
  const confidence = ref('')
  const dateFrom = ref('')
  const dateTo = ref('')

  // Sort
  const sortBy = ref('resolved_at')
  const sortOrder = ref('desc')

  // Pagination (absorbs usePagination composable)
  const page = ref(1)
  const pageSize = ref(50)
  const total = ref(0)
  const totalPages = computed(() => Math.ceil(total.value / pageSize.value) || 1)

  // Data
  const rows = ref<ResolveResponse[]>([])
  const selectedPurls = ref(new Set<string>())
  const allSelected = computed(() => rows.value.length > 0 && selectedPurls.value.size === rows.value.length)
  const someSelected = computed(() => selectedPurls.value.size > 0 && selectedPurls.value.size < rows.value.length)

  // Inline edit
  const editingPurl = ref<string | null>(null)
  const editingValues = ref<{ purl?: string; repository_url?: string }>({})

  // Import modal
  const showImportModal = ref(false)
  const importFile = ref<File | null>(null)
  const importStrategy = ref<'upsert' | 'skip_existing'>('upsert')
  const importResults = ref<ImportResponse | null>(null)
  const importLoading = ref(false)
  const importError = ref<string | null>(null)

  // Feedback
  const loading = ref(false)
  const errorMessage = ref<string | null>(null)
  const successMessage = ref<string | null>(null)

  // Actions
  async function fetchData() { /* ... */ }
  function applyFilters() { page.value = 1; fetchData() }
  function resetFilters() { /* clear all filters */ }
  function setSort(column: string) { /* toggle, fetch */ }
  function toggleSelectAll(checked: boolean) { /* ... */ }
  function toggleRow(purl: string) { /* ... */ }
  function startEdit(row: ResolveResponse) { /* ... */ }
  function cancelEdit() { /* ... */ }
  async function saveEdit(row: ResolveResponse) { /* PATCH + refresh */ }
  async function deleteRow(purl: string) { /* ... */ }
  async function deleteSelected() { /* ... */ }
  async function exportCsv() { /* Blob download */ }
  function handleImportFile(file: File) { /* ... */ }
  async function handleImportUpload() { /* POST form */ }
  function closeImportModal() { /* reset import state */ }
  function goToPage(p: number) { if (p >= 1 && p <= totalPages.value) page.value = p }
  function changePageSize(size: number) { pageSize.value = size; page.value = 1 }

  return {
    search, resolver, confidence, dateFrom, dateTo,
    sortBy, sortOrder,
    page, pageSize, total, totalPages,
    rows, selectedPurls, allSelected, someSelected,
    editingPurl, editingValues,
    showImportModal, importFile, importStrategy, importResults, importLoading, importError,
    loading, errorMessage, successMessage,
    fetchData, applyFilters, resetFilters, setSort,
    toggleSelectAll, toggleRow,
    startEdit, cancelEdit, saveEdit,
    deleteRow, deleteSelected, exportCsv,
    handleImportFile, handleImportUpload, closeImportModal,
    goToPage, changePageSize,
  }
})
```

### Registration in `main.ts`

```ts
import { createPinia } from 'pinia'
const pinia = createPinia()
createApp(App).use(pinia).use(router).mount('#app')
```

### Files affected
- `frontend/package.json` — add `pinia` dependency
- `frontend/src/main.ts` — install Pinia
- `frontend/src/stores/useSettingsStore.ts` — new file
- `frontend/src/stores/useDbAdminStore.ts` — new file
- `frontend/src/views/Settings.vue` — replace local state with `useSettingsStore()`
- `frontend/src/views/DatabaseAdmin.vue` — replace local state with `useDbAdminStore()` (intermediate state before decomposition)

---

## Fix #3: DatabaseAdmin.vue decomposition

### Problem
`DatabaseAdmin.vue` is 964 lines (266 template, 325 script, 373 CSS). Other views are 257–612 lines. A single-file component this large is hard to navigate, review, and test.

### Solution
Split into 4 components, all connected to `useDbAdminStore`:

```
DatabaseAdmin.vue (~40 lines)     — layout shell
  ├── DbFilterPanel.vue (~90)     — search, resolver, confidence, date range filters
  ├── DbDataTable.vue (~280)      — table, sort, inline-edit, pagination, selection
  └── DbImportModal.vue (~190)    — import modal (reuses existing ModalDialog + FileUploadZone)
```

### Component responsibilities

**DbFilterPanel.vue** (`frontend/src/components/db/DbFilterPanel.vue`)
- Renders filter row: search input, resolver select, confidence select, date from/to, Apply/Reset buttons
- Reads/writes `search`, `resolver`, `confidence`, `dateFrom`, `dateTo` from store
- Calls `applyFilters()`, `resetFilters()` from store

**DbDataTable.vue** (`frontend/src/components/db/DbDataTable.vue`)
- Renders the full table with all columns
- Sortable column headers (calls `setSort()`)
- Checkbox column for row selection (reads `selectedPurls`, calls `toggleRow()`/`toggleSelectAll()`)
- Inline editing on double-click (reads `editingPurl`/`editingValues`, calls `startEdit()`/`saveEdit()`/`cancelEdit()`)
- Pagination bar (reads `page`, `totalPages`, `total`, calls `goToPage()`/`changePageSize()`)
- Toolbar with Export/Import/Delete buttons (calls `exportCsv()`/`deleteSelected()`)
- Loading spinner and error/success messages (reads `loading`, `errorMessage`, `successMessage`)
- Helper functions: `joinArray()`, `truncate()`, `formatDate()`, `visiblePages()` move here as private utilities

**DbImportModal.vue** (`frontend/src/components/db/DbImportModal.vue`)
- Wraps existing `ModalDialog` + `FileUploadZone`
- CSV format reference section
- Import strategy radio (upsert / skip_existing)
- Upload button
- Import results display
- Reads/writes `showImportModal`, `importFile`, `importStrategy`, `importResults`, `importLoading`, `importError` from store
- Calls `handleImportFile()`/`handleImportUpload()`/`closeImportModal()` from store

`usePagination` composable is no longer imported — its logic is absorbed into `useDbAdminStore`.

`safeUrl` import from `useDownload` remains in `DbDataTable.vue` where repository URL links are rendered.

### Files affected
- `frontend/src/views/DatabaseAdmin.vue` — reduced to a ~40-line shell
- `frontend/src/components/db/DbFilterPanel.vue` — new file
- `frontend/src/components/db/DbDataTable.vue` — new file
- `frontend/src/components/db/DbImportModal.vue` — new file

---

## Implementation order

1. **`apiFetch` refactoring** — isolated, no behavioural change, all tests pass
2. **Install Pinia, create stores** — `useSettingsStore` + `useDbAdminStore`, update `main.ts`
3. **Wire `useSettingsStore` into `Settings.vue`** — replace local `ref` with store
4. **Wire `useDbAdminStore` into `DatabaseAdmin.vue`** — replace local `ref` with store (pre-decomposition)
5. **Decompose `DatabaseAdmin.vue`** — create 3 sub-components, reduce shell to ~40 lines

Steps 2–4 can be tested incrementally: store logic can be unit-tested in isolation, then component integration tested via existing `DatabaseAdmin.test.ts` and `Settings.test.ts`.

## Testing

- Existing `DatabaseAdmin.test.ts` and `Settings.test.ts` remain passing after each step
- `client.ts` refactoring: no new tests needed (same behaviour, same interface)
- Store unit tests: `npm run test:coverage --prefix frontend` verifies coverage
- `usePagination` test (`composables/usePagination.test.ts`) is removed — logic absorbed into `useDbAdminStore`

## Scope boundaries

- **Not included:** Pinia stores for PurlResolver, SbomUpdater, ImagesListConverter — their state is per-page and doesn't need sharing
- **Not included:** Any backend changes
- **Not included:** CSS variable extraction or global style refactoring
