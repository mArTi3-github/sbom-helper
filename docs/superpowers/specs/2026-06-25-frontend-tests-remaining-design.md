# Frontend Tests — Remaining Components

## Description

Add Vitest unit tests for the four remaining views (`PurlResolver`, `SbomUpdater`, `ImagesListConverter`, `DatabaseAdmin`) and two composables (`useDownload`, `usePagination`). The trivial components (`NotFound`, `AppNav`, `FileUploadZone`, `ModalDialog`) are deliberately excluded (YAGNI) — they contain minimal logic and would yield tests with low signal-to-noise.

The goal is **basic, user-facing coverage** — not exhaustive testing. The reference style is `frontend/src/views/Settings.test.ts`: explicit `vitest` imports, module-level `vi.mock('../api/<module>')`, fake timers via `vi.useFakeTimers()` + `vi.advanceTimersByTime()` + `await flushPromises()`, and assertions on mock call counts/arguments and DOM state.

## Goals & Non-Goals

### Goals
- Cover critical user flows in each remaining view (resolve, enrich SBOM, convert images, manage DB).
- Cover edge cases: empty input, network errors (`ApiError` + generic `Error`), validation, loading states.
- Cover the two composables as separate unit tests (clean logic, especially security-relevant `safeUrl`).
- Maintain the existing `Settings.test.ts` style for consistency and AI-agent navigability.

### Non-Goals
- 100% line/branch coverage. Target is **basic coverage** — focus on non-trivial branches (user actions, network errors, edge cases).
- Tests for trivial components (`NotFound`, `AppNav`, `FileUploadZone`, `ModalDialog`).
- CSS class assertions for status badges (e.g. `status-found`, `badge-high`) — too brittle; text-based assertions are preferred.
- E2E tests — out of scope for this iteration.
- Adding new test dependencies beyond the already-installed `vitest`, `@vue/test-utils`, `happy-dom`, `@vitest/coverage-v8`.

## Conventions (apply to all six new test files)

1. **Explicit imports** from `'vitest'` — no globals (`globals: false` is set in `vitest.config.ts`).
2. **Module-level API mocking** via `vi.mock('../api/<module>')` — exports are replaced with `vi.fn()` stubs.
3. **Browser API mocking** when needed:
   - `vi.spyOn(window, 'confirm').mockReturnValue(true)` for `DatabaseAdmin` delete confirmations.
   - `vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:fake')` for CSV export.
4. **Fake timers** for debounce/timeouts via `vi.useFakeTimers()` inside `try { ... } finally { vi.useRealTimers() }`.
5. **Vue mounting** via `mount(Component)` from `@vue/test-utils`, followed by `await flushPromises()` for initial data loads.
6. **Assertions**: mock call counts, mock call arguments, DOM presence/absence, error text.
7. **Typing**: import fixtures from `frontend/src/types/api.ts` for typed responses.
8. **Cleanup**: `beforeEach` with `vi.clearAllMocks()` and reset of `mockResolvedValue` for all mocked functions.
9. **Test file location**: co-located with source — `Component.vue` → `Component.test.ts` next to it.

## Test Files Overview

| File | Type | Mount? | # Tests | Primary coverage |
|---|---|---|---|---|
| `frontend/src/views/PurlResolver.test.ts` | View | yes | 7 | Resolve PURL flow + errors + details toggle |
| `frontend/src/views/SbomUpdater.test.ts` | View | yes | 9 | File upload, options, ignore patterns, process, AbortSignal |
| `frontend/src/views/ImagesListConverter.test.ts` | View | yes | 5 | Convert SBOM → images list + errors + download |
| `frontend/src/views/DatabaseAdmin.test.ts` | View | yes | ~18 | Filter, sort, select, edit, delete, import, export, paginate, errors |
| `frontend/src/composables/useDownload.test.ts` | Composable | no | 6 | `downloadJson`, `safeUrl` edge cases |
| `frontend/src/composables/usePagination.test.ts` | Composable | no | 5 | State, computed, guard logic |

