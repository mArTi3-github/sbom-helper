# Web UI

## Description

A Vue 3 SPA with a landing page and six tool pages: a PURL resolver page accepting one or more PURLs per request, an SBOM-updater page for enriching CycloneDX SBOM files, a Fix SBOM page for applying selectable normalization fixes to CycloneDX SBOM documents, a database administration page for managing the `resolved_purls` table, a settings page for application configuration, and an Images List Converter page for transforming CycloneDX SBOM files into machine-readable lists of Docker container images.

## Key Files

- `frontend/src/views/HomePage.vue` — landing page: hero section and tiles linking to the six tool pages
- `frontend/src/views/PurlResolver.vue` — PURL resolver page: textarea input (one PURL per line, batch supported), resolve button, results table with per-PURL status, warnings, and resolver metadata
- `frontend/src/views/SbomUpdater.vue` — SBOM-updater page: file upload, options, ignore patterns editor, results summary and table
- `frontend/src/views/SbomFixer.vue` — Fix SBOM page: file upload, grouped fix options with master checkboxes, save/reset options, status card, statistics and issues spoilers, fixed-SBOM download
- `frontend/src/views/sbomFixerRules.ts` — single catalog of the 21 fix rules (rule id, option key, before/after JSON examples) that drives the rule rows of the Fix SBOM page
- `frontend/src/components/RuleHelp.vue` — presentational rule help: round "(i)" button and an inline panel with a description and "Before"/"After" snippets
- `frontend/src/views/SbomFixer.test.ts` — Vitest unit tests for the Fix SBOM page
- `frontend/src/views/DatabaseAdmin.vue` — database administration page: filterable/sortable table, inline editing, CSV import/export, bulk delete
- `frontend/src/views/Settings.vue` — settings page: URL validation, retry config, log level, JSON Format, APK resolver, deps.dev, ecosyste.ms, Libraries.io, and LLM resolver cards
- `frontend/src/views/ImagesListConverter.vue` — Images List Converter page: file upload, conversion status card, images table, download
- `frontend/src/views/NotFound.vue` — 404 catch-all page
- `frontend/src/router/index.ts` — Vue Router configuration (7 page routes + catch-all)
- `frontend/src/App.vue` — Root component: layout shell with `AppNav` + `<router-view>`
- `frontend/src/components/AppNav.vue` — Navigation bar shared across all pages
- `frontend/src/components/FileUploadZone.vue` — Reusable drag-and-drop file upload zone
- `frontend/src/components/ModalDialog.vue` — Reusable modal dialog
- `frontend/src/components/RecentJobs.vue` — Background job status list with auto-polling
- `frontend/src/components/db/DbDataTable.vue` — Sortable/filterable PURL data table for database admin
- `frontend/src/components/db/DbFilterPanel.vue` — Search, resolver filter (dynamically populated from `GET /api/v1/db/resolvers`), and date range controls for database admin
- `frontend/src/components/db/DbImportModal.vue` — CSV import dialog with drag-and-drop upload
- `frontend/src/api/client.ts` — Typed fetch wrapper with `ApiError` class
- `frontend/src/api/purl.ts` — PURL resolution API client
- `frontend/src/api/sbom.ts` — SBOM enrichment + ignore patterns + SBOM fix API client (`fixSbom`, `getFixOptions`, `saveFixOptions`)
- `frontend/src/api/db.ts` — Database admin API client (list, update, delete, import, export)
- `frontend/src/api/settings.ts` — Settings API client
- `frontend/src/i18n/index.ts` — vue-i18n configuration (Composition API mode, `legacy: false`)
- `frontend/src/i18n/locales/en.json` — English UI strings (grouped by domain)
- `frontend/src/i18n/locales/ru.json` — Russian UI strings (identical key structure)
- `frontend/src/tests/i18n.ts` — `mountWithI18n` helper for test mounting with vue-i18n plugin
- `frontend/src/api/jobs.ts` — Background job API client (create, poll, download, cancel, list)
- `frontend/src/api/images.ts` — Images list conversion API client
- `frontend/src/types/api.ts` — TypeScript interfaces mirroring backend response models; the SBOM fix types mirror `sbom/fixer.py` (`SbomFixOptions` and its nested option models mirror the Pydantic models; `SbomFixStat`/`SbomFixIssue` mirror the dataclasses) while `SbomFixResponse` mirrors the `routes/sbom_fix.py` response payload and `SbomFixOptionsResponse` mirrors the options endpoint payload
- `frontend/src/composables/useDownload.ts` — File download helper composable
- `frontend/src/stores/useSettingsStore.ts` — Pinia store for application settings state (shared across views)
- `frontend/src/stores/useDbAdminStore.ts` — Pinia store for database admin state (filtering, sorting, selection, pagination, page size, goToPage, changePageSize, resolver list via `resolvers` ref and `fetchResolvers()` action)
- `frontend/src/assets/main.css` — Global CSS variables and resets
- `src/purl_resolver/main.py` — Mounts SPA via `SPAStaticFiles` at `/` after all API routes

