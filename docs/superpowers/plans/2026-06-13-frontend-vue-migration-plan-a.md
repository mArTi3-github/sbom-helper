# Plan A: Frontend Migration to Vue 3 SPA — Simple Pages

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a Vue 3 SPA scaffold and migrate 3 pages (Settings, PURL Resolver, Images List Converter) from Jinja2+VanillaJS to Vue 3 + TypeScript, served by the existing FastAPI backend.

**Architecture:** Vue 3 SPA with Vite + TypeScript, Vue Router for client-side navigation. FastAPI serves built static files via `StaticFiles(html=True)`. Coexistence: Jinja2 templates remain functional; SPA pages are accessed at the same routes. No extra nginx container, no CSS framework, no Pinia.

**Tech Stack:** Vue 3 (Composition API + `<script setup>`), Vite, TypeScript, Vue Router 4, existing FastAPI backend with zero backend changes.

---

## File Structure

```
frontend/                          # NEW directory
├── index.html                     # Vite entry
├── package.json
├── tsconfig.json                  # extends tsconfig.app.json + tsconfig.node.json
├── tsconfig.app.json
├── tsconfig.node.json
├── vite.config.ts
├── env.d.ts
├── public/
│   └── favicon.ico
└── src/
    ├── main.ts                    # createApp + router
    ├── App.vue                    # AppNav + <router-view>
    ├── assets/
    │   └── main.css               # CSS variables from existing design
    ├── router/
    │   └── index.ts               # 5 routes + 404 (Settings, PurlResolver, ImagesListConverter active; SbomUpdater, DatabaseAdmin as stubs)
    ├── types/
    │   └── api.ts                 # TypeScript interfaces mirroring schemas.py
    ├── api/
    │   ├── client.ts              # fetch wrapper: request<T>() + ApiError
    │   ├── settings.ts            # getSettings, updateSettings
    │   ├── purl.ts                # resolvePurl
    │   └── images.ts              # convertImagesList
    ├── components/
    │   ├── AppNav.vue             # Navigation bar (5 links, active state)
    │   ├── FileUploadZone.vue     # Drag-and-drop + file select
    │   └── ModalDialog.vue        # Reusable modal (needed by Plan B, scaffold now)
    └── views/
        ├── Settings.vue           # 6 setting cards
        ├── PurlResolver.vue       # Single PURL resolve
        ├── ImagesListConverter.vue # SBOM → images list
        ├── SbomUpdater.vue        # STUB: placeholder message
        ├── DatabaseAdmin.vue      # STUB: placeholder message
        └── NotFound.vue           # 404
```

## Implementation Tasks

### Task 1: Scaffold Vite + Vue 3 + TypeScript project

**Files:**
- Create: `frontend/` (entire directory structure via Vite scaffold)
- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`, `tsconfig.app.json`, `tsconfig.node.json`
- Create: `frontend/env.d.ts`
- Create: `frontend/index.html`
- Create: `frontend/src/main.ts`

- [ ] **Step 1: Scaffold with Vite**

Run:
```bash
cd /home/administrator/Desktop/projects/sbom-helper
npm create vite@latest frontend -- --template vue-ts
cd frontend
```

This creates `frontend/` with the vue-ts template: `package.json`, `tsconfig*.json`, `vite.config.ts`, `index.html`, `src/main.ts`, `src/App.vue`, `src/assets/vue.svg`, `src/components/HelloWorld.vue`, `env.d.ts`.

- [ ] **Step 2: Install vue-router**

Run:
```bash
cd /home/administrator/Desktop/projects/sbom-helper/frontend
npm install vue-router@4
```

- [ ] **Step 3: Configure vite.config.ts**

Write `frontend/vite.config.ts`:
```ts
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  base: '/',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
```

- [ ] **Step 4: Clean up scaffold files**

Remove `frontend/src/components/HelloWorld.vue`, `frontend/src/assets/vue.svg`, `frontend/src/style.css` (if created).

- [ ] **Step 5: Create global CSS**

Write `frontend/src/assets/main.css` with CSS variables extracted from existing templates. Include: `:root` variables for colors (primary `#2563eb`, danger `#dc2626`, success `#166534`, warning `#854d0e`), base reset, card styles, badge styles, spinner animation, toggle switch styles.

Source the values from the existing templates — they are consistent across all 5 HTML files.

- [ ] **Step 6: Update main.ts**

Write `frontend/src/main.ts`:
```ts
import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import './assets/main.css'

const app = createApp(App)
app.use(router)
app.mount('#app')
```

- [ ] **Step 7: Verify scaffold builds**

