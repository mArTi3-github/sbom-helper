# Frontend Test Framework + Settings.vue Tests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Vitest to the frontend toolchain and a baseline of 8 tests for `Settings.vue` covering auto-save, debounce, blur, toast, and clear-token behaviour.

**Architecture:** Vitest with happy-dom and Vue plugin is configured in a dedicated `frontend/vitest.config.ts`. The test file lives next to its component (`Settings.test.ts`) and mocks the API client module. Timer-based behaviour (debounce, toast) uses `vi.useFakeTimers()`.

**Tech Stack:** Vitest, @vue/test-utils, happy-dom, @vitest/coverage-v8. Existing Vue 3 + Vite + TypeScript stack.

## Global Constraints

- All test imports are explicit (`import { describe, it, expect, vi } from 'vitest'`); no globals.
- DOM environment: `happy-dom`.
- Coverage provider: `v8`; reporters `text` and `html` (no thresholds, no CI enforcement).
- Timer mocking strategy: `vi.useFakeTimers()` + `vi.advanceTimersByTime(500)` + `await flushPromises()` to drain microtasks after each debounce tick.
- The test file lives at `frontend/src/views/Settings.test.ts` (colocated with the component, matching Vue community convention).
- API client is mocked via `vi.mock('../api/settings')` — no real network calls.

---

## File Structure

**Create:**
- `frontend/vitest.config.ts` — Vitest configuration.
- `frontend/src/views/Settings.test.ts` — 8 tests for `Settings.vue`.

**Modify:**
- `frontend/package.json` — add 4 devDependencies + 3 scripts.
- `specs/domains/web-ui.md` — append one bullet to the Settings Page section.

---

### Task 1: Install test dependencies

**Files:**
- Modify: `frontend/package.json` (add devDependencies)

- [ ] **Step 1: Add devDependencies to `frontend/package.json`**

Open `frontend/package.json` and add the following four entries inside the existing `devDependencies` object (after the last existing entry):

```json
"vitest": "^3.2.4",
"@vue/test-utils": "^2.4.6",
"happy-dom": "^20.0.2",
"@vitest/coverage-v8": "^3.2.4"
```

The exact version pins are not load-bearing — they are reasonable floors; if a newer minor is already in the lockfile-style cache, that is fine. The four entries must end up alphabetically placed or grouped at the end of `devDependencies`. After the edit, the `devDependencies` block should look like:

```json
"devDependencies": {
  "@types/node": "^24.12.3",
  "@vitejs/plugin-vue": "^6.0.6",
  "@vitest/coverage-v8": "^3.2.4",
  "@vue/test-utils": "^2.4.6",
  "@vue/tsconfig": "^0.9.1",
  "happy-dom": "^20.0.2",
  "typescript": "~6.0.2",
  "vite": "^8.0.12",
  "vitest": "^3.2.4",
  "vue-tsc": "^3.2.8"
}
```

- [ ] **Step 2: Run npm install inside `frontend/`**

Run:

```bash
npm install --prefix frontend
```

Expected: installs the four new packages and their transitive deps; no errors.

- [ ] **Step 3: Verify `vitest` binary is callable**

Run:

```bash
npx --prefix frontend vitest --version
```

Expected: prints a version string such as `3.2.4` (or whatever was actually resolved).

