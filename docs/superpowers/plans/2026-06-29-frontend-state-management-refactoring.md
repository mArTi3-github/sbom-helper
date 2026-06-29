# Frontend State Management Refactoring — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor frontend: unify API client error handling, introduce Pinia state management for Settings and DbAdmin, decompose DatabaseAdmin.vue into sub-components.

**Architecture:** Three sequential phases: (1) client.ts → unified `apiFetch`, (2) Pinia stores → `useSettingsStore` + `useDbAdminStore`, (3) DatabaseAdmin decomposition → `DbFilterPanel`, `DbDataTable`, `DbImportModal`. Each phase produces independently testable changes.

**Tech Stack:** Vue 3.5 (Composition API + `<script setup>`), TypeScript 6.0, Vitest 4.1, Pinia 4.x, happy-dom

## Global Constraints

- Pinia installed via `npm install pinia` (no `@pinia/testing` — tests use `setActivePinia(createPinia())`)
- Setup store syntax (`defineStore('id', () => { ... })`) — not Options API
- `storeToRefs` for destructuring state/getters in components
- All existing tests remain passing after each step
- Vue files use `<script setup lang="ts">` and `<style scoped>`
- New components directory: `frontend/src/components/db/`

---

### Task 1: Unify API client — `apiFetch` function

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/api/db.ts` (line 1 + line 63)
- Modify: `frontend/src/api/purl.ts` (line 1)
- Modify: `frontend/src/api/sbom.ts` (line 1)
- Modify: `frontend/src/api/settings.ts` (line 1)
- Modify: `frontend/src/api/images.ts` (line 1)

**Interfaces:**
- Consumes: `ApiError` class (already exists, no signature change)
- Produces: `apiFetch<T>(url, options?, format?): Promise<T>` — single replacement for `request` + `requestBlob`

- [ ] **Step 1: Rewrite `client.ts`**

Replace both `request` and `requestBlob` with a single `apiFetch`. Keep `ApiError` class unchanged.

```ts
export class ApiError extends Error {
  status: number
  error: string
  constructor(status: number, error: string, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.error = error
  }
}

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

- [ ] **Step 2: Update API module imports**

In each of these 5 files, replace `import { request }` or `import { request, requestBlob }` with `import { apiFetch }`:

| File | Old import | New import |
|---|---|---|
| `api/purl.ts` | `import { request } from './client'` | `import { apiFetch } from './client'` |
| `api/sbom.ts` | `import { request } from './client'` | `import { apiFetch } from './client'` |
| `api/settings.ts` | `import { request } from './client'` | `import { apiFetch } from './client'` |
| `api/images.ts` | `import { request } from './client'` | `import { apiFetch } from './client'` |
| `api/db.ts` | `import { request, requestBlob } from './client'` | `import { apiFetch } from './client'` |

- [ ] **Step 3: Replace call-sites in `api/db.ts`**

Change all `request<T>(...)` → `apiFetch<T>(...)` (7 calls). Change `requestBlob(...)` → `apiFetch<Blob>(..., 'blob')`:

```ts
export function listPurls(params: PurlListParams): Promise<PurlListResponse> {
  const query = buildPurlQuery(params)
  return apiFetch<PurlListResponse>(`/api/v1/db/purls?${query.toString()}`)
}

export function updatePurl(purl: string, body: PurlUpdateRequest): Promise<{ ok: boolean }> {
  const encoded = encodeURIComponent(purl).replace(/%2F/g, '/')
  return apiFetch<{ ok: boolean }>(`/api/v1/db/purls/${encoded}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export function deletePurls(purls: string[]): Promise<DeleteResponse> {
  return apiFetch<DeleteResponse>('/api/v1/db/purls', {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ purls }),
  })
}

export function importCsv(file: File, strategy: 'upsert' | 'skip_existing'): Promise<ImportResponse> {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('strategy', strategy)
  return apiFetch<ImportResponse>('/api/v1/db/import', {
    method: 'POST',
    body: formData,
  })
}

export function exportSelectedCsv(purls: string[]): Promise<Blob> {
  return apiFetch<Blob>('/api/v1/db/export', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ purls }),
  }, 'blob')
}
```

- [ ] **Step 4: Replace call-sites in remaining API modules**

Change `request<T>(...)` → `apiFetch<T>(...)` in each file. The function signatures and arguments remain identical — only the name changes.

`api/purl.ts`:
```ts
import { apiFetch } from './client'
import type { ResolveRequest, ResolveResponse } from '../types/api'

export function resolvePurl(body: ResolveRequest): Promise<ResolveResponse> {
  return apiFetch<ResolveResponse>('/api/v1/resolve', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}
```

`api/sbom.ts`:
```ts
import { apiFetch } from './client'
import type { IgnorePatternItem, SbomResponse } from '../types/api'

export function getIgnorePatterns(): Promise<{ patterns: IgnorePatternItem[] }> {
  return apiFetch<{ patterns: IgnorePatternItem[] }>('/api/v1/sbom/ignore-patterns')
}

export function saveIgnorePatterns(patterns: IgnorePatternItem[]): Promise<{ status: string }> {
  return apiFetch<{ status: string }>('/api/v1/sbom/ignore-patterns', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ patterns }),
  })
}

export function resolveSbom(
  file: File,
  removeUnresolved: boolean,
  validateRefs: boolean,
  ignorePatterns: IgnorePatternItem[],
  signal?: AbortSignal,
): Promise<SbomResponse> {
  const formData = new FormData()
  formData.append('file', file)
  if (removeUnresolved) formData.append('remove_unresolved_no_subcomponents', 'true')
  if (validateRefs) formData.append('validate_existing_refs', 'true')
  if (ignorePatterns.length > 0) formData.append('ignore_patterns', JSON.stringify(ignorePatterns))
  return apiFetch<SbomResponse>('/api/v1/resolve/sbom', {
    method: 'POST',
    body: formData,
    signal,
  })
}
```

`api/settings.ts`:
```ts
import { apiFetch } from './client'
import type { SettingsResponse, SettingsUpdate } from '../types/api'

export function getSettings(): Promise<SettingsResponse> {
  return apiFetch<SettingsResponse>('/api/v1/settings')
}

