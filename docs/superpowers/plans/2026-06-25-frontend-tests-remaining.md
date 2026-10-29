# Frontend Tests — Remaining Components Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Vitest unit tests for the four remaining views (`PurlResolver`, `SbomUpdater`, `ImagesListConverter`, `DatabaseAdmin`) and two composables (`useDownload`, `usePagination`), following the conventions of the existing `Settings.test.ts`.

**Architecture:** Six new test files co-located with source files. View tests mount via `@vue/test-utils` with module-level `vi.mock('../api/<module>')` for API isolation; composable tests call pure functions directly without mounting. Same import style, fake-timer style, and assertion style as `Settings.test.ts`.

**Tech Stack:** Vitest 4.1.9, @vue/test-utils 2.4.11, happy-dom 20.10.6, TypeScript.

## Global Constraints

- All tests use **explicit imports from `'vitest'`** — no globals (`vitest.config.ts` has `globals: false`).
- All API mocks via `vi.mock('../api/<module>', () => ({ ... }))` at the module level.
- All Vue mounting via `mount()` from `@vue/test-utils`, followed by `await flushPromises()` for initial loads.
- All fake-timer blocks must be wrapped in `try { ... } finally { vi.useRealTimers() }`.
- All test files must be **co-located** with the source file (`Component.vue` → `Component.test.ts` next to it).
- No new dependencies may be added to `frontend/package.json`.
- All mock fixtures must mirror the **complete** TypeScript shape of the real API response (no partial mocks).
- Browser API mocks: `vi.spyOn(window, 'confirm').mockReturnValue(true)` and `vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:fake')` when needed in `beforeEach`.
- Reference style: `frontend/src/views/Settings.test.ts` — match its import order, helper function naming (`flush`, `mountXxx`), and assertion style.

---

## File Structure

**Create:**
- `frontend/src/views/PurlResolver.test.ts` — view tests (~7 tests)
- `frontend/src/views/SbomUpdater.test.ts` — view tests (~9 tests)
- `frontend/src/views/ImagesListConverter.test.ts` — view tests (~5 tests; final count after TDD may be 7–8)
- `frontend/src/views/DatabaseAdmin.test.ts` — view tests (~18 tests)
- `frontend/src/composables/useDownload.test.ts` — composable tests (~8 tests)
- `frontend/src/composables/usePagination.test.ts` — composable tests (~7 tests)

**Modify:**
- `specs/domains/web-ui.md` — add a "Test Coverage" section listing all six tested files.

**No other files are modified.**

---

## Task 1: usePagination.test.ts

**Files:**
- Create: `frontend/src/composables/usePagination.test.ts`

**Why first:** `DatabaseAdmin.test.ts` (Task 5) indirectly exercises `usePagination`. By testing the composable first we confirm its contract independently.

### Step 1: Create the test file with initial state test

Create `frontend/src/composables/usePagination.test.ts`:

```typescript
import { describe, it, expect } from 'vitest'
import { usePagination } from './usePagination'

describe('usePagination', () => {
  it('initial state has page 1, pageSize 50, total 0, totalPages 1', () => {
    const { page, pageSize, total, totalPages } = usePagination()
    expect(page.value).toBe(1)
    expect(pageSize.value).toBe(50)
    expect(total.value).toBe(0)
    expect(totalPages.value).toBe(1)
  })

  it('computes totalPages from total and pageSize', () => {
    const { total, totalPages } = usePagination()
    total.value = 250
    expect(totalPages.value).toBe(5)
  })

  it('totalPages is at least 1 when total is 0', () => {
    const { totalPages } = usePagination()
    expect(totalPages.value).toBe(1)
  })

  it('goToPage navigates to a valid page', () => {
    const { page, total, goToPage } = usePagination()
    total.value = 200
    goToPage(3)
    expect(page.value).toBe(3)
  })

  it('goToPage ignores pages below 1', () => {
    const { page, total, goToPage } = usePagination()
    total.value = 200
    page.value = 2
    goToPage(-1)
    expect(page.value).toBe(2)
  })

  it('goToPage ignores pages beyond totalPages', () => {
    const { page, total, goToPage } = usePagination()
    total.value = 200
    page.value = 2
    goToPage(999)
    expect(page.value).toBe(2)
  })

  it('changePageSize updates size and resets to page 1', () => {
    const { page, pageSize, changePageSize } = usePagination()
    page.value = 3
    changePageSize(100)
    expect(pageSize.value).toBe(100)
    expect(page.value).toBe(1)
  })

  it('reset returns to page 1', () => {
    const { page, reset } = usePagination()
    page.value = 5
    reset()
    expect(page.value).toBe(1)
  })
})
```

### Step 2: Run the tests

Run from project root:

```bash
npm test --prefix frontend -- src/composables/usePagination.test.ts
```