- [ ] **Step 4: Commit**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "chore(frontend): add vitest, @vue/test-utils, happy-dom, coverage-v8"
```

---

### Task 2: Create Vitest config and add `test` scripts

**Files:**
- Create: `frontend/vitest.config.ts`
- Modify: `frontend/package.json` (add 3 scripts)

- [ ] **Step 1: Write `frontend/vitest.config.ts`**

Create the file with these contents:

```ts
import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  test: {
    environment: 'happy-dom',
    globals: false,
    include: ['src/**/*.{test,spec}.ts'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html'],
      include: ['src/**/*.{ts,vue}'],
      exclude: ['src/**/*.{test,spec}.ts', 'src/main.ts', 'src/router/**'],
    },
  },
})
```

- [ ] **Step 2: Add `test` scripts to `frontend/package.json`**

Inside the `scripts` block, add these three entries (place them after the existing `"preview"` line so the block stays alphabetical-ish):

```json
"test": "vitest run",
"test:watch": "vitest",
"test:coverage": "vitest run --coverage"
```

After the edit the `scripts` block should look like:

```json
"scripts": {
  "dev": "vite",
  "build": "vue-tsc -b && vite build",
  "preview": "vite preview",
  "test": "vitest run",
  "test:watch": "vitest",
  "test:coverage": "vitest run --coverage"
}
```

- [ ] **Step 3: Verify Vitest runs against an empty test suite**

Run:

```bash
npm test --prefix frontend
```

Expected output ends with something like:

```
No test files found, exiting with code 0

Test Files  0 passed (0)
```

Exit code 0. (If a future Vitest version prints "no tests found" without code 0, that is acceptable; the important thing is no crash from the config.)

- [ ] **Step 4: Commit**

```bash
git add frontend/vitest.config.ts frontend/package.json
git commit -m "chore(frontend): add vitest config and test scripts"
```

---

### Task 3: Create `Settings.test.ts` with all 8 tests

**Files:**
- Create: `frontend/src/views/Settings.test.ts`

**Interfaces:**
- Mocked `getSettings` returns a `SettingsResponse`-shaped object with predictable defaults.
- Mocked `updateSettings` returns the same shape (a successful PATCH) or rejects (for the error toast test).
- `flushPromises()` helper resolves the microtask queue (required because `updateSettings` is async and `loadSettings` is awaited inside `autoSave`).

- [ ] **Step 1: Create the test file with mocks and a helper**

Create `frontend/src/views/Settings.test.ts` with the following contents:

```ts
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
```

> Note: the `findToggle` helper is intentionally omitted — tests use positional checkbox indices (`checkboxes[0]` for `validate_db_urls`) since the three toggles have a stable order in the rendered DOM.

- [ ] **Step 2: Write test 1 — renders loaded settings**

Append after the helpers (inside the same file, before any `describe`):

```ts
describe('Settings.vue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    successUpdate.mockResolvedValue(defaultSettings)
    getSettingsMock.mockResolvedValue(defaultSettings)
  })

  it('renders the loaded settings', async () => {
    const wrapper = mountSettings()
    await flushPromises()
    expect(wrapper.find('.loading').exists()).toBe(false)
    expect(wrapper.findAll('input[type="number"]').length).toBeGreaterThan(0)
    expect(wrapper.findAll('input[type="password"]').length).toBe(3)
    expect(getSettingsMock).toHaveBeenCalledTimes(1)
  })
})
```

- [ ] **Step 3: Run tests; verify only test 1 passes**

Run:

```bash
npx --prefix frontend vitest run src/views/Settings.test.ts
```

Expected: 1 test passes; no other tests exist yet.

- [ ] **Step 4: Add test 2 — toggle change triggers debounced PATCH**

Add the following inside the `describe` block:

```ts
  it('auto-saves toggle change after debounce', async () => {
    vi.useFakeTimers()
    try {
      const wrapper = mountSettings()
      await flushPromises()

      const checkboxes = wrapper.findAll<HTMLInputElement>('input[type="checkbox"]')
      expect(checkboxes.length).toBeGreaterThanOrEqual(1)
      await checkboxes[0].setValue(true)
      await flush()
      expect(successUpdate).not.toHaveBeenCalled()

      await flush(500)
      expect(successUpdate).toHaveBeenCalledTimes(1)
      expect(successUpdate).toHaveBeenCalledWith({ validate_db_urls: true })
    } finally {
      vi.useRealTimers()
    }
  })