**Total: ~50 tests in 6 files.**

---

## PurlResolver.test.ts

**Mocks:** `../api/purl` (`resolvePurl`).

### Test scenarios

1. **renders initial form** — title, input, resolve button; resolve button is enabled; no loading/result/error shown.
2. **does not submit when input is empty** — typing nothing, click Resolve; `resolvePurl` is not called (HTML `required` attribute prevents submission, but verify no API call).
3. **shows loading state during resolve** — mock `resolvePurl` with a deferred promise; click Resolve; verify `.loading` element is shown; await flush; verify it's hidden.
4. **renders resolved result on success** — mock with a `ResolveResponse` containing `repository_url`, `confidence: 'high'`, `evidence`, `warnings`, `version_reference`, `found_by`, `resolver`; verify result card with anchor link to repo URL, confidence badge text, and details toggle present.
5. **toggles details section** — click "Show details", verify `dl` with details items becomes visible; click again, verify hidden.
6. **shows error message on `ApiError`** — mock `resolvePurl.mockRejectedValueOnce(new ApiError(404, 'not_found', 'No repository found'))`; click Resolve; verify `.error-msg` with the API message is shown; verify no result card.
7. **shows network error on generic Error** — mock `resolvePurl.mockRejectedValueOnce(new Error('network'))`; verify `.error-msg` contains "Network error".

---

## SbomUpdater.test.ts

**Mocks:** `../api/sbom` (`getIgnorePatterns`, `saveIgnorePatterns`, `resolveSbom`).

### Test scenarios

1. **loads initial state with empty ignore patterns** — `getIgnorePatterns` returns `{ patterns: [] }`; verify one empty pattern row is rendered (default fallback).
2. **loads ignore patterns from API** — `getIgnorePatterns` returns two patterns; verify two rows are populated; verify `getIgnorePatterns` called once on mount.
3. **falls back to empty pattern row on load error** — `getIgnorePatterns.mockRejectedValueOnce(...)`; verify one empty pattern row is rendered (graceful degradation).
4. **adds and removes pattern rows** — click "Добавить строку"; verify new empty row appears; click ✕ button on row 0; verify row count decreases.
5. **saves ignore patterns and filters empty rows** — fill row with `{ field: 'purl', pattern: 'requests' }`, leave one empty row; click Save; verify `saveIgnorePatterns` called with array of non-empty patterns only; verify "Сохранено" text appears (then auto-resets via setTimeout — use fake timers).
6. **shows error when save patterns fails (ApiError)** — `saveIgnorePatterns.mockRejectedValueOnce(new ApiError(...))`; verify `.error-msg` with API message.
7. **process button is disabled when no file selected** — verify button has `disabled` attribute; click does nothing.
8. **processes SBOM on Process click and renders results** — emit `file-selected` via `FileUploadZone` (mock component or trigger event directly); click Process; verify `resolveSbom` called with `(file, removeUnresolved, validateRefs, ignorePatterns, AbortSignal)`; await; verify summary values (total/found/not_found) and one results table row.
9. **passes AbortSignal to resolveSbom** — separate check that the 5th argument to `resolveSbom` is an `AbortSignal` instance (regression guard against losing cancellation support).

---

## ImagesListConverter.test.ts

**Mocks:** `../api/images` (`convertImagesList`).

### Test scenarios