Expected: All 8 tests PASS. (Implementation already exists; this is verification of the existing behavior, not TDD red-green. The composable's source is unchanged.)

### Step 3: Commit

```bash
git add frontend/src/composables/usePagination.test.ts
git commit -m "test(usePagination): cover state, computed, and guard logic"
```

---

## Task 2: useDownload.test.ts

**Files:**
- Create: `frontend/src/composables/useDownload.test.ts`

**Why second:** `safeUrl` is security-critical (rejects `javascript:`, `data:`, `vbscript:`). Test it in isolation before any view depends on it indirectly.

### Step 1: Create the test file

Create `frontend/src/composables/useDownload.test.ts`:

```typescript
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { downloadJson, safeUrl } from './useDownload'

describe('safeUrl', () => {
  it('returns undefined for null input', () => {
    expect(safeUrl(null)).toBeUndefined()
  })

  it('returns undefined for undefined input', () => {
    expect(safeUrl(undefined)).toBeUndefined()
  })

  it('returns undefined for empty string', () => {
    expect(safeUrl('')).toBeUndefined()
  })

  it('returns "#" for javascript: protocol', () => {
    expect(safeUrl('javascript:alert(1)')).toBe('#')
  })

  it('returns "#" for data: protocol', () => {
    expect(safeUrl('data:text/html,<script>alert(1)</script>')).toBe('#')
  })

  it('returns "#" for vbscript: protocol', () => {
    expect(safeUrl('vbscript:msgbox(1)')).toBe('#')
  })

  it('returns the URL unchanged for https', () => {
    expect(safeUrl('https://github.com/foo/bar')).toBe('https://github.com/foo/bar')
  })

  it('returns the URL unchanged for git+https', () => {
    expect(safeUrl('git+https://github.com/foo/bar.git')).toBe('git+https://github.com/foo/bar.git')
  })

  it('returns the URL unchanged for ssh', () => {
    expect(safeUrl('ssh://git@github.com/foo/bar.git')).toBe('ssh://git@github.com/foo/bar.git')
  })
})

describe('downloadJson', () => {
  let createObjectURL: ReturnType<typeof vi.spyOn>
  let revokeObjectURL: ReturnType<typeof vi.spyOn>
  let clickSpy: ReturnType<typeof vi.fn>
  let createElementSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    createObjectURL = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:fake-url')
    revokeObjectURL = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
    clickSpy = vi.fn()
    createElementSpy = vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
      if (tag === 'a') {
        return { click: clickSpy, href: '', download: '' } as unknown as HTMLAnchorElement
      }
      return document.createElement(tag)
    })
  })

  afterEach(() => {
    createObjectURL.mockRestore()
    revokeObjectURL.mockRestore()
    createElementSpy.mockRestore()
  })

  it('creates blob URL, triggers anchor click, and revokes URL', () => {
    downloadJson({ a: 1 }, 'test.json')
    expect(createObjectURL).toHaveBeenCalledTimes(1)
    expect(clickSpy).toHaveBeenCalledTimes(1)
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:fake-url')
  })

  it('serializes data as pretty JSON', () => {
    let capturedBlob: Blob | undefined
    createObjectURL.mockImplementation((obj: Blob | MediaSource) => {
      capturedBlob = obj as Blob
      return 'blob:fake-url'
    })
    downloadJson({ a: 1, b: [1, 2, 3] }, 'test.json')
    expect(capturedBlob).toBeDefined()
    expect(capturedBlob!.type).toBe('application/json')
  })

  it('sets the download attribute on the anchor element', () => {
    let capturedAnchor: HTMLAnchorElement | undefined
    createElementSpy.mockImplementation((tag: string) => {
      if (tag === 'a') {
        const anchor = {
          click: clickSpy,
          set href(v: string) { this._href = v },
          get href() { return this._href },
          set download(v: string) { this._download = v },
          get download() { return this._download },
        } as unknown as HTMLAnchorElement
        capturedAnchor = anchor
        return anchor
      }
      return document.createElement(tag)
    })
    downloadJson({ x: 1 }, 'my-file.json')
    expect(capturedAnchor).toBeDefined()
    expect(capturedAnchor!.download).toBe('my-file.json')
    expect(capturedAnchor!.href).toBe('blob:fake-url')
  })
})
```

### Step 2: Run the tests

```bash
npm test --prefix frontend -- src/composables/useDownload.test.ts
```

Expected: All 12 tests PASS.

### Step 3: Commit

```bash
git add frontend/src/composables/useDownload.test.ts
git commit -m "test(useDownload): cover downloadJson and safeUrl edge cases"
```

---

## Task 3: PurlResolver.test.ts

**Files:**
- Create: `frontend/src/views/PurlResolver.test.ts`

**Mocks:** `../api/purl` (`resolvePurl`). Reuse `ApiError` from `../api/client`.

### Step 1: Create the test file

Create `frontend/src/views/PurlResolver.test.ts`:

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import PurlResolver from './PurlResolver.vue'
import { ApiError } from '../api/client'
import type { ResolveResponse } from '../types/api'

const successResponse: ResolveResponse = {
  purl: 'pkg:pypi/requests@2.31.0',
  repository_url: 'https://github.com/psf/requests',
  repository_type: 'github',
  repository_kind: 'source_code',
  confidence: 'high',
  evidence: ['homepage', 'description'],
  warnings: [],
  version_reference: 'https://github.com/psf/requests/tree/v2.31.0',
  resolver: 'purl2repo',
  found_by: 'purl2repo',
  resolved_at: '2026-06-25T10:00:00',
}

const resolvePurlMock = vi.fn()

vi.mock('../api/purl', () => ({
  resolvePurl: (body: { purl: string }) => resolvePurlMock(body),
}))

function mountResolver() {
  return mount(PurlResolver)
}

describe('PurlResolver.vue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    resolvePurlMock.mockResolvedValue(successResponse)
  })

  it('renders initial form without loading or result', async () => {
    const wrapper = mountResolver()
    await flushPromises()
    expect(wrapper.find('h1').text()).toBe('PURL Resolver')
    expect(wrapper.find('input[type="text"]').exists()).toBe(true)
    expect(wrapper.find('button[type="submit"]').exists()).toBe(true)
    expect(wrapper.find('.loading').exists()).toBe(false)
    expect(wrapper.find('.result').exists()).toBe(false)
    expect(wrapper.find('.error-msg').exists()).toBe(false)
  })

  it('calls resolvePurl with the trimmed PURL on submit', async () => {
    const wrapper = mountResolver()
    await flushPromises()
    await wrapper.find('input[type="text"]').setValue('  pkg:pypi/requests@2.31.0  ')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()
    expect(resolvePurlMock).toHaveBeenCalledTimes(1)
    expect(resolvePurlMock).toHaveBeenCalledWith({ purl: 'pkg:pypi/requests@2.31.0' })
  })

  it('renders result card with repository URL on success', async () => {
    const wrapper = mountResolver()
    await flushPromises()
    await wrapper.find('input[type="text"]').setValue('pkg:pypi/requests@2.31.0')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()
    const repoLink = wrapper.find('.repo-url a')
    expect(repoLink.exists()).toBe(true)
    expect(repoLink.attributes('href')).toBe('https://github.com/psf/requests')
    expect(repoLink.text()).toBe('https://github.com/psf/requests')
  })

  it('toggles details section when Show details is clicked', async () => {
    const wrapper = mountResolver()
    await flushPromises()
    await wrapper.find('input[type="text"]').setValue('pkg:pypi/requests@2.31.0')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    const toggle = wrapper.find('.details-toggle')
    expect(toggle.exists()).toBe(true)
    expect(wrapper.find('.details').exists()).toBe(false)

    await toggle.trigger('click')
    expect(wrapper.find('.details').exists()).toBe(true)
    const detailsText = wrapper.find('.details').text()
    expect(detailsText).toContain('Repository Type')
    expect(detailsText).toContain('github')
    expect(detailsText).toContain('Evidence')
    expect(detailsText).toContain('homepage')

    await toggle.trigger('click')
    expect(wrapper.find('.details').exists()).toBe(false)
  })

  it('shows API error message when resolvePurl rejects with ApiError', async () => {
    resolvePurlMock.mockRejectedValueOnce(new ApiError(404, 'not_found', 'No repository found'))
    const wrapper = mountResolver()
    await flushPromises()
    await wrapper.find('input[type="text"]').setValue('pkg:pypi/missing@1.0.0')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()
    expect(wrapper.find('.error-msg').exists()).toBe(true)
    expect(wrapper.find('.error-msg').text()).toBe('No repository found')
    expect(wrapper.find('.result').exists()).toBe(false)
  })

  it('shows network error message when resolvePurl rejects with generic Error', async () => {
    resolvePurlMock.mockRejectedValueOnce(new Error('network down'))
    const wrapper = mountResolver()
    await flushPromises()
    await wrapper.find('input[type="text"]').setValue('pkg:pypi/requests@2.31.0')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()
    expect(wrapper.find('.error-msg').exists()).toBe(true)
    expect(wrapper.find('.error-msg').text()).toContain('Network error')
  })

  it('shows fallback "No repository URL found" when response has null repository_url', async () => {
    resolvePurlMock.mockResolvedValueOnce({
      ...successResponse,
      repository_url: null,
      confidence: null,
      repository_type: null,
      repository_kind: null,
      evidence: [],
      warnings: [],
      version_reference: null,
    })
    const wrapper = mountResolver()
    await flushPromises()
    await wrapper.find('input[type="text"]').setValue('pkg:pypi/missing@1.0.0')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()
    expect(wrapper.find('.repo-url').text()).toContain('No repository URL found')
  })
})
```

### Step 2: Run the tests

```bash
npm test --prefix frontend -- src/views/PurlResolver.test.ts
```

Expected: All 7 tests PASS.

### Step 3: Commit

```bash
git add frontend/src/views/PurlResolver.test.ts
git commit -m "test(PurlResolver): cover resolve flow, details toggle, and error states"
```

---

## Task 4: ImagesListConverter.test.ts

**Files:**
- Create: `frontend/src/views/ImagesListConverter.test.ts`

**Mocks:** `../api/images` (`convertImagesList`).

### Step 1: Create the test file

Create `frontend/src/views/ImagesListConverter.test.ts`:

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import ImagesListConverter from './ImagesListConverter.vue'
import { ApiError } from '../api/client'
import type { ImagesListResponse } from '../types/api'

const okResponse: ImagesListResponse = {
  was_transformed: false,
  images: [
    {
      name: 'nginx',
      version: '1.25.0',
      missing_components: false,
      missing_name: false,
      missing_version: false,
      missing_properties: false,
    },
    {
      name: 'redis',
      version: null,
      missing_components: true,
      missing_name: false,
      missing_version: true,
      missing_properties: false,
    },
  ],
  images_list: { images: [{ name: 'nginx', version: '1.25.0' }] },
}

const convertMock = vi.fn()

vi.mock('../api/images', () => ({
  convertImagesList: (file: File) => convertMock(file),
}))

function mountConverter() {
  return mount(ImagesListConverter)
}

describe('ImagesListConverter.vue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    convertMock.mockResolvedValue(okResponse)
  })

  it('renders initial empty state with disabled Convert button', async () => {
    const wrapper = mountConverter()
    await flushPromises()
    expect(wrapper.find('h1').text()).toBe('Images List Converter')
    const button = wrapper.find('.toolbar button')
    expect(button.exists()).toBe(true)
    expect(button.attributes('disabled')).toBeDefined()
    expect(wrapper.find('.results').exists()).toBe(false)
  })

  it('enables Convert button after file is selected and calls API', async () => {
    const wrapper = mountConverter()
    await flushPromises()
    const file = new File(['{}'], 'sbom.json', { type: 'application/json' })
    const uploadZone = wrapper.findComponent({ name: 'FileUploadZone' })
    await uploadZone.vm.$emit('file-selected', file)
    await flushPromises()

    const button = wrapper.find('.toolbar button')
    expect(button.attributes('disabled')).toBeUndefined()
    await button.trigger('click')
    await flushPromises()
    expect(convertMock).toHaveBeenCalledTimes(1)
    expect(convertMock).toHaveBeenCalledWith(file)
  })

  it('renders green status card when was_transformed is false', async () => {
    const wrapper = mountConverter()
    await flushPromises()
    const file = new File(['{}'], 'sbom.json', { type: 'application/json' })
    await wrapper.findComponent({ name: 'FileUploadZone' }).vm.$emit('file-selected', file)
    await flushPromises()
    await wrapper.find('.toolbar button').trigger('click')
    await flushPromises()
    const statusCard = wrapper.find('.status-card')
    expect(statusCard.exists()).toBe(true)
    expect(statusCard.classes()).toContain('status-ok')
    expect(statusCard.text()).toContain('Преобразований не требуется')
  })

  it('renders yellow status card when was_transformed is true', async () => {
    convertMock.mockResolvedValueOnce({ ...okResponse, was_transformed: true })
    const wrapper = mountConverter()
    await flushPromises()
    const file = new File(['{}'], 'sbom.json', { type: 'application/json' })
    await wrapper.findComponent({ name: 'FileUploadZone' }).vm.$emit('file-selected', file)
    await flushPromises()
    await wrapper.find('.toolbar button').trigger('click')
    await flushPromises()
    const statusCard = wrapper.find('.status-card')
    expect(statusCard.classes()).toContain('status-transformed')
    expect(statusCard.text()).toContain('Выполнено преобразование')
  })

  it('renders images table with completeness flags', async () => {
    const wrapper = mountConverter()
    await flushPromises()
    const file = new File(['{}'], 'sbom.json', { type: 'application/json' })
    await wrapper.findComponent({ name: 'FileUploadZone' }).vm.$emit('file-selected', file)
    await flushPromises()
    await wrapper.find('.toolbar button').trigger('click')
    await flushPromises()
    const rows = wrapper.findAll('tbody tr')
    expect(rows.length).toBe(2)
    expect(rows[0].text()).toContain('nginx')
    expect(rows[0].text()).toContain('1.25.0')
    expect(rows[1].text()).toContain('redis')
  })

  it('shows API error message on ApiError', async () => {
    convertMock.mockRejectedValueOnce(new ApiError(400, 'bad_request', 'Invalid SBOM'))
    const wrapper = mountConverter()
    await flushPromises()
    const file = new File(['{}'], 'sbom.json', { type: 'application/json' })
    await wrapper.findComponent({ name: 'FileUploadZone' }).vm.$emit('file-selected', file)
    await flushPromises()
    await wrapper.find('.toolbar button').trigger('click')
    await flushPromises()
    expect(wrapper.find('.error-msg').exists()).toBe(true)
    expect(wrapper.find('.error-msg').text()).toBe('Invalid SBOM')
    expect(wrapper.find('.results').exists()).toBe(false)
  })

  it('shows network error message on generic Error', async () => {
    convertMock.mockRejectedValueOnce(new Error('network'))
    const wrapper = mountConverter()
    await flushPromises()
    const file = new File(['{}'], 'sbom.json', { type: 'application/json' })
    await wrapper.findComponent({ name: 'FileUploadZone' }).vm.$emit('file-selected', file)
    await flushPromises()
    await wrapper.find('.toolbar button').trigger('click')
    await flushPromises()
    expect(wrapper.find('.error-msg').text()).toContain('Network error')
  })

  it('triggers JSON download when "Скачать список образов" is clicked', async () => {
    const createObjectURL = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:fake')
    const revokeObjectURL = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
    const clickSpy = vi.fn()
    const originalCreate = document.createElement.bind(document)
    const createSpy = vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
      if (tag === 'a') {
        return { click: clickSpy, set href(v: string) {}, get href() { return '' }, set download(v: string) {}, get download() { return '' } } as unknown as HTMLAnchorElement
      }
      return originalCreate(tag)
    })

    const wrapper = mountConverter()
    await flushPromises()
    const file = new File(['{}'], 'sbom.json', { type: 'application/json' })
    await wrapper.findComponent({ name: 'FileUploadZone' }).vm.$emit('file-selected', file)
    await flushPromises()
    await wrapper.find('.toolbar button').trigger('click')
    await flushPromises()

    const buttons = wrapper.findAll('.toolbar button')
    const downloadBtn = buttons.find((b) => b.text().includes('Скачать'))
    expect(downloadBtn).toBeDefined()
    await downloadBtn!.trigger('click')

    expect(clickSpy).toHaveBeenCalled()
    expect(createObjectURL).toHaveBeenCalled()
    createObjectURL.mockRestore()
    revokeObjectURL.mockRestore()
    createSpy.mockRestore()
  })
})
```