export function updateSettings(body: SettingsUpdate): Promise<SettingsResponse> {
  return apiFetch<SettingsResponse>('/api/v1/settings', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}
```

`api/images.ts`:
```ts
import { apiFetch } from './client'
import type { ImagesListResponse } from '../types/api'

export function convertImagesList(file: File): Promise<ImagesListResponse> {
  const formData = new FormData()
  formData.append('file', file)
  return apiFetch<ImagesListResponse>('/api/v1/convert/images-list', {
    method: 'POST',
    body: formData,
  })
}
```

- [ ] **Step 5: Run tests to verify no regressions**

```bash
npm test --prefix frontend
```
Expected: All existing tests pass (same interface, no behavioural change).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/
git commit -m "refactor: unify request/requestBlob into single apiFetch in client.ts"
```

---

### Task 2: Install Pinia and create stores

**Files:**
- Modify: `frontend/package.json` — add `pinia` dependency
- Create: `frontend/src/stores/useSettingsStore.ts`
- Create: `frontend/src/stores/useDbAdminStore.ts`
- Modify: `frontend/src/main.ts` — register Pinia

**Interfaces:**
- Consumes: `apiFetch` from Task 1, API functions from `api/settings.ts` and `api/db.ts`
- Produces: `useSettingsStore` (15 state fields, 3 actions, 1 getter), `useDbAdminStore` (~20 state fields, ~15 actions, 3 getters)

- [ ] **Step 1: Install Pinia**

```bash
npm install pinia --prefix frontend
```

- [ ] **Step 2: Create `stores/useSettingsStore.ts`**

```ts
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getSettings, updateSettings } from '../api/settings'
import type { SettingsUpdate } from '../types/api'

export const useSettingsStore = defineStore('settings', () => {
  const validateDbUrls = ref(false)
  const urlValidationTimeout = ref(5)
  const revalidationCooldownHours = ref(24)
  const retryMaxAttempts = ref(3)
  const retryBaseCooldownSeconds = ref(5)
  const logLevel = ref('INFO')
  const librariesioEnabled = ref(false)
  const ecosystemsEnabled = ref(false)
  const ecosystemsMaxRequestsPerSecond = ref(2)
  const batchSemaphoreLimit = ref(10)
  const connectivityUrl = ref('https://github.com')
  const connectivityTimeout = ref(2)
  const rateLimitCooldown = ref(60)
  const tokenSet = ref({ github_token: false, librariesio_api_key: false, ecosystems_api_key: false })
  const githubToken = ref('')
  const librariesioKey = ref('')
  const ecosystemsKey = ref('')
  const loading = ref(true)

  const hasAnyToken = computed(() =>
    tokenSet.value.github_token || tokenSet.value.librariesio_api_key || tokenSet.value.ecosystems_api_key
  )

  async function load() {
    try {
      const data = await getSettings()
      validateDbUrls.value = data.validate_db_urls
      urlValidationTimeout.value = data.url_validation_timeout
      revalidationCooldownHours.value = data.revalidation_cooldown_hours
      retryMaxAttempts.value = data.retry_max_attempts
      retryBaseCooldownSeconds.value = data.retry_base_cooldown_seconds
      logLevel.value = data.log_level
      librariesioEnabled.value = data.librariesio_enabled
      ecosystemsEnabled.value = data.ecosystems_enabled
      ecosystemsMaxRequestsPerSecond.value = data.ecosystems_max_requests_per_second
      batchSemaphoreLimit.value = data.batch_semaphore_limit
      connectivityUrl.value = data.connectivity_url
      connectivityTimeout.value = data.connectivity_timeout
      rateLimitCooldown.value = data.rate_limit_cooldown
      tokenSet.value = data.token_set
    } catch {
      throw new Error('Failed to load settings')
    }
  }

  async function save(partial: SettingsUpdate) {
    const data = await updateSettings(partial)
    tokenSet.value = data.token_set
    if ('github_token' in partial) githubToken.value = ''
    if ('librariesio_api_key' in partial) librariesioKey.value = ''
    if ('ecosystems_api_key' in partial) ecosystemsKey.value = ''
  }

  async function clearToken(field: 'github_token' | 'librariesio_api_key' | 'ecosystems_api_key') {
    await updateSettings({ [field]: null } as SettingsUpdate)
  }

  return {
    validateDbUrls, urlValidationTimeout, revalidationCooldownHours,
    retryMaxAttempts, retryBaseCooldownSeconds, logLevel,
    librariesioEnabled, ecosystemsEnabled, ecosystemsMaxRequestsPerSecond,
    batchSemaphoreLimit, connectivityUrl, connectivityTimeout, rateLimitCooldown,
    tokenSet, githubToken, librariesioKey, ecosystemsKey, loading,
    hasAnyToken, load, save, clearToken,
  }
})
```

- [ ] **Step 3: Create `stores/useDbAdminStore.ts`**

```ts
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { listPurls, updatePurl, deletePurls, importCsv, exportSelectedCsv as apiExportCsv } from '../api/db'
import type { PurlListParams } from '../api/db'
import type { ResolveResponse, ImportResponse } from '../types/api'
import { ApiError } from '../api/client'

export const useDbAdminStore = defineStore('dbAdmin', () => {
  const search = ref('')
  const resolver = ref('')
  const confidence = ref('')
  const dateFrom = ref('')
  const dateTo = ref('')

  const sortBy = ref('resolved_at')
  const sortOrder = ref('desc')

  const page = ref(1)
  const pageSize = ref(50)
  const total = ref(0)
  const totalPages = computed(() => Math.ceil(total.value / pageSize.value) || 1)

  const rows = ref<ResolveResponse[]>([])
  const selectedPurls = ref(new Set<string>())
  const allSelected = computed(() => rows.value.length > 0 && selectedPurls.value.size === rows.value.length)
  const someSelected = computed(() => selectedPurls.value.size > 0 && selectedPurls.value.size < rows.value.length)

  const editingPurl = ref<string | null>(null)
  const editingValues = ref<{ purl?: string; repository_url?: string }>({})

  const showImportModal = ref(false)
  const importFile = ref<File | null>(null)
  const importStrategy = ref<'upsert' | 'skip_existing'>('upsert')
  const importResults = ref<ImportResponse | null>(null)
  const importLoading = ref(false)
  const importError = ref<string | null>(null)

  const loading = ref(false)
  const errorMessage = ref<string | null>(null)
  const successMessage = ref<string | null>(null)

  async function fetchData() {
    loading.value = true
    errorMessage.value = null
    try {
      const params: PurlListParams = {
        page: page.value,
        page_size: pageSize.value,
        search: search.value || undefined,
        resolver: resolver.value || undefined,
        confidence: confidence.value || undefined,
        date_from: dateFrom.value || undefined,
        date_to: dateTo.value || undefined,
        sort_by: sortBy.value,
        sort_order: sortOrder.value,
      }
      const data = await listPurls(params)
      rows.value = data.rows
      total.value = data.total
      selectedPurls.value = new Set()
      editingPurl.value = null
      editingValues.value = {}
    } catch (e: unknown) {
      if (e instanceof ApiError) {
        errorMessage.value = e.message
      } else if (e instanceof Error) {
        errorMessage.value = 'Network error: could not reach the server.'
      } else {
        errorMessage.value = 'An unexpected error occurred.'
      }
    } finally {
      loading.value = false
    }
  }

  function applyFilters() { page.value = 1; fetchData() }

  function resetFilters() {
    search.value = ''
    resolver.value = ''
    confidence.value = ''
    dateFrom.value = ''
    dateTo.value = ''
    sortBy.value = 'resolved_at'
    sortOrder.value = 'desc'
    page.value = 1
    fetchData()
  }

  function setSort(column: string) {
    if (sortBy.value === column) {
      sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc'
    } else {
      sortBy.value = column
      sortOrder.value = 'asc'
    }
    fetchData()
  }

  function toggleSelectAll(checked: boolean) {
    selectedPurls.value = checked ? new Set(rows.value.map(r => r.purl)) : new Set()
  }

  function toggleRow(purl: string) {
    const next = new Set(selectedPurls.value)
    if (next.has(purl)) next.delete(purl)
    else next.add(purl)
    selectedPurls.value = next
  }

  function startEdit(row: ResolveResponse) {
    editingPurl.value = row.purl
    editingValues.value = { purl: row.purl, repository_url: row.repository_url || '' }
  }

  function cancelEdit() {
    editingPurl.value = null
    editingValues.value = {}
  }

  async function saveEdit(row: ResolveResponse) {
    if (editingPurl.value !== row.purl) return
    const body: { purl?: string | null; repository_url?: string | null } = {}
    if (editingValues.value.purl !== undefined && editingValues.value.purl !== row.purl) {
      body.purl = editingValues.value.purl || null
    }
    if (editingValues.value.repository_url !== undefined && editingValues.value.repository_url !== (row.repository_url || '')) {
      body.repository_url = editingValues.value.repository_url || null
    }
    if (Object.keys(body).length === 0) { cancelEdit(); return }
    try {
      await updatePurl(row.purl, body)
      cancelEdit()
      showSuccess('Record updated successfully')
      await fetchData()
    } catch (e: unknown) {
      if (e instanceof ApiError) {
        errorMessage.value = e.message
      } else {
        errorMessage.value = 'Failed to update record'
      }
      cancelEdit()
    }
  }

  async function deleteRow(purl: string) {
    try {
      await deletePurls([purl])
      showSuccess('Record deleted')
      await fetchData()
    } catch (e: unknown) {
      if (e instanceof ApiError) {
        errorMessage.value = e.message
      } else {
        errorMessage.value = 'Failed to delete record'
      }
    }
  }

  async function deleteSelected() {
    const count = selectedPurls.value.size
    if (count === 0) return
    try {
      await deletePurls(Array.from(selectedPurls.value))
      showSuccess(`${count} record(s) deleted`)
      await fetchData()
    } catch (e: unknown) {
      if (e instanceof ApiError) {
        errorMessage.value = e.message
      } else {
        errorMessage.value = 'Failed to delete records'
      }
    }
  }

  async function exportCsv() {
    if (selectedPurls.value.size === 0) return null
    try {
      const blob = await apiExportCsv(Array.from(selectedPurls.value))
      showSuccess('CSV exported successfully')
      return blob
    } catch (e: unknown) {
      if (e instanceof ApiError) {
        errorMessage.value = e.message
      } else {
        errorMessage.value = 'Failed to export CSV'
      }
      return null
    }
  }

  function handleImportFile(file: File) {
    importFile.value = file
    importResults.value = null
  }

  async function handleImportUpload() {
    if (!importFile.value) return
    importLoading.value = true
    importResults.value = null
    importError.value = null
    try {
      const result = await importCsv(importFile.value, importStrategy.value)
      importResults.value = result
      await fetchData()
    } catch (e: unknown) {
      if (e instanceof ApiError) {
        importError.value = e.message
      } else {
        importError.value = 'Failed to import CSV'
      }
    } finally {
      importLoading.value = false
    }
  }

  function closeImportModal() {
    showImportModal.value = false
    importFile.value = null
    importResults.value = null
    importError.value = null
  }

  function goToPage(p: number) {
    if (p < 1 || p > totalPages.value) return
    page.value = p
  }

  function changePageSize(size: number) {
    pageSize.value = size
    page.value = 1
  }

  function showSuccess(msg: string) {
    successMessage.value = msg
    setTimeout(() => { successMessage.value = null }, 3000)
  }

  return {
    search, resolver, confidence, dateFrom, dateTo,
    sortBy, sortOrder,
    page, pageSize, total, totalPages,
    rows, selectedPurls, allSelected, someSelected,
    editingPurl, editingValues,
    showImportModal, importFile, importStrategy, importResults, importLoading, importError,
    loading, errorMessage, successMessage,
    fetchData, applyFilters, resetFilters, setSort,
    toggleSelectAll, toggleRow, startEdit, cancelEdit, saveEdit,
    deleteRow, deleteSelected, exportCsv,
    handleImportFile, handleImportUpload, closeImportModal,
    goToPage, changePageSize,
  }
})
```

- [ ] **Step 4: Register Pinia in `main.ts`**

```ts
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import './assets/main.css'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount('#app')
```

- [ ] **Step 5: Verify compilation**

```bash
npm run build --prefix frontend 2>&1 | head -30
```
Expected: Build succeeds (stores compile, types resolve).

- [ ] **Step 6: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/stores/ frontend/src/main.ts
git commit -m "feat: add Pinia state management with useSettingsStore and useDbAdminStore"
```

---

### Task 3: Wire `useSettingsStore` into `Settings.vue`

**Files:**
- Modify: `frontend/src/views/Settings.vue`
- Modify: `frontend/src/views/Settings.test.ts`

**Interfaces:**
- Consumes: `useSettingsStore` (Task 2), API mock pattern from existing test
- Produces: Settings.vue script section reduced from 140 to ~60 lines

- [ ] **Step 1: Rewrite Settings.vue `<script setup>`**

Replace all local `ref` declarations with `useSettingsStore()` + `storeToRefs`. Keep toast logic local (UI-only). Keep `githubTokenInput`, `librariesioKeyInput`, `ecosystemsKeyInput` as local refs (input-only state, not persisted).

```ts
<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { storeToRefs } from 'pinia'
import { useSettingsStore } from '../stores/useSettingsStore'
import type { SettingsUpdate } from '../types/api'

const store = useSettingsStore()
const {
  validateDbUrls, urlValidationTimeout, revalidationCooldownHours,
  retryMaxAttempts, retryBaseCooldownSeconds, logLevel,
  librariesioEnabled, ecosystemsEnabled, ecosystemsMaxRequestsPerSecond,
  batchSemaphoreLimit, connectivityUrl, connectivityTimeout, rateLimitCooldown,
  tokenSet, loading,
} = storeToRefs(store)

const githubTokenInput = ref('')
const librariesioKeyInput = ref('')
const ecosystemsKeyInput = ref('')

const toast = ref<{ text: string; isError: boolean } | null>(null)
let toastTimer: ReturnType<typeof setTimeout> | null = null

function showToast(text: string, isError: boolean) {
  if (toastTimer) clearTimeout(toastTimer)
  toast.value = { text, isError }
  toastTimer = setTimeout(() => { toast.value = null; toastTimer = null }, isError ? 5000 : 3000)
}

function debounce<T extends (...args: unknown[]) => void>(fn: T, ms: number): T {
  let timer: ReturnType<typeof setTimeout> | null = null
  return ((...args: unknown[]) => {
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => { timer = null; fn(...args) }, ms)
  }) as T
}

