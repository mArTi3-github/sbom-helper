# HTTP API Contract

## Participants

- **Provider**: sbom-helper service (FastAPI)
- **Consumer**: Any HTTP client (browser, curl, scripts, future frontend)

## Base URL

All API endpoints are served from the root path. No version prefix in the base URL — versioning is in the path (`/api/v1/`).

## Endpoints

### `POST /api/v1/resolve`

Resolve a single PURL to its repository URL.

#### Request

```json
{
  "purl": "pkg:pypi/requests@2.31.0"
}
```

- `purl`: required, non-empty string. The response `purl` field contains the normalized form (`scheme:type/namespace/name`), not the original input PURL.

#### Success Response (200) — resolved

```json
{
  "purl": "pkg:pypi/requests",
  "repository_url": "https://github.com/psf/requests",
  "repository_type": "github",
  "repository_kind": "source_code",
  "confidence": "high",
  "evidence": ["homepage from PyPI metadata"],
  "warnings": [],
  "version_reference": "https://github.com/psf/requests/tree/v2.31.0",
  "resolver": "purl2repo",
  "resolved_at": "2026-05-31T12:00:00Z"
}
```

Note: `purl` field contains the normalized form (version, qualifiers, subpath stripped). The original PURL is only used internally for resolver processing.

#### Success Response (200) — unresolved

```json
{
  "purl": "pkg:pypi/obscure-package",
  "repository_url": null,
  "repository_type": null,
  "repository_kind": null,
  "confidence": null,
  "evidence": [],
  "warnings": ["No repository URL found for this PURL"],
  "version_reference": null
}
```

#### Error Response (400) — invalid PURL

```json
{
  "error": "invalid_purl",
  "message": "PURL must start with 'pkg:'."
}
```

#### Error Response (502) — upstream error

```json
{
  "error": "upstream_error",
  "message": "Failed to resolve: registry API timeout"
}
```

#### Validation Error (422) — request body invalid

Standard FastAPI/Pydantic 422 response with field-level validation details.

### `GET /health`

Simple health check for monitoring and container orchestration.

#### Response (200)

```json
{
  "status": "ok"
}
```

### `GET /`

Serve the web UI HTML page (PURL resolver).

#### Response (200)

Content-Type: `text/html`. Returns the Jinja2-rendered index page with a navigation bar linking to PURL Resolver, SBOM Updater, Database Admin, and Settings pages.

---

### `GET /sbom-updater`

Serve the SBOM-updater web UI page.

#### Response (200)

Content-Type: `text/html`. Returns the Jinja2-rendered sbom.html page with a file upload form for CycloneDX JSON SBOM files. The page handles file selection, upload, result display, and enriched SBOM download via JavaScript.

---

### `POST /api/v1/resolve/sbom`

Accepts a CycloneDX JSON SBOM file, extracts all PURL components that lack VCS or source-distribution external references, resolves each unique normalized PURL via the Service Layer, inserts `type: vcs` external references into the SBOM, and returns the enriched SBOM together with a resolution report. Components that already have VCS external references are stored in the database via `store_preexisting_references()` without resolution.

#### Request

`multipart/form-data` with field `file` containing a CycloneDX JSON file.

- Maximum file size: 200 MB (configurable via `SBOM_MAX_FILE_SIZE`)
- File must be valid JSON with `bomFormat: "CycloneDX"` and `specVersion: "1.6"`
- JSON is parsed, the root dict is validated for required CycloneDX fields, then mutated in-place during enrichment

#### Success Response (200)

```json
{
  "summary": {
    "total_purls": 10,
    "found": 8,
    "not_found": 2,
    "skipped": 0
  },
  "results": [
    {
      "purl": "pkg:pypi/certifi",
      "status": "found",
      "repository_url": "https://github.com/certifi/python-certifi"
    },
    {
      "purl": "pkg:pypi/unknown",
      "status": "not_found",
      "repository_url": null
    }
  ],
  "enriched_sbom": { "...": "..." }
}
```

- `summary.total_purls` — number of unique PURLs that needed enrichment
- `summary.found` — how many resolved successfully
- `summary.not_found` — how many had no repository URL found
- `summary.skipped` — how many PURLs could not be parsed (invalid format)
- `results` — per-PURL report indust only for components that needed enrichment (components already having VCS/source-distribution references are excluded)
- `enriched_sbom` — the full enriched SBOM JSON (version incremented by 1, timestamp preserved)

#### Error Response (400) — invalid JSON

```json
{
  "error": "invalid_json",
  "message": "Invalid JSON: Expecting value: line 1 column 1"
}
```

#### Error Response (400) — invalid SBOM format

```json
{
  "error": "invalid_sbom",
  "message": "Missing required field: bomFormat"
}
```

#### Error Response (413) — file too large