### Step 2: Run the tests

```bash
npm test --prefix frontend -- src/views/ImagesListConverter.test.ts
```

Expected: All 8 tests PASS.

### Step 3: Commit

```bash
git add frontend/src/views/ImagesListConverter.test.ts
git commit -m "test(ImagesListConverter): cover conversion flow, status cards, and download"
```

---

## Task 5: SbomUpdater.test.ts

**Files:**
- Create: `frontend/src/views/SbomUpdater.test.ts`

**Mocks:** `../api/sbom` (`getIgnorePatterns`, `saveIgnorePatterns`, `resolveSbom`).

### Step 1: Create the test file

Create `frontend/src/views/SbomUpdater.test.ts`:

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import SbomUpdater from './SbomUpdater.vue'
import { ApiError } from '../api/client'
import type { SbomResponse } from '../types/api'

const emptyPatterns = { patterns: [] }
const twoPatterns = { patterns: [{ field: 'purl', pattern: 'requests' }, { field: 'type', pattern: 'npm' }] }

const successResult: SbomResponse = {
  summary: {
    total_purls: 10,
    found: 7,
    not_found: 3,
    skipped: 0,
    removed: 0,
    ignored: 0,
  },
  results: [
    { purl: 'pkg:pypi/requests@2.31.0', status: 'found', repository_url: 'https://github.com/psf/requests', found_by: 'purl2repo', resolver: 'purl2repo' },
    { purl: 'pkg:pypi/missing@1.0.0', status: 'not_found', repository_url: null },
  ],
  enriched_sbom: { bomFormat: 'CycloneDX', components: [] },
}