function autoSave(partial: SettingsUpdate) {
  store.save(partial)
    .then(() => showToast('Settings saved', false))
    .catch((err: Error) => showToast(`Failed to save: ${err.message}`, true))
}

const debouncedAutoSave = debounce(autoSave, 500)

async function onGithubTokenBlur() {
  const value = githubTokenInput.value.trim()
  if (!value) return
  await autoSave({ github_token: value } as SettingsUpdate)
}

async function onLibrariesIoKeyBlur() {
  const value = librariesioKeyInput.value.trim()
  if (!value) return
  await autoSave({ librariesio_api_key: value } as SettingsUpdate)
}

async function onEcosystemsKeyBlur() {
  const value = ecosystemsKeyInput.value.trim()
  if (!value) return
  await autoSave({ ecosystems_api_key: value } as SettingsUpdate)
}

async function clearToken() {
  try {
    await store.clearToken('github_token')
    showToast('Token cleared', false)
    await store.load()
  } catch { showToast('Failed to clear token', true) }
}

async function clearLibrariesIoKey() {
  try {
    await store.clearToken('librariesio_api_key')
    showToast('Libraries.io key cleared', false)
    await store.load()
  } catch { showToast('Failed to clear key', true) }
}

async function clearEcosystemsKey() {
  try {
    await store.clearToken('ecosystems_api_key')
    showToast('ecosyste.ms key cleared', false)
    await store.load()
  } catch { showToast('Failed to clear key', true) }
}