## Flows

### PURL Resolution (single or batch)

```
User                   Browser (Vue SPA)             API Layer
  |                       |                           |
  | Navigate to           |                           |
  | /purl-resolver        |                           |
  |---------------------->|                           |
  |                       | GET /purl-resolver        |
  |                       | (SPA fallback, index.html)|
  |                       |-------------------------->|
  |                       | 200 index.html            |
  |                       |<--------------------------|
  |                       | Vue Router mounts         |
  |                       | PurlResolver.vue          |
  |                       |                           |
  | Enters one or more     |                           |
  | PURLs (one per line),  |                           |
  | clicks "Resolve"       |                           |
  |---------------------->|                           |
  |                       | POST /api/v1/resolve/batch |
  |                       | {"purls": [...]}          |
  |                       |-------------------------->|
  |                       | 200 {results: [...]}      |
  |                       |<--------------------------|
  | Sees results table    |                           |
  | (one row per PURL)    |                           |
  |<----------------------|                           |
```

### SBOM Enrichment

```
User                   Browser (Vue SPA)             API Layer
  |                       |                           |
  | Navigate to /sbom-updater                        |
  |---------------------->|                           |
  |                       | Vue Router mounts         |
  |                       | SbomUpdater.vue           |
  |                       | (no full-page reload)     |
  |                       |                           |
  | Selects .json file,   |                           |
  | toggles remove option,|                           |
  | clicks process button |                           |
  |---------------------->|                           |
  |                       | POST /api/v1/resolve/sbom |
  |                       | (multipart/form-data +    |
  |                       |  optional booleans)       |
  |                       |-------------------------->|
  |                       | 200 {summary, enriched}   |
  |                       |<--------------------------|
  | Sees results table    |                           |
  | with summary cards    |                           |
  | (including removed)   |                           |
  | and download button   |                           |
  |<----------------------|                           |
```

### Fix SBOM

```
User                   Browser (Vue SPA)             API Layer
  |                       |                           |
  | Navigate to /fix-sbom |                           |
  |---------------------->|                           |
  |                       | Vue Router mounts          |
  |                       | SbomFixer.vue              |
  |                       | GET /api/v1/sbom/fix/options
  |                       |-------------------------->|
  |                       | 200 {options} or defaults  |
  |                       |<--------------------------|
  | Reviews/toggles rules,|                           |
  | optionally saves them |                           |
  |---------------------->| POST /api/v1/sbom/fix/options
  |                       |-------------------------->|
  |                       | 200 {status: "saved"}      |
  |                       |<--------------------------|
  | Selects .json file,   |                           |
  | clicks "Fix SBOM"     |                           |
  |---------------------->|                           |
  |                       | POST /api/v1/sbom/fix      |
  |                       | (multipart: file + options |
  |                       |  JSON string)              |
  |                       |-------------------------->|
  |                       | 200 {changed, fixed_sbom,  |
  |                       |      stats, issues}        |
  |                       |<--------------------------|
  | Sees status card,     |                           |
  | statistics spoiler,   |                           |
  | issues report, and    |                           |
  | downloads *_fixed.json|                           |
  |<----------------------|                           |
```

### Images List Conversion

```
User                   Browser (Vue SPA)             API Layer
  |                       |                           |
  | Navigate to /images-list-converter               |
  |---------------------->|                           |
  |                       | Vue Router mounts         |
  |                       | ImagesListConverter.vue   |
  |                       | (no full-page reload)     |
  |                       |                           |
  | Selects .json file,   |                           |
  | clicks convert button |                           |
  |---------------------->|                           |
  |                       | POST /api/v1/convert/images-list
  |                       | (multipart/form-data)     |
  |                       |-------------------------->|
  |                       | 200 {was_transformed,     |
  |                       |      images, images_list} |
  |                       |<--------------------------|
  | Sees status card,     |                           |
  | images table with     |                           |
  | completeness flags,   |                           |
  | and download button   |                           |
  |<----------------------|                           |
```

## Invariants

### PURL Resolver Page