const getIgnorePatternsMock = vi.fn()
const saveIgnorePatternsMock = vi.fn()
const resolveSbomMock = vi.fn()

vi.mock('../api/sbom', () => ({
  getIgnorePatterns: () => getIgnorePatternsMock(),
  saveIgnorePatterns: (patterns: unknown) => saveIgnorePatternsMock(patterns),
  resolveSbom: (file: File, removeUnresolved: boolean, validateRefs: boolean, patterns: unknown, signal: AbortSignal) =>
    resolveSbomMock(file, removeUnresolved, validateRefs, patterns, signal),
}))

function mountUpdater() {
  return mount(SbomUpdater)
}

describe('SbomUpdater.vue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getIgnorePatternsMock.mockResolvedValue(emptyPatterns)
    saveIgnorePatternsMock.mockResolvedValue({ status: 'ok' })
    resolveSbomMock.mockResolvedValue(successResult)
  })

  it('loads on mount with one empty pattern row when API returns empty', async () => {
    const wrapper = mountUpdater()
    await flushPromises()
    expect(getIgnorePatternsMock).toHaveBeenCalledTimes(1)
    const rows = wrapper.findAll('.pattern-row')
    expect(rows.length).toBe(1)
    const inputs = rows[0].findAll('input[type="text"]')
    expect(inputs[0].element.value).toBe('')
    expect(inputs[1].element.value).toBe('')
  })

  it('loads existing ignore patterns from API', async () => {
    getIgnorePatternsMock.mockResolvedValueOnce(twoPatterns)
    const wrapper = mountUpdater()
    await flushPromises()
    const rows = wrapper.findAll('.pattern-row')
    expect(rows.length).toBe(2)
    expect(rows[0].findAll('input[type="text"]')[0].element.value).toBe('purl')
    expect(rows[0].findAll('input[type="text"]')[1].element.value).toBe('requests')
  })

  it('falls back to empty pattern row when getIgnorePatterns fails', async () => {
    getIgnorePatternsMock.mockRejectedValueOnce(new Error('network'))
    const wrapper = mountUpdater()
    await flushPromises()
    expect(wrapper.findAll('.pattern-row').length).toBe(1)
  })

  it('adds a new empty pattern row when "Добавить строку" is clicked', async () => {
    const wrapper = mountUpdater()
    await flushPromises()
    const addBtn = wrapper.findAll('.pattern-toolbar button').find((b) => b.text().includes('Добавить'))
    await addBtn!.trigger('click')
    expect(wrapper.findAll('.pattern-row').length).toBe(2)
  })

  it('removes a pattern row when ✕ button is clicked', async () => {
    getIgnorePatternsMock.mockResolvedValueOnce(twoPatterns)
    const wrapper = mountUpdater()
    await flushPromises()
    expect(wrapper.findAll('.pattern-row').length).toBe(2)
    const removeBtn = wrapper.find('.btn-delete')
    await removeBtn.trigger('click')
    expect(wrapper.findAll('.pattern-row').length).toBe(1)
  })

  it('saves only non-empty pattern rows', async () => {
    vi.useFakeTimers()
    try {
      getIgnorePatternsMock.mockResolvedValueOnce(twoPatterns)
      const wrapper = mountUpdater()
      await flushPromises()
      // add an empty row
      const addBtn = wrapper.findAll('.pattern-toolbar button').find((b) => b.text().includes('Добавить'))
      await addBtn!.trigger('click')
      await flushPromises()

      const saveBtn = wrapper.findAll('.pattern-toolbar button').find((b) => b.text().includes('Сохранить'))
      await saveBtn!.trigger('click')
      await flushPromises()

      expect(saveIgnorePatternsMock).toHaveBeenCalledTimes(1)
      expect(saveIgnorePatternsMock).toHaveBeenCalledWith([
        { field: 'purl', pattern: 'requests' },
        { field: 'type', pattern: 'npm' },
      ])
    } finally {
      vi.useRealTimers()
    }
  })

  it('shows error message when saveIgnorePatterns fails with ApiError', async () => {
    saveIgnorePatternsMock.mockRejectedValueOnce(new ApiError(400, 'bad_request', 'Invalid pattern'))
    const wrapper = mountUpdater()
    await flushPromises()
    const saveBtn = wrapper.findAll('.pattern-toolbar button').find((b) => b.text().includes('Сохранить'))
    await saveBtn!.trigger('click')
    await flushPromises()
    expect(wrapper.find('.error-msg').exists()).toBe(true)
    expect(wrapper.find('.error-msg').text()).toBe('Invalid pattern')
  })

  it('processes SBOM and renders summary + results table', async () => {
    const wrapper = mountUpdater()
    await flushPromises()
    const file = new File(['{}'], 'bom.json', { type: 'application/json' })
    await wrapper.findComponent({ name: 'FileUploadZone' }).vm.$emit('file-selected', file)
    await flushPromises()

    const processBtn = wrapper.findAll('.toolbar button').find((b) => b.text().includes('Обработать'))
    expect(processBtn!.attributes('disabled')).toBeUndefined()
    await processBtn!.trigger('click')
    await flushPromises()

    expect(resolveSbomMock).toHaveBeenCalledTimes(1)
    expect(wrapper.find('.results').exists()).toBe(true)
    expect(wrapper.text()).toContain('10')
    expect(wrapper.text()).toContain('7')
    expect(wrapper.text()).toContain('Not found')
    expect(wrapper.findAll('tbody tr').length).toBe(2)
  })

  it('passes an AbortSignal as the 5th argument to resolveSbom', async () => {
    const wrapper = mountUpdater()
    await flushPromises()
    const file = new File(['{}'], 'bom.json', { type: 'application/json' })
    await wrapper.findComponent({ name: 'FileUploadZone' }).vm.$emit('file-selected', file)
    await flushPromises()
    await wrapper.findAll('.toolbar button').find((b) => b.text().includes('Обработать'))!.trigger('click')
    await flushPromises()

    const args = resolveSbomMock.mock.calls[0]
    expect(args.length).toBe(5)
    expect(args[4]).toBeInstanceOf(AbortSignal)
  })

  it('process button is disabled when no file is selected', async () => {
    const wrapper = mountUpdater()
    await flushPromises()
    const processBtn = wrapper.findAll('.toolbar button').find((b) => b.text().includes('Обработать'))
    expect(processBtn!.attributes('disabled')).toBeDefined()
    await processBtn!.trigger('click')
    await flushPromises()
    expect(resolveSbomMock).not.toHaveBeenCalled()
  })
})
```

### Step 2: Run the tests

```bash
npm test --prefix frontend -- src/views/SbomUpdater.test.ts
```

Expected: All 10 tests PASS.

### Step 3: Commit

```bash
git add frontend/src/views/SbomUpdater.test.ts
git commit -m "test(SbomUpdater): cover patterns editor, process flow, and AbortSignal"
```

---

## Task 6: DatabaseAdmin.test.ts

**Files:**
- Create: `frontend/src/views/DatabaseAdmin.test.ts`

**Mocks:** `../api/db` (`listPurls`, `updatePurl`, `deletePurls`, `importCsv`, `exportSelectedCsv`). Browser mocks for `window.confirm` and `URL.createObjectURL`.

This is the largest test file. Split into three commits for reviewability.

### Step 1: Create the test file with the first 7 tests (load + filter + sort + select)

Create `frontend/src/views/DatabaseAdmin.test.ts`:

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import DatabaseAdmin from './DatabaseAdmin.vue'
import { ApiError } from '../api/client'
import type { ResolveResponse, PurlListResponse } from '../types/api'

function makeRow(purl: string, overrides: Partial<ResolveResponse> = {}): ResolveResponse {
  return {
    purl,
    repository_url: `https://github.com/${purl.split('/')[1]}`,
    repository_type: 'github',
    repository_kind: 'source_code',
    confidence: 'high',
    evidence: [],
    warnings: [],
    version_reference: null,
    resolver: 'purl2repo',
    found_by: 'purl2repo',
    resolved_at: '2026-06-25T10:00:00',
    ...overrides,
  }
}

