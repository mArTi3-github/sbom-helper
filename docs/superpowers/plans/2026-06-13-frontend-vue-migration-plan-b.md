# Plan B Implementation: Frontend Vue Migration — Complex Pages + Integration

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the Vue 3 SPA migration — implement SBOM Updater (Phase 4), Database Admin (Phase 5), and cleanup (Phase 6).

**Architecture:** Vue 3 + Vite + TypeScript SPA served by FastAPI as static files. Two new API modules (`sbom.ts`, `db.ts`) mirroring backend endpoints. DB Admin uses a `usePagination` composable. All new types added to `types/api.ts`.

**Tech Stack:** Vue 3, Vue Router 4, TypeScript, Vite, FastAPI

---

## File Structure

### New/Modified files:

| File | Action | Responsibility |
|---|---|---|
| `frontend/src/types/api.ts` | Modify | Add `SbomSummary`, `SbomResultItem`, `SbomResponse`, `IgnorePatternItem`, `PurlListResponse`, `PurlUpdateRequest`, `DeleteResponse`, `ImportResponse`, `ImportErrorItem` |
| `frontend/src/api/sbom.ts` | Create | `getIgnorePatterns()`, `saveIgnorePatterns()`, `resolveSbom()` |
| `frontend/src/api/db.ts` | Create | `listPurls()`, `updatePurl()`, `deletePurls()`, `importCsv()`, `exportCsv()` |
| `frontend/src/composables/usePagination.ts` | Create | Reactive pagination state: `page`, `pageSize`, `total`, `goToPage()`, `changePageSize()` |
| `frontend/src/views/SbomUpdater.vue` | Rewrite | Replace stub with full SBOM enrichment UI |
| `frontend/src/views/DatabaseAdmin.vue` | Rewrite | Replace stub with full DB admin UI (filters, table, pagination, inline edit, CSV import/export) |
| `Dockerfile` | Modify | Add `frontend-build` stage (node:20-alpine) + copy dist to prod stage |
| `src/purl_resolver/router.py` | Modify | Add StaticFiles mount, remove Jinja2Templates, remove TemplateResponse routes |
| `pyproject.toml` | Modify | Remove `jinja2` dependency, remove `templates` from `[tool.setuptools.package-data]` |
| `README.md` | Modify | Add dev workflow with `npm run build -- --watch` |
| `CONTEXT.md` | Modify | Update project structure |

### Files to delete:

| File | Reason |
|---|---|
| `src/purl_resolver/templates/index.html` | Replaced by Vue SPA |
| `src/purl_resolver/templates/sbom.html` | Replaced by Vue SPA |
| `src/purl_resolver/templates/db-admin.html` | Replaced by Vue SPA |
| `src/purl_resolver/templates/settings.html` | Replaced by Vue SPA |
| `src/purl_resolver/templates/images-list-converter.html` | Replaced by Vue SPA |

---

## Task 1: Add SBOM and DB types to types/api.ts

**Files:**
- Modify: `frontend/src/types/api.ts`

- [ ] **Add SBOM-related types after existing `ImagesListResponse`**

```typescript
export interface IgnorePatternItem {
  field: string
  pattern: string
}

export interface SbomSummary {
  total_purls: number
  found: number
  not_found: number
  skipped: number
  removed: number
  ignored: number
}

export interface SbomResultItem {
  purl: string
  status: 'found' | 'not_found' | 'removed' | 'ignored'
  repository_url: string | null
  found_by?: string
  resolver?: string
  name?: string
  version?: string
}

export interface SbomResponse {
  summary: SbomSummary
  results: SbomResultItem[]
  enriched_sbom: unknown
}
```

- [ ] **Add DB Admin types after `SbomResponse`**

```typescript
export interface PurlListResponse {
  rows: ResolveResponse[]
  total: number
  page: number
  page_size: number
}

export interface PurlUpdateRequest {
  purl?: string | null
  repository_url?: string | null
}

export interface PurlDeleteRequest {
  purls: string[]
}

export interface DeleteResponse {
  deleted: number
}

export interface ImportErrorItem {
  row: number
  error: string
}

export interface ImportResponse {
  imported: number
  skipped: number
  errors: ImportErrorItem[]
}
```