Run:
```bash
cd /home/administrator/Desktop/projects/sbom-helper/frontend
npm run build
```
Expected: `frontend/dist/` directory created with `index.html` and `assets/` containing JS/CSS bundles.

### Task 2: API Types and Client

**Files:**
- Create: `frontend/src/types/api.ts`
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/api/settings.ts`
- Create: `frontend/src/api/purl.ts`
- Create: `frontend/src/api/images.ts`

- [ ] **Step 1: Create TypeScript types**

Write `frontend/src/types/api.ts`:
```ts
// Mirror of src/purl_resolver/schemas.py

export interface ResolveRequest {
  purl: string
}

export interface ResolveResponse {
  purl: string
  repository_url: string | null
  repository_type: string | null
  repository_kind: string | null
  confidence: string | null
  evidence: string[]
  warnings: string[]
  version_reference: string | null
  resolver: string
  found_by: string
  resolved_at: string
}

export interface ErrorResponse {
  error: string
  message: string
}

// ========== Settings ==========
export interface SettingsTokenSet {
  github_token: boolean
  librariesio_api_key: boolean
  ecosystems_api_key: boolean
}

export interface SettingsResponse {
  validate_db_urls: boolean
  url_validation_timeout: number
  revalidation_cooldown_hours: number
  retry_max_attempts: number
  retry_base_cooldown_seconds: number
  log_level: string
  librariesio_enabled: boolean
  ecosystems_enabled: boolean
  ecosystems_max_requests_per_second: number
  token_set: SettingsTokenSet
}

export interface SettingsUpdate {
  validate_db_urls?: boolean
  url_validation_timeout?: number
  github_token?: string | null
  librariesio_enabled?: boolean
  librariesio_api_key?: string | null
  ecosystems_enabled?: boolean
  ecosystems_api_key?: string | null
  ecosystems_max_requests_per_second?: number
  revalidation_cooldown_hours?: number
  retry_max_attempts?: number
  retry_base_cooldown_seconds?: number
  log_level?: string
}

// ========== Images List ==========
export interface ImageItem {
  name: string | null
  version: string | null
  missing_components: boolean
  missing_name: boolean
  missing_version: boolean
  missing_properties: boolean
}

export interface ImagesListResponse {
  was_transformed: boolean
  images: ImageItem[]
  images_list: unknown
}
```

- [ ] **Step 2: Create API client**

Write `frontend/src/api/client.ts`:
```ts
export class ApiError extends Error {
  constructor(
    public status: number,
    public error: string,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

export async function request<T>(
  url: string,
  options?: RequestInit,
): Promise<T> {
  const res = await fetch(url, options)

  if (!res.ok) {
    let errorData: { error?: string; message?: string } = {}
    try {
      errorData = await res.json()
    } catch {
      // ignore parse errors
    }
    throw new ApiError(
      res.status,
      errorData.error || 'unknown_error',
      errorData.message || `HTTP ${res.status}`,
    )
  }

  return res.json() as Promise<T>
}
```

- [ ] **Step 3: Create API modules**

Write `frontend/src/api/settings.ts`:
```ts
import { request } from './client'
import type { SettingsResponse, SettingsUpdate } from '../types/api'

export function getSettings(): Promise<SettingsResponse> {
  return request<SettingsResponse>('/api/v1/settings')
}

export function updateSettings(body: SettingsUpdate): Promise<SettingsResponse> {
  return request<SettingsResponse>('/api/v1/settings', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}
```

Write `frontend/src/api/purl.ts`:
```ts
import { request } from './client'
import type { ResolveRequest, ResolveResponse } from '../types/api'

export function resolvePurl(body: ResolveRequest): Promise<ResolveResponse> {
  return request<ResolveResponse>('/api/v1/resolve', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}
```

Write `frontend/src/api/images.ts`:
```ts
import { request } from './client'
import type { ImagesListResponse } from '../types/api'

export function convertImagesList(file: File): Promise<ImagesListResponse> {
  const formData = new FormData()
  formData.append('file', file)
  return request<ImagesListResponse>('/api/v1/convert/images-list', {
    method: 'POST',
    body: formData,
  })
}
```

### Task 3: Router, App.vue, Shared Components

**Files:**
- Create: `frontend/src/router/index.ts`
- Create: `frontend/src/App.vue`
- Create: `frontend/src/components/AppNav.vue`
- Create: `frontend/src/components/FileUploadZone.vue`
- Create: `frontend/src/components/ModalDialog.vue`

- [ ] **Step 1: Create router**

Write `frontend/src/router/index.ts`:
```ts
import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'purl-resolver',
      component: () => import('../views/PurlResolver.vue'),
    },
    {
      path: '/settings',
      name: 'settings',
      component: () => import('../views/Settings.vue'),
    },
    {
      path: '/images-list-converter',
      name: 'images-list-converter',
      component: () => import('../views/ImagesListConverter.vue'),
    },
    {
      path: '/sbom-updater',
      name: 'sbom-updater',
      component: () => import('../views/SbomUpdater.vue'),
    },
    {
      path: '/db-admin',
      name: 'db-admin',
      component: () => import('../views/DatabaseAdmin.vue'),
    },
    {
      path: '/:pathMatch(.*)*',
      name: 'not-found',
      component: () => import('../views/NotFound.vue'),
    },
  ],
})

