# Web UI

## Description

Four browser interfaces: a single-page PURL resolver, an SBOM-updater page for enriching CycloneDX SBOM files, a database administration page for managing the `resolved_purls` table, and a settings page for application configuration.

## Key Files

- `src/purl_resolver/templates/index.html` — PURL resolver page: structure, styles, and logic
- `src/purl_resolver/templates/sbom.html` — SBOM-updater page: file upload form, results table, download button
- `src/purl_resolver/templates/db-admin.html` — database administration page: filterable table with pagination, inline editing, CSV import/export, bulk delete
- `src/purl_resolver/templates/settings.html` — settings page: URL validation toggle and timeout, GitHub token management (set/clear), ecosyste.ms resolver card (enable toggle, API key input), Libraries.io resolver card (enable toggle, API key input, status badge, clear button)
- `src/purl_resolver/router.py` — Serves templates at `GET /`, `GET /sbom-updater`, `GET /db-admin`, and `GET /settings`

## Flows

### Single PURL Resolution

```
User                   Browser                    API Layer
  |                       |                           |
  | Navigate to /         |                           |
  |---------------------->|                           |
  |                       | 200 index.html            |
  |                       |<--------------------------|
  |                       |                           |
  | Enters PURL, clicks   |                           |
  | "Resolve"             |                           |
  |---------------------->|                           |
  |                       | POST /api/v1/resolve      |
  |                       |-------------------------->|
  |                       | 200 {result}              |
  |                       |<--------------------------|
  | Sees result card      |                           |
  |<----------------------|                           |
```

### SBOM Enrichment

```
User                   Browser                    API Layer
  |                       |                           |
  | Navigate to /sbom-updater                        |
  |---------------------->|                           |
  |                       | 200 sbom.html             |
  |                       |<--------------------------|
  |                       |                           |
  | Selects .json file,   |                           |
  | toggles remove option,|                           |
  | clicks "Обработать"   |                           |
  |---------------------->|                           |
  |                       | POST /api/v1/resolve/sbom |
  |                       | (multipart/form-data +    |
  |                       |  optional boolean)        |
  |                       |-------------------------->|
  |                       | 200 {summary, enriched}   |
  |                       |<--------------------------|
  | Sees results table    |                           |
  | with summary cards    |                           |
  | (including removed)   |                           |
  | and download button   |                           |
  |<----------------------|                           |
```

## Invariants

### PURL Resolver Page

- The page never reloads during resolution (single-page behaviour via `fetch()`)
- Submit button is disabled while a request is in flight
- All states (loading, success, unresolved, error, network failure) have distinct visual representations
- `version_reference` in details is rendered as a clickable link
- Evidence items are listed as an unordered list in the details section
- Warnings within the resolved result card are shown in red; the unresolved fallback message is shown in yellow; errors in red

### SBOM-updater Page

- The page never reloads during enrichment (single-page behaviour via `fetch()`)
- Upload area supports drag-and-drop and file picker
- Process button is disabled until a file is selected
- Checkbox "Удалять ненайденные компоненты без подкомпонентов" controls `remove_unresolved_no_subcomponents` form parameter
- Checkbox "Проверять существующие VCS-ссылки в SBOM" controls `validate_existing_refs` form parameter; when checked, existing VCS externalReferences in the SBOM are validated via HEAD + git ls-remote — invalid URLs trigger re-resolution
- Loading spinner is shown during server-side processing
- Results table displays: PURL (normalized), status (Found/Not found/Removed), repository URL (clickable)
- Summary cards show: total PURLs, found, not found, skipped, removed
- "Скачать обогащённый SBOM" button triggers JSON file download
- All states (empty, loading, success, partial, error, network failure) have distinct visual representations
- Main page (`GET /`) includes a navigation link to the SBOM-updater page

### DB-Admin Page

- The page never reloads during data operations (single-page behaviour via `fetch()`)
- Column visibility is user-configurable via checkboxes (default: PURL, repository_url, resolver)
- All states (loading, empty, error, success) have distinct visual representations
- Edits update via PATCH and re-fetch the current page
- Export uses semicolon (`;`) delimiter and respects current filter settings
- Import expects semicolon (`;`) delimiter, UTF-8 encoding (BOM handled automatically); first row must contain headers; required columns: `purl`, `repository_url`
- Import modal includes a collapsible CSV format reference section
- Import modal supports drag-and-drop for CSV files
- All three pages use a consistent navigation bar

### Settings Page

- Settings page is accessible at `/settings` with a nav-bar link on all pages
- URL Validation card: toggle switch controls `validate_db_urls`, number input controls `url_validation_timeout` (1–60 seconds), number input controls `revalidation_cooldown_hours` (0–720, default 24; 0 disables cooldown)
- GitHub API Token card: password input for GitHub PAT, status badge (set/not set), clear button, link to token generation
- ecosyste.ms Resolver card: enable toggle, optional API key input (for higher rate limits), status badge (set/not set), clear button
- Libraries.io Resolver card: enable toggle, API key input, status badge (set/not set), clear button, link to libraries.io login
- Settings are loaded from `GET /api/v1/settings` on page load
- Settings are saved via `PATCH /api/v1/settings` on button click
- Success/error feedback is shown after save attempt
- Nav-bar is consistent with all other pages