1. **renders initial empty state** — file not selected; convert button disabled; no result/error.
2. **convert button is disabled until file selected** — emit `file-selected` event on `FileUploadZone`; verify button enabled; click; verify `convertImagesList` called with the file.
3. **renders status card "no transformation needed"** — mock `{ was_transformed: false, images: [...], images_list: {...} }`; verify `.status-card.status-ok` rendered (green left border) with "Преобразований не требуется" text.
4. **renders status card "transformation performed"** — mock `{ was_transformed: true, ... }`; verify `.status-card.status-transformed` rendered with "Выполнено преобразование" text.
5. **renders images table with completeness flags** — mock images with `missing_version: true`, `missing_components: false`; verify table rows with correct ✓/✗ symbols in each column.
6. **shows error on ApiError** — `convertImagesList.mockRejectedValueOnce(new ApiError(...))`; verify `.error-msg` with API message; verify no results.
7. **shows network error on generic Error** — `convertImagesList.mockRejectedValueOnce(new Error())`; verify `.error-msg` contains "Network error".
8. **download button triggers JSON download** — after successful convert, click "Скачать список образов"; verify a download link is created (can mock `URL.createObjectURL` and check spy was called, or spy on `document.createElement` for `'a'` tag).

---

## DatabaseAdmin.test.ts

**Mocks:** `../api/db` (`listPurls`, `updatePurl`, `deletePurls`, `importCsv`, `exportSelectedCsv`).

**Browser mocks (beforeEach):** `vi.spyOn(window, 'confirm').mockReturnValue(true)`, `vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:fake')`.

### Test scenarios

1. **loads rows on mount** — `listPurls` returns `{ rows: [...], total: 100, page: 1, page_size: 50 }`; verify table rows rendered; verify `listPurls` called with default params (page=1, page_size=50, sort_by='resolved_at', sort_order='desc').
2. **applies filters on Apply click** — type search, set resolver filter, click Apply; verify `listPurls` called with new params including search/resolver, page reset to 1.
3. **resets filters on Reset click** — type search, click Reset; verify all inputs cleared, `listPurls` called with empty params.
4. **sorts by column header click** — click "PURL" header; verify `listPurls` called with `sort_by: 'purl', sort_order: 'asc'`; click again; verify order flips to `desc`.
5. **toggles row selection and select-all** — click row checkbox; verify count in "Export CSV (1)" / "Delete Selected (1)" buttons; click header checkbox; verify all rows selected (export button shows total count); uncheck header; verify none selected.
6. **enters edit mode and saves change on Enter** — double-click PURL cell, type new value, press Enter; verify `updatePurl` called with `{ purl: newValue }`; verify row re-renders with new value (mock `listPurls` again for re-fetch).
7. **enters edit mode and cancels on Escape** — start edit, press Escape; verify `updatePurl` not called; verify cell shows original value.
8. **saves inline edit on blur** — start edit, change value, click outside (trigger `blur`); verify `updatePurl` called.
9. **delete single row (confirm=true)** — click "Del" button on a row; verify `confirm` called with row purl; verify `deletePurls([purl])` called; verify success message shown; verify `listPurls` re-fetched.
10. **does not delete when confirm=false** — `window.confirm.mockReturnValue(false)`; click "Del"; verify `deletePurls` NOT called.
11. **delete selected (bulk)** — select 2 rows via checkboxes; click "Delete Selected"; verify `deletePurls` called with array of both purls.
12. **exports selected CSV** — select 2 rows; click "Export CSV"; verify `exportSelectedCsv` called with array of both purls; verify `URL.createObjectURL` called and download triggered.
13. **imports CSV file with upsert strategy** — open modal, emit file-selected, click Upload; verify `importCsv(file, 'upsert')` called; verify imported/skipped stats rendered; verify `listPurls` re-fetched.
14. **imports CSV file with skip_existing strategy** — set radio to "Skip existing", upload; verify `importCsv(file, 'skip_existing')` called.
15. **shows import error on ApiError** — `importCsv.mockRejectedValueOnce(new ApiError(...))`; verify `.error-msg` in modal with API message.
16. **paginates to next page** — set up `total: 100`; click "Next ›"; verify `listPurls` called with `page: 2`.
17. **changes page size** — select 100 in per-page dropdown; verify `listPurls` called with `page_size: 100, page: 1`.
18. **shows ApiError message on list failure** — `listPurls.mockRejectedValueOnce(new ApiError(500, ...))`; verify `.error-msg` with API message.
19. **shows network error on generic Error** — `listPurls.mockRejectedValueOnce(new Error())`; verify `.error-msg` contains "Network error".