- [ ] **Verify:** `cd frontend && npx vue-tsc --noEmit` passes without errors

---

## Task 2: Create api/sbom.ts

**Files:**
- Create: `frontend/src/api/sbom.ts`

- [ ] **Create the SBOM API module**

```typescript
import { request } from './client'
import type { IgnorePatternItem, SbomResponse } from '../types/api'

export function getIgnorePatterns(): Promise<{ patterns: IgnorePatternItem[] }> {
  return request<{ patterns: IgnorePatternItem[] }>('/api/v1/sbom/ignore-patterns')
}

export function saveIgnorePatterns(patterns: IgnorePatternItem[]): Promise<{ status: string }> {
  return request<{ status: string }>('/api/v1/sbom/ignore-patterns', {
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
  if (ignorePatterns.length > 0) {
    formData.append('ignore_patterns', JSON.stringify(ignorePatterns))
  }
  return request<SbomResponse>('/api/v1/resolve/sbom', {
    method: 'POST',
    body: formData,
    signal,
  })
}
```

- [ ] **Verify:** `cd frontend && npx vue-tsc --noEmit` passes

---

## Task 3: Create api/db.ts

**Files:**
- Create: `frontend/src/api/db.ts`

- [ ] **Create the DB Admin API module**

```typescript
import { request } from './client'
import type { PurlListResponse, PurlUpdateRequest, DeleteResponse, ImportResponse } from '../types/api'

export interface PurlListParams {
  page: number
  page_size: number
  search?: string
  resolver?: string
  confidence?: string
  date_from?: string
  date_to?: string
  sort_by?: string
  sort_order?: string
}

export function listPurls(params: PurlListParams): Promise<PurlListResponse> {
  const query = new URLSearchParams()
  query.set('page', String(params.page))
  query.set('page_size', String(params.page_size))
  if (params.search) query.set('search', params.search)
  if (params.resolver) query.set('resolver', params.resolver)
  if (params.confidence) query.set('confidence', params.confidence)
  if (params.date_from) query.set('date_from', params.date_from)
  if (params.date_to) query.set('date_to', params.date_to)
  if (params.sort_by) query.set('sort_by', params.sort_by)
  if (params.sort_order) query.set('sort_order', params.sort_order)
  return request<PurlListResponse>(`/api/v1/db/purls?${query.toString()}`)
}

export function updatePurl(purl: string, body: PurlUpdateRequest): Promise<{ ok: boolean }> {
  const encoded = encodeURIComponent(purl).replace(/%2F/g, '/')
  return request<{ ok: boolean }>(`/api/v1/db/purls/${encoded}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export function deletePurls(purls: string[]): Promise<DeleteResponse> {
  return request<DeleteResponse>('/api/v1/db/purls', {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ purls }),
  })
}

export function importCsv(file: File, strategy: 'upsert' | 'skip_existing'): Promise<ImportResponse> {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('strategy', strategy)
  return request<ImportResponse>('/api/v1/db/import', {
    method: 'POST',
    body: formData,
  })
}

export function exportCsv(params: PurlListParams): Promise<Blob> {
  const query = new URLSearchParams()
  if (params.search) query.set('search', params.search)
  if (params.resolver) query.set('resolver', params.resolver)
  if (params.confidence) query.set('confidence', params.confidence)
  if (params.date_from) query.set('date_from', params.date_from)
  if (params.date_to) query.set('date_to', params.date_to)
  if (params.sort_by) query.set('sort_by', params.sort_by)
  if (params.sort_order) query.set('sort_order', params.sort_order)
  return fetch(`/api/v1/db/export?${query.toString()}`).then(r => {
    if (!r.ok) throw new Error('Export failed')
    return r.blob()
  })
}
```

- [ ] **Verify:** `cd frontend && npx vue-tsc --noEmit` passes

---

## Task 4: Create usePagination composable

**Files:**
- Create: `frontend/src/composables/usePagination.ts`

- [ ] **Create the pagination composable**

```typescript
import { ref, computed } from 'vue'