onMounted(async () => {
  await store.load()
  loading.value = false
})

onBeforeUnmount(() => {
  if (toastTimer) clearTimeout(toastTimer)
})
</script>
```

- [ ] **Step 2: Update Settings.test.ts — add Pinia setup**

```ts
import { setActivePinia, createPinia } from 'pinia'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import Settings from './Settings.vue'
import type { SettingsResponse } from '../types/api'

const defaultSettings: SettingsResponse = {
  validate_db_urls: false,
  url_validation_timeout: 5,
  revalidation_cooldown_hours: 24,
  retry_max_attempts: 3,
  retry_base_cooldown_seconds: 5,
  log_level: 'INFO',
  librariesio_enabled: false,
  ecosystems_enabled: false,
  ecosystems_max_requests_per_second: 2,
  batch_semaphore_limit: 10,
  connectivity_url: 'https://github.com',
  connectivity_timeout: 2,
  rate_limit_cooldown: 60,
  token_set: { github_token: false, librariesio_api_key: false, ecosystems_api_key: false },
}

const successUpdate = vi.fn().mockResolvedValue(defaultSettings)
const getSettingsMock = vi.fn().mockResolvedValue(defaultSettings)

vi.mock('../api/settings', () => ({
  getSettings: () => getSettingsMock(),
  updateSettings: (body: unknown) => successUpdate(body),
}))

async function flush(ms = 0) {
  if (ms > 0) vi.advanceTimersByTime(ms)
  await flushPromises()
}

function mountSettings(): VueWrapper {
  return mount(Settings)
}

describe('Settings.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    successUpdate.mockResolvedValue(defaultSettings)
    getSettingsMock.mockResolvedValue(defaultSettings)
  })
  // ... rest of tests remain identical
})
```

- [ ] **Step 3: Run Settings tests**

```bash
npm test --prefix frontend -- src/views/Settings.test.ts
```
Expected: All 8 tests pass.

- [ ] **Step 4: Run full test suite**

```bash
npm test --prefix frontend
```
Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/Settings.vue frontend/src/views/Settings.test.ts
git commit -m "refactor: wire useSettingsStore into Settings.vue"
```

---