- The page never reloads during resolution (Vue reactivity, no full-page navigation)
- Input is a textarea: one PURL per line; empty lines are ignored; multiple lines are sent as a batch to `POST /api/v1/resolve/batch`
- Results are rendered as a table with one row per input PURL (status, repository URL, warnings, resolver, found_by)
- Submit button is disabled while a request is in flight
- All states (loading, success, unresolved, error, network failure) have distinct visual representations
- Warnings within a resolved row are shown in red; the unresolved fallback message is shown in yellow; errors in red
- `found_by` and `resolver` fields are displayed in the details section when present

### SBOM-updater Page

- The page never reloads during enrichment (Vue reactivity, no full-page navigation)
- Upload area supports drag-and-drop and file picker (via `FileUploadZone` component)
- Process button is disabled until a file is selected
- "Remove unresolved components without subcomponents" checkbox controls `remove_unresolved_no_subcomponents` form parameter
- "Validate pre-existing URLs from SBOM" checkbox controls `validate_existing_refs` form parameter; when checked, existing VCS externalReferences in the SBOM are validated via HEAD + git ls-remote — invalid URLs trigger re-resolution
- Ignore patterns editor: dynamic rows with field/pattern inputs, add/remove buttons, save button; patterns are persisted via `POST /api/v1/sbom/ignore-patterns` and loaded on page mount
- Loading spinner is shown during server-side processing
- Results table displays: PURL (normalized), status (Found/Not found/Removed/Ignored), repository URL (clickable), found_by, resolver; all display strings are translated via i18n keys
- Summary cards show: total PURLs, found, not found, skipped, removed, ignored; labels are translated via i18n keys
- Download enriched SBOM button triggers JSON file download (via `useDownload` composable); indent size comes from `store.jsonIndent` (settings-controlled); button label is translated via i18n
- All states (empty, loading, success, partial, error, network failure) have distinct visual representations

### Fix SBOM Page

- The page never reloads during fixing (Vue reactivity, no full-page navigation)
- On mount the page loads saved options via `GET /api/v1/sbom/fix/options` and application settings (`useSettingsStore().load()` for `jsonIndent`) in parallel; the page is available at `/fix-sbom` and the nav/home entry uses the `sbomFixer` i18n namespace
- If loading saved options fails (network/500), the built-in defaults are used and a non-blocking warning is shown; if loading settings fails, the page still works and downloads use `jsonIndent = 4`
- Defaults: every option enabled except `metadata_component.remove_purl` and `components.fill_missing_gost_properties`; `specVersion = "1.7"`
- Every rule row has a round "(i)" help button; clicking it expands an inline panel under the row inside the group card with a description of the rule and "Before"/"After" snippets of a CycloneDX JSON fragment
- At most one help panel is open at a time; clicking the same button again closes it, and pressing Escape closes the panel while focus is inside the rule's help control (for example right after clicking the "i" button); the button sits outside the rule's `<label>`, so opening help never toggles the rule's checkbox
- Rule rows are rendered from the `sbomFixerRules.ts` catalog in catalog order; in the `metadata` card `metadata.reorder` is the first row, matching the reorder-first order of the other blocks; the order of entries in the statistics spoiler is still defined by the backend (`RULE_IDS`), not by the catalog
- Options are grouped into `root`, `metadata` (with a `metadata.component` sub-block), and `components` cards
- Each group and the `metadata.component` sub-block has a master checkbox: checked when all its child options are on, indeterminate when only some are; toggling it sets all its children; the `metadata` master also covers `metadata.component.*`, while the sub-block master changes only `metadata_component.*`; "select all"/"clear all" buttons operate on their own group only
- The `specVersion` text input is enabled only while `root.set_spec_version` is checked
- The current form values are used for a run immediately; "Save settings" persists them via `POST /api/v1/sbom/fix/options` and shows "Saved" or the translated save error next to the button; "Reset defaults" restores built-in defaults locally without saving
- A new file selection resets results and errors but keeps the current options
- The "Fix SBOM" button is disabled until a file is selected and while a request is in flight; a spinner is shown during processing
- The results area shows a status card ("changes applied" / "no changes required"), a statistics spoiler open by default (all enabled rules, including zero counts), and either a green "no issues remaining" card or an issues spoiler closed by default with the issue count; the issues table is rendered only while the spoiler is open and scrolls within a bounded height
- Statistics and issue labels are translated via i18n; issue details are formatted from `details` (for example the missing GOST names joined by commas), with the full value in `title`; unknown issue codes fall back to the bare code
- The "Download fixed SBOM" button triggers a JSON download via `useDownload`; the file name is `<input name without .json>_fixed.json` and the indent comes from `store.jsonIndent` (settings-controlled)
- All states (empty, loading, changed, unchanged, with/without issues, error, network failure) have distinct visual representations
- API errors are translated via `t('errors.' + errorCode, errorData)`; network failures use `errors.network_error`; unexpected errors use `errors.unexpected_error`