export default router
```

- [ ] **Step 2: Create App.vue**

Write `frontend/src/App.vue`:
```vue
<script setup lang="ts">
import AppNav from './components/AppNav.vue'
</script>

<template>
  <div class="app-layout">
    <AppNav />
    <main class="container">
      <router-view />
    </main>
    <footer class="app-footer">Powered by sbom-helper</footer>
  </div>
</template>

<style scoped>
.app-layout {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}
.container {
  max-width: 960px;
  margin: 0 auto;
  padding: 2rem 1rem;
  flex: 1;
  width: 100%;
}
.app-footer {
  text-align: center;
  padding: 1rem;
  color: #999;
  font-size: 0.8rem;
}
</style>
```

The `max-width` on `.container` should be `720px` for Settings and PURL Resolver, `960px` for ImagesListConverter. Use a prop or computed class based on route — or simply use `960px` as default (it works fine for all pages, just wider cards on Settings/PURL).

- [ ] **Step 3: Create AppNav.vue**

Write `frontend/src/components/AppNav.vue`. Use `<router-link>` for all 5 routes. Highlight active link with `router-link-active` class. Style matches existing nav bar (inline flex, gap, font-size 0.9rem). The nav includes: PURL Resolver, SBOM Updater, Database Admin, Settings, Images List Converter.

Use `v-for` over a routes array for DRY navigation.

- [ ] **Step 4: Create FileUploadZone.vue**

Write `frontend/src/components/FileUploadZone.vue`:
- Props: `accept` (string, default `.json`), `maxSize` (number, default 200MB)
- Emit: `file-selected(file: File)`
- Template: dashed border upload area with drag-and-drop (dragenter/dragover/dragleave/drop events), hidden `<input type="file">`, click-to-browse
- Shows filename and size after selection
- Scoped CSS from existing `.upload-area` styles

- [ ] **Step 5: Create ModalDialog.vue**

Write `frontend/src/components/ModalDialog.vue`:
- Props: `show` (boolean), `title` (string)
- Emit: `close`
- Template: overlay + centered card with title, close button, `<slot>` for content
- Scoped CSS: overlay background with `rgba(0,0,0,0.4)`, card with `position: fixed`, transform centering

### Task 4: Stub Views (SbomUpdater, DatabaseAdmin, NotFound)

**Files:**
- Create: `frontend/src/views/SbomUpdater.vue`
- Create: `frontend/src/views/DatabaseAdmin.vue`
- Create: `frontend/src/views/NotFound.vue`

- [ ] **Step 1: Create SbomUpdater stub**

Write `frontend/src/views/SbomUpdater.vue`:
```vue
<script setup lang="ts">
</script>

<template>
  <div class="card">
    <p>SBOM Updater — coming soon in Plan B.</p>
    <p style="margin-top: 0.5rem; font-size: 0.875rem; color: #666;">
      Use the <a href="/sbom-updater" style="color: #2563eb;">original page</a> for now.
    </p>
  </div>
</template>
```

- [ ] **Step 2: Create DatabaseAdmin stub**

Same pattern, referencing `/db-admin` original page.

- [ ] **Step 3: Create NotFound.vue**

```vue
<template>
  <div class="card" style="text-align: center;">
    <h2>404</h2>
    <p>Page not found</p>
    <router-link to="/" style="color: #2563eb;">Go to PURL Resolver</router-link>
  </div>