### Task 4: Wire `useDbAdminStore` into `DatabaseAdmin.vue` (pre-decomposition)

**Files:**
- Modify: `frontend/src/views/DatabaseAdmin.vue`
- Modify: `frontend/src/views/DatabaseAdmin.test.ts`
- Remove: `frontend/src/composables/usePagination.ts`
- Remove: `frontend/src/composables/usePagination.test.ts`

**Interfaces:**
- Consumes: `useDbAdminStore` (Task 2), `safeUrl` from `useDownload`
- Produces: DatabaseAdmin.vue script section reduced from ~325 to ~40 lines

- [ ] **Step 1: Rewrite DatabaseAdmin.vue `<script setup>`**

Replace all local state with `useDbAdminStore()`. Remove `usePagination` import.

```ts
<script setup lang="ts">
import { ref, computed } from 'vue'
import { storeToRefs } from 'pinia'
import { useDbAdminStore } from '../stores/useDbAdminStore'
import { safeUrl } from '../composables/useDownload'
import ModalDialog from '../components/ModalDialog.vue'
import FileUploadZone from '../components/FileUploadZone.vue'

const store = useDbAdminStore()
const {
  loading, errorMessage, successMessage,
  search, resolver, confidence, dateFrom, dateTo,
  sortBy, sortOrder,
  page, totalPages, total, pageSize,
  rows, selectedPurls, allSelected, someSelected,
  editingPurl, editingValues,
  showImportModal, importFile, importStrategy, importResults, importLoading, importError,
} = storeToRefs(store)

const localPageSize = ref(pageSize.value)
const visiblePages = computed(() => {
  const pages: (number | string)[] = []
  const tp = totalPages.value
  if (tp <= 7) { for (let i = 1; i <= tp; i++) pages.push(i); return pages }
  pages.push(1)
  if (page.value > 3) pages.push('...')
  const start = Math.max(2, page.value - 1)
  const end = Math.min(tp - 1, page.value + 1)
  for (let i = start; i <= end; i++) pages.push(i)
  if (page.value < tp - 2) pages.push('...')
  pages.push(tp)
  return pages
})

function joinArray(arr: string[] | null | undefined): string {
  if (!arr || arr.length === 0) return '\u2014'
  return arr.join('; ')
}

function formatDate(iso: string): string {
  if (!iso) return '\u2014'
  const d = new Date(iso)
  const pad = (n: number) => n.toString().padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}
</script>
```

Keep the `<template>` and `<style>` sections unchanged from the current file.

- [ ] **Step 2: Update DatabaseAdmin.test.ts — add Pinia setup**

Add `import { setActivePinia, createPinia } from 'pinia'` and `setActivePinia(createPinia())` in `beforeEach`.

```ts
import { setActivePinia, createPinia } from 'pinia'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import DatabaseAdmin from './DatabaseAdmin.vue'
import { ApiError } from '../api/client'
import type { ResolveResponse, PurlListResponse } from '../types/api'

// ... (makeRow, rows, defaultListResponse, mocks all unchanged) ...

describe('DatabaseAdmin.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    listPurlsMock.mockResolvedValue(defaultListResponse)
    // ... rest unchanged
  })
  // ... all tests unchanged
})
```

- [ ] **Step 3: Remove `usePagination` composable and its test**

```bash
rm frontend/src/composables/usePagination.ts frontend/src/composables/usePagination.test.ts
```

Pagination logic is now part of `useDbAdminStore`.

- [ ] **Step 4: Run DatabaseAdmin tests**

```bash
npm test --prefix frontend -- src/views/DatabaseAdmin.test.ts
```
Expected: All tests pass (the template and DOM structure haven't changed, only the data source).

- [ ] **Step 5: Run full test suite**

```bash
npm test --prefix frontend
```
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/views/DatabaseAdmin.vue frontend/src/views/DatabaseAdmin.test.ts frontend/src/composables/
git commit -m "refactor: wire useDbAdminStore into DatabaseAdmin.vue, remove usePagination composable"
```

---

### Task 5: Decompose DatabaseAdmin.vue into sub-components

**Files:**
- Modify: `frontend/src/views/DatabaseAdmin.vue` — reduce to ~40-line layout shell
- Modify: `frontend/src/views/DatabaseAdmin.test.ts` — update selectors for new component tree
- Create: `frontend/src/components/db/DbFilterPanel.vue`
- Create: `frontend/src/components/db/DbDataTable.vue`
- Create: `frontend/src/components/db/DbImportModal.vue`

**Interfaces:**
- Consumes: `useDbAdminStore` (each sub-component calls it independently)
- Produces: new component tree with DatabaseAdmin.vue as thin shell

- [ ] **Step 1: Create `components/db/DbFilterPanel.vue`**

Extract the filter panel section from DatabaseAdmin.vue template (lines 6-44) plus its associated CSS (lines 613-656). All filter state is read/written via `useDbAdminStore()`.

```vue
<template>
  <div class="card filter-panel">
    <div class="filter-row">
      <div class="filter-group">
        <label for="search">Search by PURL</label>
        <input id="search" v-model="store.search" type="text" placeholder="e.g. requests" @keyup.enter="store.applyFilters()">
      </div>
      <div class="filter-group">
        <label for="resolver">Resolver</label>
        <select id="resolver" v-model="store.resolver">
          <option value="">Any</option>
          <option value="purl2repo">purl2repo</option>
        </select>
      </div>
      <div class="filter-group">
        <label for="confidence">Confidence</label>
        <select id="confidence" v-model="store.confidence">
          <option value="">Any</option>
          <option value="high">high</option>
          <option value="medium">medium</option>
          <option value="low">low</option>
        </select>
      </div>
      <div class="filter-group">
        <label for="date-from">Date From</label>
        <input id="date-from" v-model="store.dateFrom" type="date">
      </div>
      <div class="filter-group">
        <label for="date-to">Date To</label>
        <input id="date-to" v-model="store.dateTo" type="date">
      </div>
      <div class="filter-actions">
        <button class="btn btn-primary" @click="store.applyFilters()" :disabled="store.loading">
          <span v-if="store.loading" class="spinner"></span>
          <span v-else>Apply</span>
        </button>
        <button class="btn btn-secondary" @click="store.resetFilters()">Reset</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useDbAdminStore } from '../../stores/useDbAdminStore'
