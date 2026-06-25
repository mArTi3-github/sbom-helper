# Frontend Test Framework + Settings.vue Basic Tests

**Date:** 2026-06-25
**Status:** Approved
**Scope:** Frontend tooling + one test file (`frontend/src/views/Settings.test.ts`) + one spec note (`specs/domains/web-ui.md`).

## Goal

Introduce Vitest as the frontend test framework and add a baseline of tests
for `Settings.vue` covering the auto-save behaviour implemented in the
previous task. Other view and component tests are explicitly out of scope
(separate session).

## Dependencies

Add to `frontend/package.json` under `devDependencies`:

- `vitest` — test runner.
- `@vue/test-utils` — Vue component mounting helpers.
- `happy-dom` — DOM environment (lighter than jsdom, sufficient for Vue).
- `@vitest/coverage-v8` — coverage provider.

No runtime dependencies are added.

## Configuration

Create `frontend/vitest.config.ts`:

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

Test config is separate from `vite.config.ts` to keep build and test
concerns isolated.

## `package.json` scripts

Add three scripts:

```
"test": "vitest run",
"test:watch": "vitest",
"test:coverage": "vitest run --coverage"
```

## Test file: `frontend/src/views/Settings.test.ts`

Mocks: `vi.mock('../api/settings')` provides stubs for `getSettings` and
`updateSettings` returning a realistic default settings object.

Timer strategy: `vi.useFakeTimers()` for debounce tests, with
`vi.advanceTimersByTime(500)` and `await flushPromises()` to resolve
microtasks after the debounced call fires.

### Test cases

1. **Renders loaded settings.** After `getSettings()` resolves, the page
   shows the toggle, the number inputs, and the password inputs with the
   returned values, and the loading indicator is gone.

2. **Toggle change triggers debounced PATCH.** Setting `validateDbUrls`
   to `true`, advancing timers by 500 ms, and flushing promises results
   in exactly one `updateSettings` call with
   `{ validate_db_urls: true }`.

3. **Debounce coalesces rapid changes.** Two rapid toggle changes
   (`false → true → false`) within the debounce window result in a single
   `updateSettings` call carrying the final value.

4. **Password blur with value triggers PATCH.** Entering a non-empty
   GitHub token and triggering blur causes `updateSettings` to be called
   with `{ github_token: <value> }`, and the input is cleared after
   success.

5. **Password blur with empty value does nothing.** Triggering blur on
   an empty password field does NOT call `updateSettings`.

6. **Success toast appears.** After a successful PATCH the DOM contains
   `.toast.toast-ok` with text `"Settings saved"`.

7. **Error toast appears on PATCH failure.** When `updateSettings`
   rejects, the toast element exists with class `.toast-err` and text
   `"Failed to save: <reason>"`.

8. **Clear token sends PATCH with null.** Clicking the `Clear token`
   button when a token is set results in `updateSettings` being called
   with `{ github_token: null }`.

## Spec update

`specs/domains/web-ui.md` — append one bullet to the `### Settings Page`
section:

> - Component is covered by `frontend/src/views/Settings.test.ts` (Vitest) with tests for auto-save, debounce, blur logic, success/error toast, and clear-token behaviour.

## Out of scope

- Tests for other views and components (separate session).
- CI integration (devops config).
- Coverage thresholds — coverage is reported, not enforced.
- E2E or browser tests.