**Note:** The actual count is ~18 tests (not 12 as initially estimated) due to the breadth of DatabaseAdmin's logic. This is still user-scenario-focused — each test maps to a real user action.

---

## useDownload.test.ts

**No mocks** — pure functions tested directly.

### Test scenarios

1. **downloadJson creates blob URL and triggers anchor click** — call `downloadJson({ a: 1 }, 'test.json')`; spy on `URL.createObjectURL` and `document.createElement`; verify blob URL created with correct mime type; verify `<a>` element clicked with correct `download` attribute; verify URL revoked.
2. **downloadJson handles complex data via JSON.stringify** — call with nested object; verify blob contains properly-formatted JSON.
3. **safeUrl returns undefined for null input** — `safeUrl(null)` → `undefined`.
4. **safeUrl returns undefined for undefined input** — `safeUrl(undefined)` → `undefined`.
5. **safeUrl returns '#' for javascript: protocol** — `safeUrl('javascript:alert(1)')` → `'#'`.
6. **safeUrl returns '#' for data: protocol** — `safeUrl('data:text/html,<script>...</script>')` → `'#'`.
7. **safeUrl returns '#' for vbscript: protocol** — `safeUrl('vbscript:msgbox(1)')` → `'#'`.
8. **safeUrl returns the URL unchanged for safe protocols** — `safeUrl('https://github.com/foo')` → `'https://github.com/foo'`; same for `http://`, `git://`, etc.

---

## usePagination.test.ts

**No mocks** — pure composable, called directly in test scope.

### Test scenarios

1. **initial state** — `usePagination()`; verify `page === 1`, `pageSize === 50`, `total === 0`, `totalPages === 1`.
2. **computes totalPages from total and pageSize** — set `total.value = 250`; verify `totalPages.value === 5` (Math.ceil(250/50)).
3. **totalPages is at least 1 when total is 0** — default state; verify `totalPages === 1` (not 0).
4. **goToPage navigates to valid page** — set total=200; call `goToPage(3)`; verify `page === 3`.
5. **goToPage ignores invalid pages (negative or beyond total)** — call `goToPage(-1)`; verify `page` unchanged; call `goToPage(999)`; verify `page` unchanged.
6. **changePageSize updates size and resets to page 1** — set `page.value = 3`, call `changePageSize(100)`; verify `pageSize === 100` and `page === 1`.
7. **reset returns to page 1** — set `page.value = 5`, call `reset()`; verify `page === 1`.

---

## Updates to specs/domains/web-ui.md

Add a new section **"Test Coverage"** after the "Settings Page" section listing all six tested files and noting the conventions used. This keeps the spec in sync with the implementation (per `specs/META.md` rule: spec updates after behavior changes).

---

## Acceptance Criteria

- All ~50 new tests pass: `npm test --prefix frontend` exits 0.
- All previously existing tests continue to pass (Settings.test.ts).
- `npm run build --prefix frontend` succeeds (no type errors from test files).
- `npm run test:coverage --prefix frontend` generates coverage report (HTML + text) without errors.
- Spec `specs/domains/web-ui.md` updated to reflect new test coverage.
- No new dependencies added to `frontend/package.json`.
- New test files follow the same conventions as `Settings.test.ts` (explicit imports, `vi.mock`, fake timers, typed fixtures).
- Spec doc committed to git as `docs/superpowers/specs/2026-06-25-frontend-tests-remaining-design.md`.

---

## Out of Scope (explicit)

- Tests for `NotFound.vue`, `AppNav.vue`, `FileUploadZone.vue`, `ModalDialog.vue` (trivially little logic).
- CSS class assertions for badges (too brittle vs text-based assertions).
- E2E tests (Playwright/Cypress).
- Coverage thresholds enforced in CI (out of scope for this iteration).
- Snapshot tests.