const store = useDbAdminStore()
</script>

<style scoped>
.filter-panel { margin-bottom: 1rem; }
.filter-row { display: flex; flex-wrap: wrap; gap: 0.75rem; align-items: flex-end; }
.filter-group { display: flex; flex-direction: column; gap: 0.25rem; }
.filter-group label { font-size: 0.8rem; color: var(--color-muted-light); text-transform: uppercase; }
.filter-group input, .filter-group select { padding: 0.5rem; border: 1px solid var(--color-input-border); border-radius: var(--border-radius); font-size: 0.9rem; min-width: 140px; }
.filter-group input:focus, .filter-group select:focus { outline: none; border-color: var(--color-primary); }
.filter-actions { display: flex; gap: 0.5rem; align-items: flex-end; padding-bottom: 1px; }
</style>
```

- [ ] **Step 2: Create `components/db/DbDataTable.vue`**

Extract: toolbar (lines 46-52), loading/error/success messages (lines 54-59), full table template (lines 61-165), pagination (lines 167-198), plus associated CSS (lines 658-889). Move helper functions (`joinArray`, `formatDate`, `visiblePages`) here.

```vue
<template>
  <div>
    <div class="toolbar">
      <button class="btn btn-secondary" :disabled="store.selectedPurls.size === 0" @click="handleExport">Export CSV ({{ store.selectedPurls.size }})</button>
      <button class="btn btn-secondary" @click="store.showImportModal = true">Import CSV</button>
      <button class="btn btn-danger" :disabled="store.selectedPurls.size === 0" @click="handleDeleteSelected">Delete Selected ({{ store.selectedPurls.size }})</button>
    </div>

    <div v-if="store.loading" class="loading"><span class="spinner"></span> Loading...</div>
    <div v-if="store.errorMessage" class="error-msg">{{ store.errorMessage }}</div>
    <div v-if="store.successMessage" class="success-msg">{{ store.successMessage }}</div>

    <div v-if="!store.loading" class="table-wrapper">
      <table>
        <thead>
          <tr>
            <th class="col-check">
              <input type="checkbox" :checked="store.allSelected" :indeterminate="store.someSelected" @change="handleToggleAll">
            </th>
            <th class="col-sortable" @click="store.setSort('purl')">PURL<span v-if="store.sortBy === 'purl'" class="sort-indicator">{{ store.sortOrder === 'asc' ? '\u25B2' : '\u25BC' }}</span></th>
            <th class="col-sortable" @click="store.setSort('repository_url')">Repository URL<span v-if="store.sortBy === 'repository_url'" class="sort-indicator">{{ store.sortOrder === 'asc' ? '\u25B2' : '\u25BC' }}</span></th>
            <th class="col-sortable" @click="store.setSort('resolver')">Resolver<span v-if="store.sortBy === 'resolver'" class="sort-indicator">{{ store.sortOrder === 'asc' ? '\u25B2' : '\u25BC' }}</span></th>
            <th class="col-sortable" @click="store.setSort('repository_type')">Type<span v-if="store.sortBy === 'repository_type'" class="sort-indicator">{{ store.sortOrder === 'asc' ? '\u25B2' : '\u25BC' }}</span></th>
            <th class="col-sortable" @click="store.setSort('repository_kind')">Kind<span v-if="store.sortBy === 'repository_kind'" class="sort-indicator">{{ store.sortOrder === 'asc' ? '\u25B2' : '\u25BC' }}</span></th>
            <th class="col-sortable" @click="store.setSort('confidence')">Confidence<span v-if="store.sortBy === 'confidence'" class="sort-indicator">{{ store.sortOrder === 'asc' ? '\u25B2' : '\u25BC' }}</span></th>
            <th class="col-sortable" @click="store.setSort('version_reference')">Version Ref<span v-if="store.sortBy === 'version_reference'" class="sort-indicator">{{ store.sortOrder === 'asc' ? '\u25B2' : '\u25BC' }}</span></th>
            <th>Evidence</th>
            <th>Warnings</th>
            <th class="col-sortable" @click="store.setSort('resolved_at')">Resolved At<span v-if="store.sortBy === 'resolved_at'" class="sort-indicator">{{ store.sortOrder === 'asc' ? '\u25B2' : '\u25BC' }}</span></th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in store.rows" :key="row.purl">
            <!-- checkboxes, inline-edit cells, action buttons — identical to current template -->
            <td class="col-check"><input type="checkbox" :checked="store.selectedPurls.has(row.purl)" @change="store.toggleRow(row.purl)"></td>
            <td @dblclick="handleDblclick(row, 'purl', $event)">
              <div v-if="store.editingPurl === row.purl">
                <input ref="editInput" v-model="store.editingValues.purl" class="inline-edit" @keydown="handleKeydown($event, row)" @blur="store.saveEdit(row)">
              </div>
              <span v-else>{{ row.purl }}</span>
            </td>
            <td @dblclick="handleDblclick(row, 'repository_url', $event)">
              <div v-if="store.editingPurl === row.purl">
                <input v-model="store.editingValues.repository_url" class="inline-edit" @keydown="handleKeydown($event, row)" @blur="store.saveEdit(row)">
              </div>
              <a v-else-if="row.repository_url" :href="safeUrl(row.repository_url)" target="_blank" class="repo-link" :title="row.repository_url">{{ row.repository_url }}</a>
              <span v-else class="null-value">\u2014</span>
            </td>
            <td>{{ row.resolver }}</td>
            <td>{{ row.repository_type || '\u2014' }}</td>
            <td>{{ row.repository_kind || '\u2014' }}</td>
            <td><span v-if="row.confidence" :class="['badge', 'badge-' + row.confidence]">{{ row.confidence }}</span><span v-else class="null-value">\u2014</span></td>
            <td>{{ row.version_reference || '\u2014' }}</td>
            <td :title="joinArray(row.evidence)">{{ truncate(joinArray(row.evidence)) }}</td>
            <td :title="joinArray(row.warnings)">{{ truncate(joinArray(row.warnings)) }}</td>
            <td class="cell-nowrap">{{ formatDate(row.resolved_at) }}</td>
            <td class="col-actions">
              <button class="btn btn-sm btn-secondary" @click="store.startEdit(row)">Edit</button>
              <button class="btn btn-sm btn-danger" @click="handleDeleteRow(row.purl)">Del</button>
            </td>
          </tr>
          <tr v-if="store.rows.length === 0"><td colspan="12" class="empty-row">No records found</td></tr>
        </tbody>
      </table>
    </div>

    <div class="pagination">
      <div class="pagination-info">Total: {{ store.total }} rows</div>
      <div class="pagination-controls">
        <button class="btn btn-sm" :disabled="store.page === 1" @click="store.goToPage(1)">&laquo; First</button>
        <button class="btn btn-sm" :disabled="store.page === 1" @click="store.goToPage(store.page - 1)">&lsaquo; Prev</button>
        <template v-for="(p, i) in visiblePages" :key="i">
          <span v-if="p === '...'" class="pagination-ellipsis">...</span>
          <button v-else :class="['btn', 'btn-sm', p === store.page ? 'btn-active' : '']" @click="store.goToPage(p as number)">{{ p }}</button>
        </template>
        <button class="btn btn-sm" :disabled="store.page === store.totalPages" @click="store.goToPage(store.page + 1)">Next &rsaquo;</button>
        <button class="btn btn-sm" :disabled="store.page === store.totalPages" @click="store.goToPage(store.totalPages)">Last &raquo;</button>
      </div>
      <div class="pagination-size">
        <label>Per page: <select v-model.number="localPageSize" @change="onPageSizeChange"><option :value="25">25</option><option :value="50">50</option><option :value="100">100</option><option :value="200">200</option></select></label>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick } from 'vue'