```

- [ ] **Step 5: Add test 3 — debounce coalesces rapid changes**

Add:

```ts
  it('coalesces rapid toggle changes into a single PATCH', async () => {
    vi.useFakeTimers()
    try {
      const wrapper = mountSettings()
      await flushPromises()

      const checkboxes = wrapper.findAll<HTMLInputElement>('input[type="checkbox"]')
      await checkboxes[0].setValue(true)
      await flush()
      await checkboxes[0].setValue(false)
      await flush()
      await checkboxes[0].setValue(true)
      await flush(500)

      expect(successUpdate).toHaveBeenCalledTimes(1)
      expect(successUpdate).toHaveBeenCalledWith({ validate_db_urls: true })
    } finally {
      vi.useRealTimers()
    }
  })
```

- [ ] **Step 6: Add test 4 — password blur with value triggers PATCH**

Add:

```ts
  it('triggers PATCH on password blur when value is non-empty', async () => {
    const wrapper = mountSettings()
    await flushPromises()

    const pwInputs = wrapper.findAll<HTMLInputElement>('input[type="password"]')
    expect(pwInputs.length).toBe(3)

    await pwInputs[0].setValue('ghp_test_token')
    await pwInputs[0].trigger('blur')
    await flushPromises()

    expect(successUpdate).toHaveBeenCalledWith({ github_token: 'ghp_test_token' })
    expect((pwInputs[0].element as HTMLInputElement).value).toBe('')
  })
```

- [ ] **Step 7: Add test 5 — password blur with empty value does nothing**

Add:

```ts
  it('does not PATCH on password blur when value is empty', async () => {
    const wrapper = mountSettings()
    await flushPromises()

    const pwInputs = wrapper.findAll<HTMLInputElement>('input[type="password"]')
    await pwInputs[0].trigger('blur')
    await flushPromises()

    expect(successUpdate).not.toHaveBeenCalled()
  })
```

- [ ] **Step 8: Add test 6 — success toast appears**

Add:

```ts
  it('shows success toast after a successful PATCH', async () => {
    vi.useFakeTimers()
    try {
      const wrapper = mountSettings()
      await flushPromises()

      const checkboxes = wrapper.findAll<HTMLInputElement>('input[type="checkbox"]')
      await checkboxes[0].setValue(true)
      await flush(500)
      await flushPromises()

      const toast = wrapper.find('.toast')
      expect(toast.exists()).toBe(true)
      expect(toast.classes()).toContain('toast-ok')
      expect(toast.text()).toBe('Settings saved')
    } finally {
      vi.useRealTimers()
    }
  })
```

- [ ] **Step 9: Add test 7 — error toast on PATCH failure**

Add:

```ts
  it('shows error toast when PATCH fails', async () => {
    vi.useFakeTimers()
    try {
      successUpdate.mockRejectedValueOnce(new Error('boom'))
      const wrapper = mountSettings()
      await flushPromises()

      const checkboxes = wrapper.findAll<HTMLInputElement>('input[type="checkbox"]')
      await checkboxes[0].setValue(true)
      await flush(500)
      await flushPromises()

      const toast = wrapper.find('.toast')
      expect(toast.exists()).toBe(true)
      expect(toast.classes()).toContain('toast-err')
      expect(toast.text()).toBe('Failed to save: boom')
    } finally {
      vi.useRealTimers()
    }
  })
```

- [ ] **Step 10: Add test 8 — clear token sends PATCH with null**

First add a `beforeEach` update so the mocked `token_set` includes a set GitHub token for this test. The simpler approach is to override the mock in this single test:

```ts
  it('sends PATCH with null when Clear token is clicked', async () => {
    getSettingsMock.mockResolvedValueOnce({
      ...defaultSettings,
      token_set: { github_token: true, librariesio_api_key: false, ecosystems_api_key: false },
    })
    const wrapper = mountSettings()
    await flushPromises()

    const clearBtn = wrapper.findAll('button').find((b) => b.text() === 'Clear token')
    expect(clearBtn).toBeDefined()
    await clearBtn!.trigger('click')
    await flushPromises()

    expect(successUpdate).toHaveBeenCalledWith({ github_token: null })
  })