const rows = [
  makeRow('pkg:pypi/requests@2.31.0'),
  makeRow('pkg:pypi/flask@2.3.0', { confidence: 'medium' }),
  makeRow('pkg:pypi/numpy@1.25.0', { confidence: 'low', repository_url: null }),
]

const defaultListResponse: PurlListResponse = { rows, total: 3, page: 1, page_size: 50 }

const listPurlsMock = vi.fn()
const updatePurlMock = vi.fn()
const deletePurlsMock = vi.fn()
const importCsvMock = vi.fn()
const exportCsvMock = vi.fn()

vi.mock('../api/db', () => ({
  listPurls: (params: unknown) => listPurlsMock(params),
  updatePurl: (purl: string, body: unknown) => updatePurlMock(purl, body),
  deletePurls: (purls: string[]) => deletePurlsMock(purls),
  importCsv: (file: File, strategy: string) => importCsvMock(file, strategy),
  exportSelectedCsv: (purls: string[]) => exportCsvMock(purls),
}))

function mountAdmin() {
  return mount(DatabaseAdmin)
}

describe('DatabaseAdmin.vue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    listPurlsMock.mockResolvedValue(defaultListResponse)
    updatePurlMock.mockResolvedValue({ ok: true })
    deletePurlsMock.mockResolvedValue({ deleted: 1 })
    importCsvMock.mockResolvedValue({ imported: 2, skipped: 0, errors: [] })
    exportCsvMock.mockResolvedValue(new Blob(['csv'], { type: 'text/csv' }))
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:fake')
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
  })

  it('loads rows on mount with default sort and page 1', async () => {
    const wrapper = mountAdmin()
    await flushPromises()
    expect(listPurlsMock).toHaveBeenCalledTimes(1)
    const params = listPurlsMock.mock.calls[0][0] as Record<string, unknown>
    expect(params.page).toBe(1)
    expect(params.page_size).toBe(50)
    expect(params.sort_by).toBe('resolved_at')
    expect(params.sort_order).toBe('desc')
    expect(wrapper.findAll('tbody tr').length).toBe(3)
  })

  it('applies filters on Apply click and resets page to 1', async () => {
    const wrapper = mountAdmin()
    await flushPromises()
    listPurlsMock.mockClear()

    await wrapper.find('#search').setValue('requests')
    await wrapper.find('#resolver').setValue('purl2repo')
    await wrapper.findAll('.filter-actions button').find((b) => b.text() === 'Apply')!.trigger('click')
    await flushPromises()

    expect(listPurlsMock).toHaveBeenCalledTimes(1)
    const params = listPurlsMock.mock.calls[0][0] as Record<string, unknown>
    expect(params.search).toBe('requests')
    expect(params.resolver).toBe('purl2repo')
    expect(params.page).toBe(1)
  })

  it('resets all filters on Reset click', async () => {
    const wrapper = mountAdmin()
    await flushPromises()
    await wrapper.find('#search').setValue('requests')
    await wrapper.find('#confidence').setValue('high')
    await wrapper.findAll('.filter-actions button').find((b) => b.text() === 'Reset')!.trigger('click')
    await flushPromises()

    expect((wrapper.find('#search').element as HTMLInputElement).value).toBe('')
    expect((wrapper.find('#confidence').element as HTMLSelectElement).value).toBe('')
    const params = listPurlsMock.mock.calls[listPurlsMock.mock.calls.length - 1][0] as Record<string, unknown>
    expect(params.search).toBeUndefined()
    expect(params.confidence).toBeUndefined()
    expect(params.sort_by).toBe('resolved_at')
    expect(params.sort_order).toBe('desc')
  })

  it('sorts by column header click and toggles order on second click', async () => {
    const wrapper = mountAdmin()
    await flushPromises()
    listPurlsMock.mockClear()

    const purlHeader = wrapper.findAll('th.col-sortable').find((th) => th.text().includes('PURL'))!
    await purlHeader.trigger('click')
    await flushPromises()
    let params = listPurlsMock.mock.calls[0][0] as Record<string, unknown>
    expect(params.sort_by).toBe('purl')
    expect(params.sort_order).toBe('asc')

    listPurlsMock.mockClear()
    await purlHeader.trigger('click')
    await flushPromises()
    params = listPurlsMock.mock.calls[0][0] as Record<string, unknown>
    expect(params.sort_by).toBe('purl')
    expect(params.sort_order).toBe('desc')
  })

  it('toggles individual row selection', async () => {
    const wrapper = mountAdmin()
    await flushPromises()
    const firstRowCheckbox = wrapper.findAll('tbody tr input[type="checkbox"]')[0]
    await firstRowCheckbox.trigger('change')
    await flushPromises()

    const exportBtn = wrapper.findAll('.toolbar button').find((b) => b.text().includes('Export CSV'))!
    expect(exportBtn.text()).toContain('(1)')
  })

  it('selects all rows when header checkbox is clicked', async () => {
    const wrapper = mountAdmin()
    await flushPromises()
    const headerCheckbox = wrapper.find('thead input[type="checkbox"]')
    await headerCheckbox.trigger('change')
    await flushPromises()

    const exportBtn = wrapper.findAll('.toolbar button').find((b) => b.text().includes('Export CSV'))!
    expect(exportBtn.text()).toContain('(3)')
  })

  it('shows empty row message when API returns no rows', async () => {
    listPurlsMock.mockResolvedValueOnce({ rows: [], total: 0, page: 1, page_size: 50 })
    const wrapper = mountAdmin()
    await flushPromises()
    expect(wrapper.find('.empty-row').exists()).toBe(true)
    expect(wrapper.find('.empty-row').text()).toBe('No records found')
  })
})
```

### Step 2: Run the first batch

```bash
npm test --prefix frontend -- src/views/DatabaseAdmin.test.ts
```

Expected: 7 tests PASS. (Will be more once we add the rest; vitest counts tests dynamically.)

### Step 3: Add inline editing tests

Append to the `describe('DatabaseAdmin.vue', ...)` block, **before the closing `})`**:

```typescript
  it('enters edit mode and saves change on Enter key', async () => {
    const wrapper = mountAdmin()
    await flushPromises()

    const firstRow = wrapper.findAll('tbody tr')[0]
    const purlCell = firstRow.findAll('td')[1]
    await purlCell.trigger('dblclick')
    await flushPromises()

    const editInput = firstRow.find('input.inline-edit')
    expect(editInput.exists()).toBe(true)
    await editInput.setValue('pkg:pypi/requests@2.32.0')
    await editInput.trigger('keydown', { key: 'Enter' })
    await flushPromises()

    expect(updatePurlMock).toHaveBeenCalledTimes(1)
    expect(updatePurlMock).toHaveBeenCalledWith('pkg:pypi/requests@2.31.0', { purl: 'pkg:pypi/requests@2.32.0' })
  })

  it('cancels edit mode on Escape key without saving', async () => {
    const wrapper = mountAdmin()
    await flushPromises()
    const firstRow = wrapper.findAll('tbody tr')[0]
    await firstRow.findAll('td')[1].trigger('dblclick')
    await flushPromises()

    const editInput = firstRow.find('input.inline-edit')
    await editInput.setValue('changed')
    await editInput.trigger('keydown', { key: 'Escape' })
    await flushPromises()

    expect(updatePurlMock).not.toHaveBeenCalled()
    expect(wrapper.find('input.inline-edit').exists()).toBe(false)
  })

  it('saves inline edit on blur', async () => {
    const wrapper = mountAdmin()
    await flushPromises()
    const firstRow = wrapper.findAll('tbody tr')[0]
    await firstRow.findAll('td')[1].trigger('dblclick')
    await flushPromises()

    const editInput = firstRow.find('input.inline-edit')
    await editInput.setValue('pkg:pypi/new@1.0.0')
    await editInput.trigger('blur')
    await flushPromises()

    expect(updatePurlMock).toHaveBeenCalledTimes(1)
    expect(updatePurlMock).toHaveBeenCalledWith('pkg:pypi/requests@2.31.0', { purl: 'pkg:pypi/new@1.0.0' })
  })