import { useDbAdminStore } from '../../stores/useDbAdminStore'
import { safeUrl } from '../../composables/useDownload'
import type { ResolveResponse } from '../../types/api'

const store = useDbAdminStore()
const localPageSize = ref(store.pageSize)
const editInput = ref<HTMLInputElement | null>(null)

const visiblePages = computed(() => {
  const pages: (number | string)[] = []
  const tp = store.totalPages
  if (tp <= 7) { for (let i = 1; i <= tp; i++) pages.push(i); return pages }
  pages.push(1)
  if (store.page > 3) pages.push('...')
  const start = Math.max(2, store.page - 1)
  const end = Math.min(tp - 1, store.page + 1)
  for (let i = start; i <= end; i++) pages.push(i)
  if (store.page < tp - 2) pages.push('...')
  pages.push(tp)
  return pages
})

function joinArray(arr: string[] | null | undefined): string {
  if (!arr || arr.length === 0) return '\u2014'
  return arr.join('; ')
}

function truncate(val: string, max = 80): string {
  return val.length <= max ? val : val.substring(0, max) + '...'
}

function formatDate(iso: string): string {
  if (!iso) return '\u2014'
  const d = new Date(iso)
  const pad = (n: number) => n.toString().padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

function handleToggleAll(event: Event) {
  store.toggleSelectAll((event.target as HTMLInputElement).checked)
}

function handleDblclick(row: ResolveResponse, field: 'purl' | 'repository_url', event: MouseEvent) {
  store.startEdit(row)
  if (field === 'repository_url') store.editingValues.repository_url = row.repository_url || ''
  nextTick(() => {
    const target = event.target as HTMLElement
    const input = target.closest('td')?.querySelector('input')
    input?.focus()
    input?.select()
  })
}

function handleKeydown(event: KeyboardEvent, row: ResolveResponse) {
  if (event.key === 'Enter') store.saveEdit(row)
  else if (event.key === 'Escape') store.cancelEdit()
}

function handleDeleteRow(purl: string) {
  if (!confirm(`Delete record "${purl}"? This cannot be undone.`)) return
  store.deleteRow(purl)
}

function handleDeleteSelected() {
  if (!confirm(`Delete ${store.selectedPurls.size} selected record(s)? This cannot be undone.`)) return
  store.deleteSelected()
}

async function handleExport() {
  const blob = await store.exportCsv()
  if (!blob) return
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'purls_export.csv'
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

function onPageSizeChange() {
  store.changePageSize(localPageSize.value)
}
</script>

<style scoped>
/* Copy all CSS from DatabaseAdmin.vue lines 658-889 (toolbar, table, pagination styles) */
</style>
```

- [ ] **Step 3: Create `components/db/DbImportModal.vue`**

Extract the import modal section (lines 200-264) plus associated CSS (lines 891-964). Uses existing `ModalDialog` and `FileUploadZone`.

```vue
<template>
  <ModalDialog :show="store.showImportModal" title="Import CSV" @close="store.closeImportModal()">
    <FileUploadZone accept=".csv" @file-selected="store.handleImportFile" />

    <details class="csv-ref">
      <summary>CSV Format Reference</summary>
      <div class="csv-ref-content">
        <p>The CSV file must have a header row. Comma (<code>,</code>) delimiter. UTF-8 encoding (BOM handled automatically).</p>
        <p>Required columns:</p>
        <ul><li><code>purl</code> — Package URL</li><li><code>repository_url</code> — Repository URL</li></ul>
        <p>Optional columns:</p>
        <ul>
          <li><code>repository_type</code> — e.g. <code>github</code>, <code>gitlab</code></li>
          <li><code>repository_kind</code> — e.g. <code>source_code</code></li>
          <li><code>confidence</code> — <code>high</code>, <code>medium</code>, or <code>low</code></li>
          <li><code>version_reference</code> — version tag/branch/SHA</li>
          <li><code>resolver</code> — resolver name (default: <code>import-csv</code>)</li>
          <li><code>evidence</code> — JSON array, e.g. <code>["homepage","description"]</code></li>
          <li><code>warnings</code> — JSON array, e.g. <code>["low_confidence"]</code></li>
        </ul>
        <p>Example:</p>
        <pre>purl,repository_url,confidence,resolver
pkg:pypi/requests@2.31.0,https://github.com/psf/requests,high,import-csv
pkg:pypi/flask@2.3.0,https://github.com/pallets/flask,medium,import-csv</pre>
      </div>
    </details>

    <div class="import-strategy">
      <label class="radio-label"><input type="radio" v-model="store.importStrategy" value="upsert"> Overwrite existing</label>
      <label class="radio-label"><input type="radio" v-model="store.importStrategy" value="skip_existing"> Skip existing</label>
    </div>

    <div class="toolbar">
      <button class="btn btn-primary" :disabled="!store.importFile || store.importLoading" @click="store.handleImportUpload()">
        {{ store.importLoading ? 'Uploading...' : 'Upload' }}
      </button>
    </div>

    <div v-if="store.importLoading" class="loading"><span class="spinner"></span> Importing...</div>
    <div v-if="store.importError" class="error-msg">{{ store.importError }}</div>

    <div v-if="store.importResults" class="import-results">
      <div class="import-stat">Imported: <strong>{{ store.importResults.imported }}</strong></div>
      <div class="import-stat">Skipped: <strong>{{ store.importResults.skipped }}</strong></div>
      <div v-if="store.importResults.errors.length" class="import-errors">
        <div class="import-stat import-stat-error">Errors: <strong>{{ store.importResults.errors.length }}</strong></div>
        <ul><li v-for="err in store.importResults.errors" :key="err.row">Row {{ err.row }}: {{ err.error }}</li></ul>
      </div>
    </div>
  </ModalDialog>
</template>

<script setup lang="ts">
import { useDbAdminStore } from '../../stores/useDbAdminStore'
import ModalDialog from '../ModalDialog.vue'
import FileUploadZone from '../FileUploadZone.vue'

const store = useDbAdminStore()
</script>

<style scoped>
/* Copy all CSS from DatabaseAdmin.vue lines 891-964 (csv-ref, import-strategy, import-results) */
</style>
```

- [ ] **Step 4: Rewrite `DatabaseAdmin.vue` as a thin shell**

```vue
<template>
  <div class="db-admin">
    <h1>Database Admin</h1>
    <p class="subtitle">View, edit, filter, import, and export the resolved_purls table</p>

    <DbFilterPanel />
    <DbDataTable />
    <DbImportModal />
  </div>
</template>

<script setup lang="ts">
import DbFilterPanel from '../components/db/DbFilterPanel.vue'
import DbDataTable from '../components/db/DbDataTable.vue'
import DbImportModal from '../components/db/DbImportModal.vue'
</script>

<style scoped>
.db-admin { max-width: 1400px; margin: 0 auto; padding: 2rem 1rem; flex: 1; }
h1 { font-size: 1.5rem; margin-bottom: 0.25rem; }
.subtitle { color: var(--color-muted); margin-bottom: 1.5rem; }
</style>
```

- [ ] **Step 5: Update `DatabaseAdmin.test.ts` for new component tree**

The test structure changes because:
1. DOM selectors like `.table-wrapper`, `.pagination-controls`, `.toolbar` are now inside sub-components
2. `wrapper.find('#search')` needs `.findComponent(DbFilterPanel).find('#search')` or `wrapper.findComponent()` depth

Replace the `mountAdmin` helper and the import section:

```ts
import { setActivePinia, createPinia } from 'pinia'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import DatabaseAdmin from './DatabaseAdmin.vue'
import DbFilterPanel from '../components/db/DbFilterPanel.vue'
import DbDataTable from '../components/db/DbDataTable.vue'
import DbImportModal from '../components/db/DbImportModal.vue'
import { ApiError } from '../api/client'
import type { ResolveResponse, PurlListResponse } from '../types/api'

// ... (makeRow, rows, defaultListResponse, mocks unchanged) ...

function mountAdmin() {
  return mount(DatabaseAdmin, {
    global: {
      stubs: {
        DbFilterPanel,
        DbDataTable,
        DbImportModal,
      },
    },
  })
}
```

Keep all test cases the same — the selectors still work because `find` traverses the full rendered DOM tree (including sub-component slots). Key selectors to verify:
- `wrapper.find('#search')` — inside `DbFilterPanel`, still reachable via `find` (scoped traversal)
- `wrapper.find('.table-wrapper')` — inside `DbDataTable`, still reachable
- `wrapper.find('.error-msg')` — inside `DbDataTable`, still reachable
- `wrapper.findComponent({ name: 'FileUploadZone' })` — inside `DbImportModal`, use `wrapper.findComponent(DbImportModal).findComponent({ name: 'FileUploadZone' })`

Test cases requiring deeper traversal need `.findComponent()` chaining. For example, filter tests that originally did `wrapper.find('#search')` should now use:

```ts
const fp = wrapper.findComponent(DbFilterPanel)
await fp.find('#search').setValue('requests')
await fp.findAll('.filter-actions button').find((b) => b.text() === 'Apply')!.trigger('click')
```

And import modal tests:

```ts
const importModal = wrapper.findComponent(DbImportModal)
await importModal.findComponent({ name: 'FileUploadZone' }).vm.$emit('file-selected', file)
// document.querySelector still works for modal-in-body patterns
```

- [ ] **Step 6: Run full test suite**

```bash
npm test --prefix frontend
```
Expected: All tests pass.

- [ ] **Step 7: Build check**

```bash
npm run build --prefix frontend 2>&1 | head -30
```
Expected: Build succeeds.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/views/DatabaseAdmin.vue frontend/src/views/DatabaseAdmin.test.ts frontend/src/components/db/
git commit -m "refactor: decompose DatabaseAdmin.vue into DbFilterPanel, DbDataTable, DbImportModal"
```

---

### Task order verification

| Task | Depends on | Testable independently |
|---|---|---|
| 1. `apiFetch` | Nothing | Yes (same interface) |
| 2. Pinia + stores | Task 1 | Yes (stores compile) |
| 3. Settings.vue → Pinia | Task 2 | Yes (Settings.test.ts) |
| 4. DatabaseAdmin.vue → Pinia | Task 2 | Yes (DatabaseAdmin.test.ts) |
| 5. Decompose DatabaseAdmin | Task 4 | Yes (DatabaseAdmin.test.ts) |

Tasks 3 and 4 are independent of each other and could be run in parallel.