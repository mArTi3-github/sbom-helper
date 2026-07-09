# HTTP API Contract

## Participants

- **Provider**: sbom-helper service (FastAPI)
- **Consumer**: Any HTTP client (browser Vue SPA, curl, scripts)

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
  "repository_kind": "vcs",
  "confidence": "high",
  "evidence": ["homepage from PyPI metadata"],
  "warnings": [],
  "version_reference": "https://github.com/psf/requests/tree/v2.31.0",
  "resolver": "purl2repo",
  "resolved_at": "2026-05-31T12:00:00Z"
}
```

Note: `purl` field contains the normalized form (version, qualifiers, subpath stripped). The original PURL is only used internally for resolver processing. `repository_kind` uses canonical values: `"vcs"` for VCS repository URLs, `"source-distribution"` for source distribution/tarball URLs.

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

Serve the Vue 3 SPA (PURL resolver page).

#### Response (200)

Content-Type: `text/html`. Returns `index.html` from the built SPA (`frontend/dist/`). Vue Router handles client-side routing — all SPA routes (`/`, `/sbom-updater`, `/db-admin`, `/settings`, `/images-list-converter`) return the same `index.html`; the router mounts the corresponding view component. API routes are registered before the SPA mount and take priority.

---

### `GET /sbom-updater`

Serve the SBOM-updater web UI page (Vue SPA route).

#### Response (200)

Content-Type: `text/html`. Returns `index.html` (SPA fallback). Vue Router mounts `SbomUpdater.vue` with file upload (drag-and-drop), enrichment options, ignore patterns editor, results display, and download button.

---

### `POST /api/v1/resolve/sbom`

Accepts a CycloneDX JSON SBOM file, extracts all PURL components that lack VCS or source-distribution external references, resolves each unique normalized PURL via the Service Layer, inserts `type: vcs` external references into the SBOM, and returns the enriched SBOM together with a resolution report. Resolved PURLs and pre-existing references are stored in the database with `resolver: "import-sbom"`. Components that already have VCS external references are stored in the database via `store_preexisting_references()` without resolution.

#### Request

`multipart/form-data` with field `file` containing a CycloneDX JSON file.

- Maximum file size: 200 MB (configurable via `SBOM_MAX_FILE_SIZE`)
- File must be valid JSON with `bomFormat: "CycloneDX"` and `specVersion: "1.6"`
- JSON is parsed, the root dict is validated for required CycloneDX fields, then mutated in-place during enrichment
- Optional field `remove_unresolved_no_subcomponents` (boolean, default: `false`) — when `true`, removes components that were not resolved and have no nested subcomponents
- Optional field `validate_existing_refs` (boolean, default: `false`) — when `true`, existing VCS externalReferences in the SBOM are validated; invalid URLs trigger re-resolution
- Optional field `ignore_patterns` (JSON string, default: `null`) — when provided, a JSON array of `{"field": "...", "pattern": "..."}` objects specifying component field/pattern pairs; components whose specified field values contain the pattern string are excluded from enrichment and reported with `status: "ignored"`

#### Success Response (200)

```json
{
  "summary": {
    "total_purls": 10,
    "found": 8,
    "not_found": 1,
    "skipped": 0,
    "removed": 1
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
    },
    {
      "purl": "pkg:pypi/obscure",
      "status": "removed",
      "repository_url": null,
      "name": "obscure",
      "version": "1.0"
    }
  ],
  "enriched_sbom": { "...": "..." }
}
```

- `summary.total_purls` — number of unique PURLs that needed enrichment (excludes ignored components)
- `summary.found` — how many resolved successfully
- `summary.not_found` — how many had no repository URL found (excludes removed components)
- `summary.skipped` — how many PURLs could not be parsed (invalid format)
- `summary.removed` — how many components were removed (only when `remove_unresolved_no_subcomponents=true`)
- `summary.ignored` — how many components were excluded via `ignore_patterns`
- `results` — per-PURL report for components that needed enrichment; components already having VCS/source-distribution references are excluded; removed components appear only as `status: "removed"`, not as `status: "not_found"`; ignored components appear as `status: "ignored"`; each result includes `found_by` (either `"local_db"` or `"resolver"`) and `resolver` (resolver name) fields
- `enriched_sbom` — the full enriched SBOM JSON (version incremented by 1, timestamp preserved); removed components are absent from `components` arrays

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

CSV format: comma (`,`) delimiter, UTF-8 encoding (BOM handled automatically). First row must contain headers. Required columns: `purl`, `repository_url`. Optional: `repository_type`, `repository_kind`, `confidence`, `evidence` (JSON array), `warnings` (JSON array), `version_reference`, `resolver` (default: `"import-csv"` when absent), `resolved_at`. Values containing commas must be quoted per RFC 4180.

Response (200): `{ "imported": N, "skipped": N, "errors": [...] }`
Response (400): `{ "error": "invalid_csv", "message": "..." }` (missing columns, wrong format)

### `POST /api/v1/db/export`

Export selected PURLs as CSV. Accepts a list of PURLs to export; returns a comma-delimited CSV file.

#### Request

```json
{
  "purls": ["pkg:pypi/requests", "pkg:npm/express"]
}
```

#### Response

`Content-Type: text/csv`, `Content-Disposition: attachment; filename="purls_export.csv"`

CSV format: comma (`,`) delimiter, UTF-8 encoding. All 10 columns exported. JSONB fields (`evidence`, `warnings`) serialized as JSON strings within quoted CSV cells. Non-existing PURLs are silently skipped.

### `GET /db-admin`

Serve the database admin page (Vue SPA route).

Response (200): `Content-Type: text/html`. Returns `index.html` (SPA fallback). Vue Router mounts `DatabaseAdmin.vue` with filterable/sortable table, inline editing, CSV import, CSV export of selected rows, and bulk delete.

---

### `GET /settings`

Serve the settings page (Vue SPA route).

Response (200): `Content-Type: text/html`. Returns `index.html` (SPA fallback). Vue Router mounts `Settings.vue` with URL validation, retry config, log level, GitHub token, ecosyste.ms, and Libraries.io settings cards.

---

### `GET /images-list-converter`

Serve the Images List Converter web UI page (Vue SPA route).

Response (200): `Content-Type: text/html`. Returns `index.html` (SPA fallback). Vue Router mounts `ImagesListConverter.vue` with file upload (drag-and-drop), conversion status card, images table with completeness flags, and download button.

---

### `GET /api/v1/settings`

Return current application settings.

#### Response (200)

```json
{
  "validate_db_urls": false,
  "url_validation_timeout": 5,
  "revalidation_cooldown_hours": 24,
  "librariesio_enabled": false,
  "ecosystems_enabled": true,
  "token_set": {
    "github_token": false,
    "librariesio_api_key": false,
    "ecosystems_api_key": false
  },
  "json_indent": 4
}
```

- `validate_db_urls`: boolean — enable URL validation for cached repository URLs (default: `false`)
- `url_validation_timeout`: integer — timeout in seconds for HEAD and git ls-remote checks (1–60, default: `5`)
- `revalidation_cooldown_hours`: integer — cooldown in hours for trusted resolver entries (0–720, default: `24`; `0` disables cooldown)
- `librariesio_enabled`: boolean — whether the libraries.io resolver is active
- `ecosystems_enabled`: boolean — whether the ecosyste.ms resolver is active (default: `true`)
- `ecosystems_max_requests_per_second`: float — rate limit for ecosyste.ms API requests (0.1–100, default: `2.0`)
- `retry_max_attempts`: integer — maximum HTTP retry attempts for fallback resolvers (1–10, default: `3`)
- `retry_base_cooldown_seconds`: float — base wait between retries in seconds (0.5–120, default: `5.0`)
- `log_level`: string — application log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`; default: `"INFO"`)
- `token_set.github_token`: boolean — whether a GitHub token is configured (token value is never returned)
- `token_set.librariesio_api_key`: boolean — whether an API key is configured
- `token_set.ecosystems_api_key`: boolean — whether an ecosyste.ms API key is configured
- `json_indent`: integer — number of spaces for JSON indentation in downloaded files (`1`, `2`, or `4`; default: `4`)

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