### DB-Admin Page

- The page never reloads during data operations (Vue reactivity, no full-page navigation)
- Resolver filter dropdown is dynamically populated on mount via `fetchResolvers()` call to `GET /api/v1/db/resolvers`; on fetch failure, dropdown shows only «Any» (graceful degradation)
- All columns are displayed by default (no visibility checkboxes)
- All states (loading, empty, error, success) have distinct visual representations
- Edits update via PATCH and re-fetch the current page
- Export exports the currently selected rows via comma (`,`) delimited CSV; button shows selected count and is disabled when no rows are selected
- Import accepts comma (`,`) delimiter; UTF-8 encoding (BOM handled automatically); first row must contain headers; required columns: `purl`, `repository_url`; optional columns: `resolver` (default `import-csv`), `resolved_at`; values containing commas must be quoted per RFC 4180
- Import modal includes a collapsible CSV format reference section listing required/optional columns and a multi-column example using `,` delimiter
- Import strategy radio labels: "Overwrite existing" (upsert) and "Skip existing" (skip_existing)
- Import modal supports drag-and-drop for CSV files (via `FileUploadZone` and `ModalDialog` components)
- Pagination is managed by `useDbAdminStore` (Pinia store with `goToPage`, `changePageSize`, `totalPages` computed state)

### Settings Page