export function usePagination() {
  const page = ref(1)
  const pageSize = ref(50)
  const total = ref(0)

  const totalPages = computed(() => Math.ceil(total.value / pageSize.value) || 1)

  function goToPage(p: number) {
    if (p < 1 || p > totalPages.value) return
    page.value = p
  }

  function changePageSize(size: number) {
    pageSize.value = size
    page.value = 1
  }

  function reset() {
    page.value = 1
  }

  return { page, pageSize, total, totalPages, goToPage, changePageSize, reset }
}
```

- [ ] **Verify:** `cd frontend && npx vue-tsc --noEmit` passes

---

## Task 5: Rewrite SbomUpdater.vue

**Files:**
- Modify: `frontend/src/views/SbomUpdater.vue` (replace stub)

- [ ] **Write the template** with:
  - Title and subtitle
  - FileUploadZone component
  - Checkboxes for options (remove unresolved, validate refs)
  - Ignore patterns editor (dynamic rows with field+pattern inputs, add/delete, save button)
  - Process button
  - Loading spinner
  - Error display
  - Results section: SummaryCard (total, found, not_found, skipped, removed, ignored), result table (PURL, Status, Repository URL, Found by, Resolver), Download button

- [ ] **Write the script** with:
  - `ref` for all reactive state (selectedFile, loading, error, results, patterns, enrichedSbom)
  - `onMounted` to load ignore patterns via `getIgnorePatterns()`
  - `handleFileSelected(file)` — store file, reset results
  - `addPatternRow()` / `removePatternRow(index)` / `savePatterns()` for ignore patterns
  - `collectPatterns()` — read current pattern rows
  - `handleProcess()` — collect form data, call `resolveSbom()` with AbortController
  - `downloadResult()` — blob URL for enriched SBOM
  - `onUnmounted()` → abort controller

- [ ] **Verify:** `cd frontend && npx vue-tsc --noEmit` passes
- [ ] **Verify:** `cd frontend && npm run build` succeeds

---

## Task 6: Rewrite DatabaseAdmin.vue

**Files:**
- Modify: `frontend/src/views/DatabaseAdmin.vue` (replace stub)

- [ ] **Write the template** with:
  - Filter panel: search input, resolver select, confidence select, date from/to, Apply/Reset buttons
  - Toolbar: Refresh, Export CSV, Import CSV, Delete Selected
  - Loading spinner
  - Error/success messages
  - Table with: checkbox column, all 10 data columns (purl, repository_url, resolver, repository_type, repository_kind, confidence, version_reference, evidence, warnings, resolved_at), actions column
  - Sortable column headers (click to sort asc/desc)
  - Inline editing: double-click on purl or repo_url → input field → save on Enter/blur
  - Row-level edit/delete buttons
  - Pagination: prev/next, page numbers, page size selector, total rows
  - Import CSV modal (ModalDialog + FileUploadZone + strategy radio + upload button + results)

- [ ] **Write the script** with:
  - `usePagination()` composable
  - Filter refs: `search`, `resolver`, `confidence`, `dateFrom`, `dateTo`
  - `sortBy` / `sortOrder` refs
  - `selectedRows` (Set of purls)
  - `editingRow` ref (currently editing purl, or null)
  - `editingValues` ref (temp values during edit)
  - `allRows` ref, `error` ref, `successMessage` ref
  - Import modal state refs
  - `fetchData()` — call `listPurls()` with filters + pagination + sort
  - `applyFilters()` / `resetFilters()` — reset page and re-fetch
  - `setSort(column)` — toggle sort
  - `toggleSelectAll()` / `toggleRow(purl)` — selection logic
  - `startEdit(row)` / `cancelEdit()` / `saveEdit(row)` — inline editing
  - `deleteRow(purl)` — single delete with confirm
  - `deleteSelected()` — bulk delete with confirm
  - `exportCsv()` — blob download
  - `importCsv()` — modal upload logic

- [ ] **Verify:** `cd frontend && npx vue-tsc --noEmit` passes
- [ ] **Verify:** `cd frontend && npm run build` succeeds

---

## Task 7: Docker integration — frontend build stage

**Files:**
- Modify: `Dockerfile`

- [ ] **Add frontend-build stage BEFORE all existing stages:**

```dockerfile
FROM node:20-alpine AS frontend-build
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build
```

- [ ] **Add copy to dev stage** (after `COPY scripts/ ./scripts/` line in the dev stage):

```dockerfile
COPY --from=frontend-build /frontend/dist/ /app/frontend/dist/
```

- [ ] **Add copy to prod stage** (after `COPY scripts/ ./scripts/` line in the prod stage):

```dockerfile
COPY --from=frontend-build /frontend/dist/ /app/frontend/dist/
```

Note: Both stages need the dist because `docker-compose.override.yml` sets `target: dev` and `docker-compose.yml` defaults to `target: prod`.

- [ ] **Verify:** `docker compose build` succeeds

---

## Task 8: FastAPI — static serving + cleanup

**Files:**
- Modify: `src/purl_resolver/router.py`

- [ ] **Replace the router.py** — add StaticFiles mount, remove Jinja2:

```python
from __future__ import annotations