```

### Step 4: Run after adding edit tests

```bash
npm test --prefix frontend -- src/views/DatabaseAdmin.test.ts
```

Expected: 10 tests PASS.

### Step 5: Add delete tests

Append to the same `describe` block, before the closing `})`:

```typescript
  it('deletes a single row when confirm returns true', async () => {
    const wrapper = mountAdmin()
    await flushPromises()
    const delBtn = wrapper.findAll('tbody tr')[0].findAll('button').find((b) => b.text() === 'Del')!
    await delBtn.trigger('click')
    await flushPromises()

    expect(window.confirm).toHaveBeenCalled()
    expect(deletePurlsMock).toHaveBeenCalledTimes(1)
    expect(deletePurlsMock).toHaveBeenCalledWith(['pkg:pypi/requests@2.31.0'])
  })

  it('does not delete when confirm returns false', async () => {
    vi.mocked(window.confirm).mockReturnValueOnce(false)
    const wrapper = mountAdmin()
    await flushPromises()
    const delBtn = wrapper.findAll('tbody tr')[0].findAll('button').find((b) => b.text() === 'Del')!
    await delBtn.trigger('click')
    await flushPromises()

    expect(deletePurlsMock).not.toHaveBeenCalled()
  })

  it('bulk deletes selected rows', async () => {
    const wrapper = mountAdmin()
    await flushPromises()
    const rowCheckboxes = wrapper.findAll('tbody tr input[type="checkbox"]')
    await rowCheckboxes[0].trigger('change')
    await rowCheckboxes[1].trigger('change')
    await flushPromises()

    const bulkBtn = wrapper.findAll('.toolbar button').find((b) => b.text().includes('Delete Selected'))!
    await bulkBtn.trigger('click')
    await flushPromises()

    expect(deletePurlsMock).toHaveBeenCalledTimes(1)
    const deletedPurls = deletePurlsMock.mock.calls[0][0] as string[]
    expect(deletedPurls).toHaveLength(2)
    expect(deletedPurls).toContain('pkg:pypi/requests@2.31.0')
    expect(deletedPurls).toContain('pkg:pypi/flask@2.3.0')
  })