</template>
```

- [ ] **Step 4: Verify build**

Run `npm run build` in `frontend/`. Expected: success, `dist/` folder with all route chunks.

### Task 5: Settings Page

**Files:**
- Create: `frontend/src/views/Settings.vue`

- [ ] **Step 1: Create Settings.vue**

A single-file component with all 6 cards. Based on `templates/settings.html` (447 lines).

**State variables** (all `ref`):
- `validateDbUrls: boolean`
- `urlValidationTimeout: number`
- `revalidationCooldownHours: number`
- `retryMaxAttempts: number`
- `retryBaseCooldownSeconds: number`
- `logLevel: string`
- `librariesioEnabled: boolean`
- `ecosystemsEnabled: boolean`
- `ecosystemsMaxRequestsPerSecond: number`
- `tokenSet: SettingsTokenSet` (from API)
- `githubTokenInput: string` (password field, cleared after save)
- `librariesioKeyInput: string`
- `ecosystemsKeyInput: string`
- `loading: boolean`
- `message: { text: string; isError: boolean } | null`

**On mounted**: call `getSettings()` and populate all refs.

**Template structure** (6 cards):
1. URL Validation — toggle + timeout + cooldown
2. GitHub Token — password input + status badge + clear button
3. Libraries.io — toggle + API key input + status badge + clear button
4. ecosyste.ms — toggle + API key input + status + rate limit + clear button
5. Resolver Behaviour — retry attempts + cooldown
6. Logging — select dropdown

**Save**: build `SettingsUpdate` payload (include token/key inputs only when filled, exclude empty strings), call `updateSettings()`, reload on success, show success/error message with auto-hide (3s timeout).

**Clear buttons**: send PATCH with `{ github_token: null }`, `{ librariesio_api_key: null }`, or `{ ecosystems_api_key: null }`.

**Scoped CSS**: Use CSS classes from the existing template: `.card`, `.card-title`, `.setting-row`, `.setting-label`, `.setting-desc`, `.toggle`, `.toggle-slider`, `.msg`, `.msg-ok`, `.msg-err`.

### Task 6: PURL Resolver Page

**Files:**
- Create: `frontend/src/views/PurlResolver.vue`

- [ ] **Step 1: Create PurlResolver.vue**

Based on `templates/index.html` (216 lines).

**State**:
- `purlInput: string` (v-model)
- `loading: boolean`
- `result: ResolveResponse | null`
- `error: string | null`
- `showDetails: boolean`

**Template**:
- Title + subtitle
- Form: input + Resolve button (disabled when loading)
- Loading spinner (conditional)
- Result card (conditional on `result`):
  - Repository URL as link
  - Confidence badge (class: `badge-{confidence}`)
  - Details toggle: evidence list, warnings, repository type/kind, version reference, found by, resolver
- Error message (conditional on `error`)

**Submit**: call `resolvePurl({ purl: purlInput.value })`, handle success (render card) and error (show error message).

**Details toggle**: `showDetails` boolean, button text toggles between "Show details" / "Hide details".

### Task 7: Images List Converter Page

**Files:**
- Create: `frontend/src/views/ImagesListConverter.vue`

- [ ] **Step 1: Create ImagesListConverter.vue**

Based on `templates/images-list-converter.html` (251 lines).

**State**:
- `selectedFile: File | null`
- `loading: boolean`
- `error: string | null`
- `result: ImagesListResponse | null`
- `imagesListData: unknown` (for download)

**Template**:
- Title + subtitle (Russian text preserved)
- `<FileUploadZone @file-selected="handleFile" />`
- "Конвертировать" button (disabled when no file or loading)
- Loading spinner
- Status card (conditional on `result`):
  - If `was_transformed`: orange warning border, "Выполнено преобразование"
  - If not: green border, "Преобразований не требуется"
- Images table (conditional on `result`):
  - Columns: Имя образа, Версия (with check/cross icons), Заполнены компоненты (check/cross), Заполнено поле name, Заполнено поле Properties
  - Iterate `result.images` with `v-for`
- "Скачать список образов" button (downloads `imagesListData` as JSON)

**handleFile(file)**: set `selectedFile = file`.

**Convert**: call `convertImagesList(selectedFile)`, set `result` and `imagesListData` on success.

**Download**: create blob URL from `imagesListData`, trigger download with filename derived from original file name + `_images_list.json`.

---

## Self-Review

**1. Spec coverage:**
- Scaffold ✅ (Task 1)
- API types + client ✅ (Task 2)
- Router + App.vue + shared components ✅ (Task 3)
- Stub views for Plan B pages ✅ (Task 4)
- Settings page ✅ (Task 5)
- PURL Resolver ✅ (Task 6)
- Images List Converter ✅ (Task 7)
- NOT in scope: SBOM Updater, Database Admin, Dockerfile changes, Jinja2 cleanup (deferred to Plan B)

**2. Placeholder scan:** No TBDs, TODOs, or vague requirements. Each task has exact file paths, code structure, and behavior description.

**3. Type consistency:** All TypeScript interfaces in `api.ts` mirror the exact field names from `schemas.py` Python models. API functions return the correct types.

**4. Scope check:** Focused on 3 pages + scaffold. No scope creep. Plan B will handle SBOM, DB Admin, and Docker/Jinja2 cleanup.