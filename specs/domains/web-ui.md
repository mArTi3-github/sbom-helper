# Web UI

## Description

Single-page browser interface for resolving PURLs without writing HTTP requests. Provides a form for PURL input and displays results in a structured card with expandable details.

## Key Files

- `src/purl_resolver/templates/index.html` — Single HTML file containing structure, styles, and logic
- `src/purl_resolver/router.py` — Serves the template at `GET /`

## Flow

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

## Invariants

- The page never reloads during resolution (single-page behaviour via `fetch()`)
- Submit button is disabled while a request is in flight
- All states (loading, success, unresolved, error, network failure) have distinct visual representations
- `version_reference` in details is rendered as a clickable link
- Evidence items are listed as an unordered list in the details section
- Warnings are shown in yellow, errors in red
