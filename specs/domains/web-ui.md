# Web UI

## Description

Two browser interfaces: a single-page PURL resolver and an SBOM-updater page for enriching CycloneDX SBOM files with repository URLs.

## Key Files

- `src/purl_resolver/templates/index.html` — PURL resolver page: structure, styles, and logic
- `src/purl_resolver/templates/sbom.html` — SBOM-updater page: file upload form, results table, download button
- `src/purl_resolver/router.py` — Serves both templates at `GET /` and `GET /sbom-updater`

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
  | clicks "Обработать"   |                           |
  |---------------------->|                           |
  |                       | POST /api/v1/resolve/sbom |
  |                       | (multipart/form-data)     |
  |                       |-------------------------->|
  |                       | 200 {summary, enriched}   |
  |                       |<--------------------------|
  | Sees results table    |                           |
  | with summary cards    |                           |
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
- Loading spinner is shown during server-side processing
- Results table displays: PURL (normalized), status (Found/Not found), repository URL (clickable)
- Summary cards show: total PURLs, found, not found, skipped
- "Скачать обогащённый SBOM" button triggers JSON file download
- All states (empty, loading, success, partial, error, network failure) have distinct visual representations
- Main page (`GET /`) includes a navigation link to the SBOM-updater page