```

- [ ] **Step 11: Run all tests; verify 8 pass**

Run:

```bash
npx --prefix frontend vitest run src/views/Settings.test.ts
```

Expected: `Test Files  1 passed (1)`, `Tests  8 passed (8)`.

If any test fails, read the failure carefully and fix the test or the component before continuing — do not silence failures with `.skip()` or `.only()`.

- [ ] **Step 12: Run type-check to catch regressions**

Run:

```bash
npm run build --prefix frontend
```

Expected: build succeeds with no TypeScript errors.

- [ ] **Step 13: Commit**

```bash
git add frontend/src/views/Settings.test.ts
git commit -m "test(settings): cover auto-save, debounce, blur, toast, clear-token"
```

---

### Task 4: Update the web-ui spec note

**Files:**
- Modify: `specs/domains/web-ui.md`

- [ ] **Step 1: Append a test-coverage bullet to the Settings Page section**

Open `specs/domains/web-ui.md`. The Settings Page section ends at the line:

```
- Success and error feedback is shown via a single toast in the bottom-right corner of the viewport (3s for success, 5s for error)
```

Append a new bullet below it:

```
- Component is covered by `frontend/src/views/Settings.test.ts` (Vitest) with tests for auto-save, debounce, blur logic, success/error toast, and clear-token behaviour
```

- [ ] **Step 2: Commit**

```bash
git add specs/domains/web-ui.md
git commit -m "docs(specs): note Settings.vue test coverage"
```

---

### Task 5: Final verification

**Files:** none

- [ ] **Step 1: Run the full test suite**

Run:

```bash
npm test --prefix frontend
```

Expected: `Test Files  1 passed (1)`, `Tests  8 passed (8)`, exit code 0.

- [ ] **Step 2: Run coverage**

Run:

```bash
npm run test:coverage --prefix frontend
```

Expected: coverage report printed; `frontend/coverage/` directory created with HTML output; `Settings.vue` shows partial coverage (not all lines are tested — that's expected for "basic" coverage).

- [ ] **Step 3: Run production build**

Run:

```bash
npm run build --prefix frontend
```

Expected: build succeeds, no TypeScript errors, output unchanged in size from the previous baseline.

- [ ] **Step 4: Commit only if any incidental fix-ups were made**

If a fix-up commit is required (e.g., to silence an unrelated lint warning that surfaced during the build), commit it with a focused message; otherwise no commit.

---

## Self-Review

**1. Spec coverage:**
- Add 4 devDependencies → Task 1.
- Create `vitest.config.ts` with happy-dom + coverage-v8 → Task 2.
- Add `test`, `test:watch`, `test:coverage` scripts → Task 2.
- 8 specific test scenarios (render, toggle, debounce coalesce, blur non-empty, blur empty, success toast, error toast, clear-token) → Task 3 Steps 2, 4-10.
- Spec note about test coverage → Task 4.

**2. Placeholder scan:** No TBD/TODO/"implement later" markers. All test bodies and config files contain real code. The one forward-reference in Task 3 Step 1 (the `findToggle` helper kept "only if a test needs it") is acknowledged but never used; subsequent tests use positional checkbox indices instead, so the helper is dead code. Fix: remove it. Updated Task 3 Step 1 above already shows the helper as present-but-unused; it should be removed for cleanliness.

**3. Type consistency:** Mocked `updateSettings` is typed via `vi.fn()` and inferred; `SettingsResponse` matches `frontend/src/types/api.ts`. Field names in test bodies (`validate_db_urls`, `github_token`, etc.) match the API. The `flushPromises` import from `@vue/test-utils` is exported by `@vue/test-utils` >= 2.4 and is the standard helper for this pattern.