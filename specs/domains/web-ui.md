# Web UI

## Description

A Vue 3 SPA with a landing page and six tool pages: a PURL resolver page accepting one or more PURLs per request, an SBOM-updater page for enriching CycloneDX SBOM files, a Fix SBOM page for applying selectable normalization fixes to CycloneDX SBOM documents, a database administration page for managing the `resolved_purls` table, a settings page for application configuration, and an Images List Converter page for transforming CycloneDX SBOM files into machine-readable lists of Docker container images.

## Key Files

- `frontend/src/views/HomePage.vue` — landing page: hero section and tiles linking to the six tool pages
- `frontend/src/views/PurlResolver.vue` — PURL resolver page: textarea input (one PURL per line, batch supported), resolve button, results table with per-PURL status, warnings, and resolver metadata
- `frontend/src/views/SbomUpdater.vue` — SBOM-updater page: file upload, options, ignore patterns editor, results summary and table
- `frontend/src/views/SbomFixer.vue` — Fix SBOM page: file upload, fix options in four sections (basic fixes, `components[]` edits with a local three-column provided_by row editor and a PURL case mode selector, component license edits with an inline pattern editor, optional-fields whitelist) with master checkboxes on the first three, the optional-fields analysis card (analysis button, candidate table, two white lists), save/reset options, status card, statistics and issues spoilers, fixed-SBOM download
- `frontend/src/views/sbomFixerRules.ts` — single catalog of the 16 static fix rules (`BASE_RULES` with 5 entries, `COMPONENTS_RULES` with 8, `LICENSES_RULES` with 3: rule id, option key, before/after JSON examples) that drives the rule rows of the Fix SBOM page
- `frontend/src/components/RuleHelp.vue` — presentational rule help: round "(i)" button and an inline panel with a description (multi-line, rendered with `white-space: pre-line`) and "Before"/"After" snippets
- `frontend/src/views/sbomFixerRules.test.ts` — Vitest unit tests for the fix rule catalog
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
- `frontend/src/api/sbom.ts` — SBOM enrichment + ignore patterns + SBOM fix API client (`fixSbom`, `getFixOptions`, `saveFixOptions`, `analyzeSbom`, `getFieldCatalog`)
- `frontend/src/api/db.ts` — Database admin API client (list, update, delete, import, export)
- `frontend/src/api/settings.ts` — Settings API client
- `frontend/src/i18n/index.ts` — vue-i18n configuration (Composition API mode, `legacy: false`)
- `frontend/src/i18n/locales/en.json` — English UI strings (grouped by domain)
- `frontend/src/i18n/locales/ru.json` — Russian UI strings (identical key structure)
- `frontend/src/tests/i18n.ts` — `mountWithI18n` helper for test mounting with vue-i18n plugin
- `frontend/src/api/jobs.ts` — Background job API client (create, poll, download, cancel, list)
- `frontend/src/api/images.ts` — Images list conversion API client
- `frontend/src/types/api.ts` — TypeScript interfaces mirroring backend response models; the SBOM fix types mirror `sbom/fixer.py` (`SbomFixOptions` and its nested option models, including `LicensesFixOptions` and `ProvidedByPatternItem`, mirror the Pydantic models; `add_patterns` reuses `IgnorePatternItem`; `SbomFixStat`/`SbomFixIssue` mirror the dataclasses) while `SbomFixResponse` mirrors the `routes/sbom_fix.py` response payload and `SbomFixOptionsResponse` mirrors the options endpoint payload; `OptionalFieldsFixOptions`, `OptionalFieldStatus`, `OptionalFieldInfo`, `FstecField`, and `FieldCatalogResponse` mirror the optional-fields catalog/analysis payloads
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
  |                       | GET /api/v1/sbom/fix/field-catalog
  |                       |-------------------------->|
  |                       | 200 {fstec_fields,        |
  |                       |      default_keep}        |
  |                       |<--------------------------|
  | Reviews/toggles rules,|                           |
  | optionally saves them |                           |
  |---------------------->| POST /api/v1/sbom/fix/options
  |                       |-------------------------->|
  |                       | 200 {status: "saved"}      |
  |                       |<--------------------------|
  | Selects .json file,   |                           |
  | clicks "Analyze"      |                           |
  |---------------------->|                           |
  |                       | POST /api/v1/sbom/fix/analyze
  |                       | (multipart: file)         |
  |                       |-------------------------->|
  |                       | 200 {fields: [...]}       |
  |                       |<--------------------------|
  | Checks candidate      |                           |
  | fields to remove,     |                           |
  | clicks "Fix SBOM"     |                           |
  |---------------------->|                           |
  |                       | POST /api/v1/sbom/fix      |
  |                       | (multipart: file + options |
  |                       |  + remove_fields)         |
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
- On mount the page loads saved options via `GET /api/v1/sbom/fix/options`, application settings (`useSettingsStore().load()` for `jsonIndent`), and the field catalog via `GET /api/v1/sbom/fix/field-catalog` in parallel (all-settled); the page is available at `/fix-sbom` and the nav/home entry uses the `sbomFixer` i18n namespace
- If loading saved options fails (network/500), the built-in defaults are used and a non-blocking warning is shown; if loading settings fails, the page still works and downloads use `jsonIndent = 4`; if the catalog request fails, the page still works with list 1 hidden and "Reset defaults" leaves the current `optional_fields.keep` unchanged (a non-critical warning is shown)
- Defaults: every static option enabled except the three `components.remove_leaf_*` flags, `components.fill_missing_gost_properties`, and the three `licenses.*` flags; `components.lowercase_purl = true` with `components.purl_case_mode = "sbom_checker"`; `components.add_provided_by = true` with the Astra default row (`purl` / `pkg:deb/astra` / «Операционная система специального назначения "Astra Linux Special Edition"»); `specVersion = "1.7"`, `manufacturer = "Positive Technologies"`, `licenses.add_patterns = []`, `optional_fields.keep` = the 10 default list-2 paths (from the catalog's `default_keep`, not a frontend copy)
- Every static rule row has a round "(i)" help button; clicking it expands an inline panel under the row inside the group card with a description of the rule and "Before"/"After" snippets of a CycloneDX JSON fragment
- At most one help panel is open at a time; clicking the same button again closes it, and pressing Escape closes the panel while focus is inside the rule's help control (for example right after clicking the "i" button); the button sits outside the rule's `<label>`, so opening help never toggles the rule's checkbox
- Rule rows are rendered from the `sbomFixerRules.ts` catalog (16 rules: `BASE_RULES` with 5 entries, `COMPONENTS_RULES` with 8, then `LICENSES_RULES` with 3) in catalog order; the order of entries in the statistics spoiler is still defined by the backend (`RULE_IDS`), not by the catalog
- The `components[]` card renders eight rule rows in catalog order: «Удалить компоненты-листья без PURL» / "Remove leaf components without PURL", «Удалить компоненты-листья с некорректным PURL» / "Remove leaf components with invalid PURL", «Удалить компоненты-листья без version» / "Remove leaf components without version", «Привести PURL к строчному регистру» / "Lowercase PURL", then the external-references filter, the properties filter, the GOST fill, and «Добавить свойство GOST:provided_by для компонентов со следующими признаками:»; the card's master checkbox, «Выбрать всё» / «Снять всё», the "(i)" help panels, the save payload, and "Reset defaults" cover all eight flags
- The lowercase-PURL rule row renders a mode selector under it (`data-purl-case-mode`) with two radio options (`data-purl-case-mode-option="sbom_checker"` and `="purl_spec"`) bound to `options.components.purl_case_mode`; `sbom_checker` is selected by default and by "Reset defaults"; both radios are disabled while `components.lowercase_purl` is off, and the selected mode is kept in state and saved independently of the rule's enabled state; "select all"/"clear all" change only the boolean flags and never the mode
- The help panel for `components.lowercase_purl` has two labelled blocks (sbom-checker and purl-spec) separated by blank lines; `RuleHelp.vue` renders the description with `white-space: pre-line` so the line breaks survive
- Options are grouped into four sections: «Базовые правки» / "Basic fixes" (`data-group="basic"`), «Правки массива components[]» / "components[] edits" (`data-group="components"`), «Правки, касающиеся лицензий компонентов» / "Component license edits" (`data-group="licenses"`), and the optional-fields whitelist card; the license card sits between the `components[]` card and the optional-fields card; there are no separate `root`, `metadata`, or `metadata.component` cards
- Base rule labels carry the JSONPath so each item is unambiguous without an object-scoping heading: `$.specVersion`, `$.version`, `$.metadata.timestamp`, `$.metadata.component.manufacturer`. The one exception is `reorder`: it covers several objects, so its label stays short («Упорядочить поля» / "Reorder fields") and the full list of objects and key orders lives in its help panel. Labels inside the `components[]` and `licenses` cards stay short because the card heading already scopes them
- The basic-fixes card, the `components[]` card, and the license card each have a master checkbox: checked when all its child options are on, indeterminate when only some are; toggling it sets all its children (the basic master covers the five base flags and leaves text values untouched, the components master covers the eight `components.*` flags, the license master covers the three `licenses.*` flags and leaves the pattern rows untouched); "select all"/"clear all" buttons operate on their own card only
- The license card renders its three rule rows (filter non-proprietary, add proprietary, remove proprietary source references) with the same "(i)" help panels as other rules. Under `licenses.add_proprietary` an inline pattern editor shows one row per `{field, pattern}` pair with "Field", "contains", "Value", and a remove-row button, plus an "Add row" button; an empty saved list renders one empty row. All pattern inputs and the add/remove buttons are disabled while `add_proprietary` is off, and turning the rule off keeps the rows
- Pattern rows are trimmed and rows with an empty field or value are dropped before saving settings and before running a fix, so blank pairs never reach the server. The license card has no save button of its own: "Save settings" persists the flags together with the normalized `add_patterns` list through the shared options endpoint
- Under `components.add_provided_by` the `components[]` card renders a local three-column row editor (field, "contains" separator, value, certified-product name) with a remove-row button and an "Add row" button, using `data-provided-by-row`, `data-provided-by-field`, `data-provided-by-value`, `data-provided-by-name`, `data-action="add-provided-by"`, and `data-action="remove-provided-by"`. All inputs and row buttons are disabled while the rule is off, and the entered rows survive toggling. A saved empty list renders one empty row; rows are trimmed and rows with any blank field are dropped on save and on fix; "Reset defaults" restores the single Astra row
- The `specVersion` text input is enabled only while `set_spec_version` is checked; the `manufacturer` text input (next to `add_manufacturer`) is enabled only while that rule is checked, and its value is saved with the options
- The current form values are used for a run immediately; "Save settings" persists them via `POST /api/v1/sbom/fix/options` and shows "Saved" or the translated save error next to the button; "Reset defaults" restores built-in defaults (static options including the eight `components.*` flags and the three `licenses.*` flags, `spec_version`, `manufacturer`, and `optional_fields.keep`) locally without saving, collapses the pattern editor to one empty row without restoring saved patterns, and restores the Astra provided_by row
- A new file selection resets results, errors, the analysis result, and the selected removal paths, but keeps the current options
- The optional-fields card (`data-group="optional-fields"`, after the license card and before the fix toolbar) presents a cosmetic-cleanup explanation; its "Analyze" button is disabled without a file and while a request is in flight; before analysis it shows a hint to load a file and run the analysis; after analysis it renders a candidate table (path, occurrence count, checkbox) with "Select all"/"Clear all" buttons acting only on candidates, and an empty-state message when no optional fields are found
- Candidates are computed from the analysis result: only `additional` fields whose path is not in `optional_fields.keep`. Editing the keep list immediately recomputes candidates without re-uploading the file; a path removed from the candidate set (e.g. added to the keep list) is also dropped from the selection
- List 1 (read-only FSTEC reference) is rendered inside a collapsed-by-default `<details data-role="fstec-list">` as a path/status table with localized statuses and condition notes. List 2 is an editable `<textarea data-role="keep-list">` (one path per line) with an inline validation error after a failed save
- "Fix SBOM" sends `remove_fields` only from the accepted candidates (the selected paths); the fix request passes the full option set including `optional_fields.keep`
- The "Fix SBOM" button is disabled until a file is selected and while a request is in flight; a spinner is shown during processing
- The results area shows a status card ("changes applied" / "no changes required"), a statistics spoiler open by default (all enabled static rules, including zero counts, plus removal rows), and either a green "no issues remaining" card or an issues spoiler closed by default with the issue count; the issues table is rendered only while the spoiler is open and scrolls within a bounded height
- Statistics and issue labels are translated via i18n; a stat row with `field` is rendered as the localized `optional_fields.remove` label plus the path, while other rows use the localized rule name; issue details are formatted from `details` (for example the missing GOST names joined by commas); long values wrap and are shown in full, no `title` tooltip is used, and the issues table scrolls only vertically (its wrapper has `overflow-x: hidden`); unknown issue codes fall back to the bare code
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
- `frontend/src/views/SbomFixer.test.ts` — option loading and fallback warning, master/indeterminate checkboxes, select/clear all, license card (master and pattern editor add/remove/disable/gating), provided_by editor (Astra default row, load/add/remove, disabled while off, values kept on toggle, normalization and incomplete-row dropping, sent on save and fix, reset restores the Astra row), PURL case selector (default enabled with `sbom_checker`, radios disabled while the rule is off, selected mode saved and sent on fix, reset restores `sbom_checker`, help panel describes both modes), pattern normalization on save and fix, reset defaults, save/reset status, spec-version and manufacturer input gating, analysis flow (analyze, unchecked candidates, keep-list filtering), candidate select/clear all, `remove_fields` on fix, read-only FSTEC list, new-file reset, catalog-failure degradation, fix flow, statistics (including `field` rows) and issues spoilers, issue-label fallback, downloads (`jsonIndent` fallback to 4), `ApiError` and network errors.
- `frontend/src/views/sbomFixerRules.test.ts` — 16-rule catalog (`BASE_RULES` 5 + `COMPONENTS_RULES` 8 + `LICENSES_RULES` 3, unique ids), base group starts with the merged `reorder` rule, removed rule ids absent, `components.lowercase_purl` present and positioned after the three leaf-removal rules, `components.add_provided_by` present and positioned after `fill_missing_gost_properties`, valid before/after JSON examples, labels and help texts present in both locales.
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