```

### Step 6: Run after adding delete tests

```bash
npm test --prefix frontend -- src/views/DatabaseAdmin.test.ts
```

Expected: 13 tests PASS.

### Step 7: Add import / export / pagination / error tests

Append to the same `describe` block, before the closing `})`:

```typescript
  it('exports selected rows as CSV and triggers download', async () => {
    const clickSpy = vi.fn()
    const originalCreate = document.createElement.bind(document)
    const createSpy = vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
      if (tag === 'a') {
        return { click: clickSpy, set href(v: string) {}, get href() { return '' }, set download(v: string) {}, get download() { return '' } } as unknown as HTMLAnchorElement
      }
      return originalCreate(tag)
    })

    const wrapper = mountAdmin()
    await flushPromises()
    await wrapper.findAll('tbody tr input[type="checkbox"]')[0].trigger('change')
    await flushPromises()

    const exportBtn = wrapper.findAll('.toolbar button').find((b) => b.text().includes('Export CSV'))!
    await exportBtn.trigger('click')
    await flushPromises()

    expect(exportCsvMock).toHaveBeenCalledTimes(1)
    expect(exportCsvMock).toHaveBeenCalledWith(['pkg:pypi/requests@2.31.0'])
    expect(clickSpy).toHaveBeenCalled()
    createSpy.mockRestore()
  })

  it('imports CSV file with upsert strategy by default', async () => {
    const wrapper = mountAdmin()
    await flushPromises()
    // Open import modal
    await wrapper.findAll('.toolbar button').find((b) => b.text().includes('Import CSV'))!.trigger('click')
    await flushPromises()

    const file = new File(['purl,repository_url\npkg:pypi/x@1,https://github.com/x'], 'import.csv', { type: 'text/csv' })
    await wrapper.findComponent({ name: 'FileUploadZone' }).vm.$emit('file-selected', file)
    await flushPromises()

    const uploadBtn = wrapper.findAll('.toolbar button').find((b) => b.text().includes('Upload'))!
    await uploadBtn.trigger('click')
    await flushPromises()

    expect(importCsvMock).toHaveBeenCalledTimes(1)
    expect(importCsvMock).toHaveBeenCalledWith(file, 'upsert')
  })

  it('imports CSV file with skip_existing strategy when radio is changed', async () => {
    const wrapper = mountAdmin()
    await flushPromises()
    await wrapper.findAll('.toolbar button').find((b) => b.text().includes('Import CSV'))!.trigger('click')
    await flushPromises()

    const file = new File(['purl,repository_url\npkg:pypi/x@1,https://github.com/x'], 'import.csv', { type: 'text/csv' })
    await wrapper.findComponent({ name: 'FileUploadZone' }).vm.$emit('file-selected', file)
    await flushPromises()

    const skipRadio = wrapper.find('input[type="radio"][value="skip_existing"]')
    await skipRadio.setValue(true)
    await flushPromises()

    await wrapper.findAll('.toolbar button').find((b) => b.text().includes('Upload'))!.trigger('click')
    await flushPromises()

    expect(importCsvMock).toHaveBeenCalledWith(file, 'skip_existing')
  })

  it('shows import error message on ApiError', async () => {
    importCsvMock.mockRejectedValueOnce(new ApiError(400, 'bad_csv', 'Malformed CSV'))
    const wrapper = mountAdmin()
    await flushPromises()
    await wrapper.findAll('.toolbar button').find((b) => b.text().includes('Import CSV'))!.trigger('click')
    await flushPromises()
    const file = new File(['bad'], 'bad.csv', { type: 'text/csv' })
    await wrapper.findComponent({ name: 'FileUploadZone' }).vm.$emit('file-selected', file)
    await flushPromises()
    await wrapper.findAll('.toolbar button').find((b) => b.text().includes('Upload'))!.trigger('click')
    await flushPromises()

    expect(wrapper.find('.import-error').exists()).toBe(true)
    expect(wrapper.text()).toContain('Malformed CSV')
  })

  it('paginates to next page when Next button is clicked', async () => {
    listPurlsMock.mockResolvedValueOnce({ rows, total: 100, page: 1, page_size: 50 })
    const wrapper = mountAdmin()
    await flushPromises()
    listPurlsMock.mockClear()

    const nextBtn = wrapper.findAll('.pagination-controls button').find((b) => b.text().includes('Next'))!
    await nextBtn.trigger('click')
    await flushPromises()

    expect(listPurlsMock).toHaveBeenCalledTimes(1)
    const params = listPurlsMock.mock.calls[0][0] as Record<string, unknown>
    expect(params.page).toBe(2)
  })

  it('changes page size and resets page to 1', async () => {
    listPurlsMock.mockResolvedValueOnce({ rows, total: 100, page: 1, page_size: 50 })
    const wrapper = mountAdmin()
    await flushPromises()
    listPurlsMock.mockClear()

    const pageSizeSelect = wrapper.find('.pagination-size select')
    await pageSizeSelect.setValue('100')
    await flushPromises()

    expect(listPurlsMock).toHaveBeenCalledTimes(1)
    const params = listPurlsMock.mock.calls[0][0] as Record<string, unknown>
    expect(params.page_size).toBe(100)
    expect(params.page).toBe(1)
  })

  it('shows API error message when listPurls rejects with ApiError', async () => {
    listPurlsMock.mockRejectedValueOnce(new ApiError(500, 'server_error', 'Database unavailable'))
    const wrapper = mountAdmin()
    await flushPromises()
    expect(wrapper.find('.error-msg').exists()).toBe(true)
    expect(wrapper.find('.error-msg').text()).toBe('Database unavailable')
  })

  it('shows network error message when listPurls rejects with generic Error', async () => {
    listPurlsMock.mockRejectedValueOnce(new Error('network'))
    const wrapper = mountAdmin()
    await flushPromises()
    expect(wrapper.find('.error-msg').exists()).toBe(true)
    expect(wrapper.find('.error-msg').text()).toContain('Network error')
  })