```json
{
  "error": "file_too_large",
  "message": "File size exceeds maximum of 200 MB"
}
```

#### Validation Error (422) — missing file field

Standard FastAPI/Pydantic 422 response.

---

### `GET /api/v1/db/purls`

List PURLs with pagination, filtering, and sorting.

Query parameters: `page`, `page_size`, `search`, `resolver`, `confidence`, `date_from`, `date_to`, `sort_by`, `sort_order`.

Response (200):
```json
{
  "rows": [{ "purl": "...", "repository_url": "...", ... }],
  "total": 1234,
  "page": 1,
  "page_size": 50
}
```

### `PATCH /api/v1/db/purls/{purl:path}`

Edit a PURL row. Body: `{ "purl": "...", "repository_url": "..." }` (both optional).

Response (200): `{ "ok": true }`
Response (404): `{ "error": "not_found", "message": "PURL not found" }`

### `DELETE /api/v1/db/purls`

Bulk delete. Body: `{ "purls": ["...", "..."] }`.

Response (200): `{ "deleted": N }`

### `POST /api/v1/db/import`

Import CSV. Multipart: `file` (CSV) + `strategy` (`"upsert"` or `"skip_existing"`).

CSV format: semicolon (`;`) delimiter, UTF-8 encoding (BOM handled automatically). First row must contain headers. Required columns: `purl`, `repository_url`. Optional: `repository_type`, `repository_kind`, `confidence`, `evidence` (JSON array), `warnings` (JSON array), `version_reference`, `resolver`, `resolved_at`.

Response (200): `{ "imported": N, "skipped": N, "errors": [...] }`
Response (400): `{ "error": "invalid_csv", "message": "..." }` (missing columns, wrong format)

### `GET /api/v1/db/export`

Export CSV. Same filter/sort params as `GET /api/v1/db/purls` (no pagination).

CSV format: semicolon (`;`) delimiter, UTF-8 encoding. All 10 columns exported. JSONB fields (`evidence`, `warnings`) serialized as JSON strings within quoted CSV cells.

Response: `Content-Type: text/csv`, `Content-Disposition: attachment; filename="resolved_purls_export.csv"`

### `GET /db-admin`

Serve the database admin page HTML.

Response (200): `Content-Type: text/html`. Jinja2-rendered `db-admin.html`.

---

### `GET /settings`

Serve the settings page HTML.

Response (200): `Content-Type: text/html`. Jinja2-rendered `settings.html`.

---

### `GET /api/v1/settings`

Return current application settings.

#### Response (200)

```json
{
  "validate_db_urls": false,
  "url_validation_timeout": 5
}
```

- `validate_db_urls`: boolean — enable URL validation for cached repository URLs (default: `false`)
- `url_validation_timeout`: integer — timeout in seconds for HEAD and git ls-remote checks (1–60, default: `5`)

---

### `PATCH /api/v1/settings`

Partially update application settings.

#### Request

```json
{
  "validate_db_urls": true,
  "url_validation_timeout": 10
}
```

Both fields optional. Only provided fields are updated.

#### Response (200)

Returns the full updated settings object (same format as `GET /api/v1/settings`).

---

## Enrichment Algorithm

1. Recursively walk all `components[]` arrays (including nested `components` inside components)
2. For each component that has a `purl` AND (has no `externalReferences` OR has no `vcs`/`source-distribution` type in `externalReferences`): mark as needing enrichment
3. Normalize each PURL to `scheme:type/namespace/name`; deduplicate across the entire SBOM
4. For each unique normalized PURL: call `service.resolve_purl()` (cache → resolver flow)
5. Store pre-existing references: for components with `needs_enrichment=False`, store their PURL and VCS repository URL in the database via `store_preexisting_references()`
6. For each component matching a resolved PURL: append `{"type": "vcs", "url": "..."}` to its `externalReferences` array; preserve all existing references
7. Increment `version` field by 1

## Error Handling Rules

| Condition | HTTP Status | Error Code |
|---|---|---|
| Invalid PURL format (application-level validation) | 400 | `invalid_purl` |
| Unsupported ecosystem (resolver returns no result) | 200 | — (`repository_url: null`, `warnings` populated) |
| Valid PURL, no repository found | 200 | — (`repository_url: null`) |
| purl2repo network/timeout error | 502 | `upstream_error` |
| Empty purl string | 422 | (Pydantic validation) |
| PURL not found on PATCH | 404 | `not_found` |
| Invalid CSV (missing columns, wrong format) | 400 | `invalid_csv` |
| CSV too large | 413 | `file_too_large` |

## Breaking Change Checklist

- [ ] Removing or renaming a response field
- [ ] Changing the type or format of a response field
- [ ] Changing HTTP status codes for existing conditions
- [ ] Adding required request fields
- [ ] Changing the endpoint URL path
- [ ] Removing or renaming error codes in error responses