import pathlib

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .routes.db_admin import router as db_admin_router
from .routes.ignore_patterns import router as ignore_patterns_router
from .routes.images_list import router as images_list_router
from .routes.resolve import router as resolve_router
from .routes.settings import router as settings_router

router = APIRouter()

router.include_router(resolve_router)
router.include_router(db_admin_router)
router.include_router(settings_router)
router.include_router(images_list_router)
router.include_router(ignore_patterns_router)


@router.get("/health")
async def health() -> JSONResponse:
    return JSONResponse(content={"status": "ok"})


SPA_DIR = pathlib.Path(__file__).resolve().parent.parent.parent.parent / "frontend" / "dist"
if SPA_DIR.exists():
    router.mount("/", StaticFiles(directory=str(SPA_DIR), html=True), name="spa")
```

Note: The `SPA_DIR` path assumes `router.py` is at `src/purl_resolver/router.py` and `frontend/dist` is at the repo root.

- [ ] **Remove templates directory** — delete all files in `src/purl_resolver/templates/`

- [ ] **Verify:** `docker compose build` succeeds

---

## Task 9: Clean up pyproject.toml

**Files:**
- Modify: `pyproject.toml`

- [ ] **Remove jinja2 dependency** from `[project] dependencies`:

```
-    "jinja2>=3.1.0",
```

- [ ] **Remove `templates/*.html` from `[tool.setuptools.package-data]`** :

```toml
[tool.setuptools.package-data]
purl_resolver = ["storage/schema.sql"]
```

- [ ] **Verify:** `pip install -e ".[dev]"` or `docker compose build` succeeds

---

## Task 10: Verify full application

- [ ] **Build the frontend:** `cd frontend && npm run build`
- [ ] **Build Docker image:** `docker compose build`
- [ ] **Start the service:** `docker compose up -d`
- [ ] **Test all 5 pages:**
  - `https://localhost:8443/` — PURL Resolver loads
  - `https://localhost:8443/sbom-updater` — SBOM Updater loads
  - `https://localhost:8443/db-admin` — Database Admin loads
  - `https://localhost:8443/settings` — Settings loads
  - `https://localhost:8443/images-list-converter` — Images List Converter loads
  - `https://localhost:8443/nonexistent` — 404 page loads

---

## Task 11: Update documentation

- [ ] **Update README.md** — describe dev workflow (npm run build -- --watch + docker compose up, or docker compose up --build)
- [ ] **Update CONTEXT.md** — reflect new project structure with frontend/ directory and SPA architecture