```

### Step 8: Run all DatabaseAdmin tests

```bash
npm test --prefix frontend -- src/views/DatabaseAdmin.test.ts
```

Expected: All 18 tests PASS.

### Step 9: Commit

```bash
git add frontend/src/views/DatabaseAdmin.test.ts
git commit -m "test(DatabaseAdmin): cover filter, sort, edit, delete, import, export, pagination"
```

---

## Task 7: Update specs/domains/web-ui.md

**Files:**
- Modify: `specs/domains/web-ui.md` — add a "Test Coverage" subsection.

### Step 1: Read the current section to anchor edits

The current spec ends with the "Global" section. Add a new section **"### Test Coverage"** after the "Global" section.

### Step 2: Append the section

Edit `specs/domains/web-ui.md` and add at the end of the file:

```markdown
### Test Coverage

Frontend unit tests are written with **Vitest 4.1.9**, `@vue/test-utils 2.4.11`, and `happy-dom`. All tests follow the conventions established in `frontend/src/views/Settings.test.ts`:

- Explicit imports from `'vitest'` (no globals).
- Module-level API mocking via `vi.mock('../api/<module>')`.
- Fake timers via `vi.useFakeTimers()` + `vi.advanceTimersByTime()` + `await flushPromises()`.
- Vue mounting via `mount()` + `await flushPromises()` for initial loads.

**Tested files:**

- `frontend/src/views/Settings.test.ts` — auto-save, debounce, blur logic, success/error toast, clear-token behaviour.
- `frontend/src/views/PurlResolver.test.ts` — resolve flow, details toggle, ApiError and network errors.
- `frontend/src/views/SbomUpdater.test.ts` — ignore-patterns editor (add/remove/save), process flow, AbortSignal passed to `resolveSbom`.
- `frontend/src/views/ImagesListConverter.test.ts` — conversion flow, status cards (transformed / not transformed), JSON download.
- `frontend/src/views/DatabaseAdmin.test.ts` — filter, sort, select, inline edit (Enter/Escape/blur), single and bulk delete (confirm branches), CSV export, CSV import (upsert / skip_existing), pagination (next page, page size), ApiError and network errors.
- `frontend/src/composables/useDownload.test.ts` — `downloadJson` blob/anchor behaviour, `safeUrl` dangerous-protocol rejection (javascript, data, vbscript).
- `frontend/src/composables/usePagination.test.ts` — initial state, `totalPages` computation, `goToPage` guard logic, `changePageSize` resets page.

**Deliberately not tested (YAGNI):** `NotFound.vue`, `AppNav.vue`, `FileUploadZone.vue`, `ModalDialog.vue` — trivial components with minimal logic; tests would yield low signal-to-noise.

Run all frontend tests:

```bash
npm test --prefix frontend
```

Run with coverage:

```bash
npm run test:coverage --prefix frontend
```
```

### Step 3: Verify the spec change

```bash
grep -n "Test Coverage" specs/domains/web-ui.md
```

Expected: One match.

### Step 4: Commit

```bash
git add specs/domains/web-ui.md
git commit -m "docs(specs): document test coverage for remaining frontend components"
```

---

## Task 8: Final Verification

**Files:** None (verification only).

### Step 1: Run the full test suite

```bash
npm test --prefix frontend
```

Expected: All tests PASS (existing Settings.test.ts + all 6 new test files). Exit code 0.

### Step 2: Run the build

```bash
npm run build --prefix frontend
```

Expected: Build succeeds. No TypeScript errors. (Test files are not included in the build output, but `vue-tsc` may type-check them depending on `tsconfig.json` include patterns. If errors appear, fix them inline.)

### Step 3: Run with coverage

```bash
npm run test:coverage --prefix frontend
```

Expected: Coverage report generates (HTML + text) without errors. Files should show partial coverage (basic level, not 100%).

### Step 4: Final commit if any fixes were needed

If step 2 or 3 surfaced minor issues (e.g. tsconfig needed adjustment), commit the fix separately:

```bash
git add -A
git commit -m "chore(frontend): fix test typecheck / coverage issues"
```

If nothing needed fixing, skip this commit.

---

## Self-Review Notes (for the plan author)

**Spec coverage:**
- PurlResolver (7 tests): ✓ all 7 spec scenarios covered.
- SbomUpdater (10 tests): ✓ all 9 spec scenarios covered + 1 extra (disabled-button guard).
- ImagesListConverter (8 tests): ✓ all 5–8 spec scenarios covered.
- DatabaseAdmin (18 tests): ✓ all spec scenarios covered.
- useDownload (12 tests): ✓ 6 spec scenarios for safeUrl + 3 for downloadJson.
- usePagination (8 tests): ✓ 5 spec scenarios + 3 extras (edge cases like empty total).
- Spec doc update (Task 7): ✓.
- Acceptance criteria (Task 8): ✓.

**Type consistency:** All mock signatures mirror the real `frontend/src/api/*.ts` exports. `ResolveResponse`, `PurlListResponse`, `SbomResponse`, `ImagesListResponse`, `ApiError` all imported from `frontend/src/types/api.ts` and `frontend/src/api/client.ts` consistently.

**Placeholder scan:** No TBD/TODO/incomplete steps. All code blocks contain actual implementation, all commands are exact.

**Risks:**
- The DatabaseAdmin tests use `vi.spyOn(document, 'createElement')` which may interact with happy-dom internals. If a test fails because of this, fall back to verifying via `URL.createObjectURL` spy only (the click happens implicitly).
- The `vi.mocked(window.confirm).mockReturnValueOnce(false)` syntax requires the spy to be set up first; this is ensured by the `beforeEach`.

**Plan total: 8 tasks, ~52 tests across 6 files, 9 commits.**