- Settings page is accessible at `/settings` via Vue Router; nav-bar link present on all pages (via `AppNav` component)
- Language card: dropdown selects UI language (`en` or `ru`); choice is persisted to `localStorage` immediately and to backend via `PATCH /api/v1/settings` with `language` field
- URL Validation card: toggle switch controls `validate_db_urls`, number input controls `url_validation_timeout` (1–60 seconds), number input controls `revalidation_cooldown_hours` (0–720, default 24; 0 disables cooldown)
- Retry Configuration card: number input controls `retry_max_attempts` (1–10), number input controls `retry_base_cooldown_seconds` (0.5–120)
- Log Level card: dropdown controls `log_level` (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- APK Resolver card: enable toggle (controls `apk_resolver_enabled`), no API key, Alpine Linux APK packages resolve to `https://github.com/alpinelinux/aports` as a fallback
- Deps.dev Resolver card: enable toggle (controls `depsdev_enabled`), no API key required
- ecosyste.ms Resolver card: enable toggle, optional API key input (for higher rate limits), rate limit input (`ecosystems_max_requests_per_second`, 0.1–100), status badge (set/not set), clear button
- Libraries.io Resolver card: enable toggle, API key input, status badge (set/not set), clear button, link to libraries.io login
- LLM Resolver card: enable toggle, OpenAI-compatible base URL, API key (status badge, clear button), model name, attempts count (1–10), timeout (1–600 s); card controls are disabled while the resolver is off
- Settings are loaded from `GET /api/v1/settings` on page mount
- Settings are auto-saved to `PATCH /api/v1/settings` on field change (toggle/select/number) or on blur for password inputs; changes are debounced at 500ms
- Success and error feedback is shown via a single toast in the bottom-right corner of the viewport (3s for success, 5s for error); toast messages are translated via i18n keys
- JSON Format card: select controls `json_indent` (1 space, 2 spaces, 4 spaces; default 4); description explains the setting affects downloaded SBOM and Images List files
- Component is covered by `frontend/src/views/Settings.test.ts` (Vitest) with tests for auto-save, debounce, blur logic, success/error toast, and clear-token behaviour

### Images List Converter Page

- The page never reloads during conversion (Vue reactivity, no full-page navigation)
- Upload area supports drag-and-drop and file picker (via `FileUploadZone` component)
- Convert button is disabled until a file is selected
- Loading spinner is shown during server-side processing
- Status card displays: "No transformation needed" (green) if `was_transformed=false`, or "Transformation applied" (yellow) if `was_transformed=true`; `was_transformed` is true when containers were promoted from nested levels or when duplicate containers (same `purl`) were removed; status messages are translated via i18n keys
- Results table columns (translated via i18n): Image name, Version, Components populated, Name field populated, Properties populated, Duplicates removed
- Completeness flags use ✅ (green) when condition is met, ❌ (red) when not; empty cells only when condition is met and flag is positive
- Version cell shows ❌ inline when version is missing
- "Duplicates removed" column shows the number of container components with the same `purl` that were removed; shows em-dash (`—`) when no duplicates were removed
- Download image list button triggers JSON file download (via `useDownload` composable); indent size comes from `store.jsonIndent` (settings-controlled); button label is translated via i18n
- All states (empty, loading, success, error, network failure) have distinct visual representations

### Global

- All pages share a consistent navigation bar via `AppNav` component (Vue Router `<router-link>`): logo (home), PURL Resolver, SBOM Updater, Fix SBOM, Images List Converter, DB Admin, Settings
- The home page shows six tiles (one per tool page) linking to `/purl-resolver`, `/sbom-updater`, `/fix-sbom`, `/images-list-converter`, `/db-admin`, and `/settings`
- Vue Router uses `createWebHistory()` (HTML5 history mode, no hash)
- Catch-all route (`/:pathMatch(.*)*`) renders `NotFound.vue` for unknown paths
- SPA is served by FastAPI via `SPAStaticFiles` (custom `StaticFiles` subclass with fallback to `index.html` for client-side routing)
- API routes are registered before the SPA mount — API paths always take priority
- Each `.vue` component uses `<style scoped>` for CSS isolation
- Global CSS variables and resets are in `frontend/src/assets/main.css`
- Most TypeScript interfaces in `frontend/src/types/api.ts` mirror `src/purl_resolver/schemas.py` — any schema change must be reflected in both; the SBOM-fixer option types mirror `src/purl_resolver/sbom/fixer.py`, and `SbomFixResponse` mirrors the `src/purl_resolver/routes/sbom_fix.py` response payload
- All user-facing strings are translated via `vue-i18n` (Composition API mode, `legacy: false`); locale files at `frontend/src/i18n/locales/{en,ru}.json` share identical key structure
- Initial locale detection: `localStorage.getItem('locale')` → `navigator.language` (if starts with `ru`) → `'en'` (fallback); locale is persisted to `localStorage` on change and synced to backend via `PATCH /api/v1/settings` `language` field
- All error responses from the API return machine-readable `error` codes (no `message` field); the frontend translates error codes via `t('errors.' + errorCode, errorData)`

### Test Coverage

Frontend unit tests are written with **Vitest 4.1.9**, `@vue/test-utils 2.4.11`, and `happy-dom`. All tests follow the conventions established in `frontend/src/views/Settings.test.ts`:

- Explicit imports from `'vitest'` (no globals).
- Module-level API mocking via `vi.mock('../api/<module>')`.
- Fake timers via `vi.useFakeTimers()` + `vi.advanceTimersByTime()` + `await flushPromises()`.
- Vue mounting via `mountWithI18n()` (from `src/tests/i18n.ts`) + `await flushPromises()` for initial loads; `mountWithI18n` wraps `@vue/test-utils` `mount()` with vue-i18n plugin pre-installed.

**Tested files:**

- `frontend/src/views/Settings.test.ts` — auto-save, debounce, blur logic, success/error toast, clear-token behaviour.
- `frontend/src/views/PurlResolver.test.ts` — resolve flow, details toggle, ApiError and network errors.
- `frontend/src/views/SbomUpdater.test.ts` — ignore-patterns editor (add/remove/save), process flow, AbortSignal passed to `resolveSbom`.
- `frontend/src/views/SbomFixer.test.ts` — option loading and fallback warning, master/indeterminate checkboxes, select/clear all, reset defaults, save/reset status, spec-version input gating, fix flow, statistics and issues spoilers, issue-label fallback, downloads (`jsonIndent` fallback to 4), `ApiError` and network errors.
- `frontend/src/views/ImagesListConverter.test.ts` — conversion flow, status cards (transformed / not transformed), JSON download.
- `frontend/src/views/DatabaseAdmin.test.ts` — filter, sort, select, inline edit (Enter/Escape/blur), single and bulk delete (confirm branches), CSV export, CSV import (upsert / skip_existing), pagination (next page, page size), ApiError and network errors.
- `frontend/src/composables/useDownload.test.ts` — `downloadJson` blob/anchor behaviour, `safeUrl` dangerous-protocol rejection (javascript, data, vbscript).
- `frontend/src/components/RecentJobs.test.ts` — job status icons, polling, cancel/delete flow.

**Deliberately not tested (YAGNI):** `NotFound.vue`, `AppNav.vue`, `FileUploadZone.vue`, `ModalDialog.vue`, `DbDataTable.vue`, `DbFilterPanel.vue`, `DbImportModal.vue` — trivial or purely presentational components with minimal logic; tests would yield low signal-to-noise.

Run all frontend tests:

```bash
npm test --prefix frontend
```

Run with coverage:

```bash
npm run test:coverage --prefix frontend
```