```json
{
  "validate_db_urls": true,
  "url_validation_timeout": 10,
  "github_token": "ghp_..."
}
```

Both fields optional. Only provided fields are updated.

- `validate_db_urls`: optional bool — enable/disable URL validation for cached repository URLs.
- `url_validation_timeout`: optional int — timeout in seconds for HEAD and git ls-remote checks (1–60).
- `revalidation_cooldown_hours`: optional int — cooldown in hours for trusted resolver entries (0–720, 0 disables cooldown).
- `github_token`: optional string — GitHub Personal Access Token. Set to `null` to clear the token. Empty string is ignored. Invalid tokens are rejected with `400 invalid_token`.
- `librariesio_enabled`: optional bool — enable/disable the libraries.io resolver.
- `librariesio_api_key`: optional string|null — libraries.io API key. Set to `null` to clear the key. Empty string is ignored. Non-empty values are validated via the libraries.io API and rejected with `400 invalid_token` if invalid.
- `ecosystems_enabled`: optional bool — enable/disable the ecosyste.ms resolver.
- `ecosystems_api_key`: optional string|null — ecosyste.ms API key (for higher rate limits). Set to `null` to clear the key. Empty string is ignored.
- `ecosystems_max_requests_per_second`: optional float — rate limit for ecosyste.ms API requests (0.1–100).
- `retry_max_attempts`: optional int — maximum HTTP retry attempts for fallback resolvers (1–10).
- `retry_base_cooldown_seconds`: optional float — base wait between retries in seconds (0.5–120).
- `log_level`: optional string — application log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`).
- `json_indent`: optional int — number of spaces for JSON indentation in downloaded files (`1`, `2`, or `4`).

#### Response (200)

Returns the full updated settings object (same format as `GET /api/v1/settings`).

#### Error Response (400) — invalid token

```json
{
  "error": "invalid_token",
  "message": "GitHub token is invalid or expired"
}
```

---

### `POST /api/v1/settings/check-github-token`

Manually validate the currently stored GitHub token. No request body.

#### Response (200) — token is valid

```json
{ "status": "valid" }
```

#### Response (200) — token is invalid

```json
{ "status": "invalid" }
```

#### Error Response (400) — token not set

```json
{
  "error": "token_not_set",
  "message": "GitHub token is not set"
}
```

---

### `POST /api/v1/convert/images-list`

Convert a CycloneDX SBOM file into a machine-readable list of Docker container images in CycloneDX format.

#### Request

`multipart/form-data` with field `file` containing a CycloneDX JSON file.

- Maximum file size: 200 MB (configurable via `SBOM_MAX_FILE_SIZE`)
- File must be valid JSON with `bomFormat: "CycloneDX"`
- JSON is parsed and validated for required CycloneDX fields

#### Success Response (200)

```json
{
  "was_transformed": true,
  "images": [
    {
      "name": "manager",
      "version": "3.0.0",
      "missing_components": false,
      "missing_name": false,
      "missing_version": false,
      "missing_properties": false,
      "duplicates_removed": 0
    }
  ],
  "images_list": { "bomFormat": "CycloneDX", "...": "..." }
}
```

- `was_transformed` — boolean, whether the SBOM was modified (true = containers were promoted from nested levels, non-containers removed, or duplicate containers with the same `purl` were removed)
- `images` — array of ImageInfo objects with completeness flags: `missing_components` (no nested components), `missing_name` (name empty/absent), `missing_version` (version empty/absent), `missing_properties` (properties empty/absent), `duplicates_removed` (how many additional copies of this image with the same `purl` were removed)
- `images_list` — the resulting CycloneDX document with only `type=container` components at the top level, deduplicated by `purl`

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

## Enrichment Algorithm

1. Recursively walk all `components[]` arrays (including nested `components` inside components)
2. For each component that has a `purl` AND (has no `externalReferences` OR has no `vcs`/`source-distribution` type in `externalReferences`): mark as needing enrichment
3. If `validate_existing_refs=true`: for components with `vcs`/`source-distribution` externalReferences, validate the URL via HEAD + git ls-remote; `INVALID` results mark the component for re-resolution (clear `existing_references`, set `needs_enrichment=True`); `NETWORK_ERROR` and `RATE_LIMITED` leave the component unchanged
4. For each component needing enrichment: validate and normalize the PURL explicitly via `validate()` + `normalize()`; invalid PURLs increment the `skipped` count and are excluded from resolution; valid unversioned PURLs are correctly normalized and included
5. Normalize each PURL to `scheme:type/namespace/name`; deduplicate across the entire SBOM
6. For each unique normalized PURL: call `service.resolve_purl()` (cache → resolver flow) with `resolver="import-sbom"`
7. Store pre-existing references: for components with `needs_enrichment=False`, store their PURL and VCS repository URL in the database via `store_preexisting_references()` with `resolver="import-sbom"`
8. For each component matching a resolved PURL: append `{"type": "vcs", "url": "..."}` to its `externalReferences` array; preserve all existing references
9. Increment `version` field by 1
10. If `remove_unresolved_no_subcomponents=true`: remove components from the SBOM where `needs_enrichment=True`, `has_subcomponents=False`, and PURL was not resolved; removed components are reported with `status: "removed"` and excluded from `status: "not_found"` counts

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
| Invalid GitHub token on settings save | 400 | `invalid_token` |
| Invalid libraries.io API key on settings save | 400 | `invalid_token` |
| Images list conversion: invalid JSON | 400 | `invalid_json` |
| Images list conversion: invalid SBOM format | 400 | `invalid_sbom` |
| Images list conversion: file too large | 413 | `file_too_large` |
| Images list conversion: missing file field | 422 | (Pydantic validation) |
| GitHub token check with no token stored | 400 | `token_not_set` |
| Network unavailable (GitHub connectivity check failed) | 503 | `network_unavailable` |

## Breaking Change Checklist

- [ ] Removing or renaming a response field
- [ ] Changing the type or format of a response field
- [ ] Changing HTTP status codes for existing conditions
- [ ] Adding required request fields
- [ ] Changing the endpoint URL path
- [ ] Removing or renaming error codes in error responses
