# HTTP API Contract

## Participants

- **Provider**: sbom-helper service (FastAPI)
- **Consumer**: Any HTTP client (browser Vue SPA, curl, scripts)

## Base URL

All API endpoints are served from the root path. No version prefix in the base URL — versioning is in the path (`/api/v1/`).

## Endpoints

### `POST /api/v1/resolve/batch`

Resolve one or more PURLs to their repository URLs. Returns one result row per input PURL, in input order.

#### Request

```json
{
  "purls": ["pkg:pypi/requests@2.31.0", "pkg:pypi/flask@3.0.0"]
}
```

- `purls`: required, non-empty list of strings (1 to `batch_max_items` items, configurable in settings, default 100).
- Each item's `purl` field in the response contains the original input string (with version), not the normalized form.

#### Success Response (200)

```json
{
  "results": [
    {
      "purl": "pkg:pypi/requests@2.31.0",
      "repository_url": "https://github.com/psf/requests",
      "warnings": [],
      "resolver": "purl2repo",
      "found_by": "resolver",
      "resolved_at": "2026-05-31T12:00:00Z",
      "error": null
    },
    {
      "purl": "pkg:pypi/obscure-package@0.1.0",
      "repository_url": null,
      "warnings": ["No resolver found a repository URL"],
      "resolver": "",
      "found_by": "",
      "resolved_at": "",
      "error": null
    }
  ]
}
```

Each row is one of:
- **Resolved** — `repository_url` set, `error` is `null`.
- **Unresolved** — `repository_url` is `null`, `error` is `null`, warnings explain why.
- **Error** — `error` contains an error code (`invalid_purl`, `upstream_error`), `repository_url` is `null`. A single invalid PURL does not fail the whole request.

#### Error Response (400) — too many PURLs

```json
{
  "error": "batch_too_large",
  "detail": "Maximum 100 PURLs per request"
}
```

#### Error Response (503) — network unavailable

```json
{
  "error": "network_unavailable"
}
```

#### Validation Error (422) — request body invalid

Standard FastAPI/Pydantic 422 response with field-level validation details (e.g. empty `purls` list).

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



### `GET /api/v1/db/purls`

List PURLs with pagination, filtering, and sorting.

Query parameters: `page`, `page_size`, `search`, `resolver`, `date_from`, `date_to`, `sort_by`, `sort_order`.

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

Edit a PURL row. Body: `{ "purl": "...", "repository_url": "..." }` (both optional; when `repository_url` is omitted, the existing value is preserved).

Response (200): `{ "ok": true }`
Response (404): `{ "error": "purl_not_found" }`

### `DELETE /api/v1/db/purls`

Bulk delete. Body: `{ "purls": ["...", "..."] }`.

Response (200): `{ "deleted": N }`

### `GET /api/v1/db/resolvers`

List distinct resolver names from the `resolved_purls` table. Used to dynamically populate the resolver filter dropdown in the DB Admin page.

#### Response (200)

```
["ecosyste.ms", "import-csv", "libraries.io", "purl2repo"]
```

Flat JSON array of strings, sorted alphabetically.

---

### `POST /api/v1/db/import`

Import CSV. Multipart: `file` (CSV) + `strategy` (`"upsert"` or `"skip_existing"`).

CSV format: comma (`,`) delimiter, UTF-8 encoding (BOM handled automatically). First row must contain headers. Required columns: `purl`, `repository_url`. Optional: `resolver` (default: `"import-csv"` when absent), `resolved_at`. Values containing commas must be quoted per RFC 4180.

Response (200): `{ "imported": N, "skipped": N, "errors": [...] }`
Response (400): `{ "error": "invalid_csv" }` (missing columns, wrong format)

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

CSV format: comma (`,`) delimiter, UTF-8 encoding. Four columns exported: `purl`, `repository_url`, `resolver`, `resolved_at`. Non-existing PURLs are silently skipped.

### `GET /db-admin`

Serve the database admin page (Vue SPA route).

Response (200): `Content-Type: text/html`. Returns `index.html` (SPA fallback). Vue Router mounts `DatabaseAdmin.vue` with filterable/sortable table, inline editing, CSV import, CSV export of selected rows, and bulk delete.

---

### `GET /settings`

Serve the settings page (Vue SPA route).

Response (200): `Content-Type: text/html`. Returns `index.html` (SPA fallback). Vue Router mounts `Settings.vue` with URL validation, retry config, log level, GitHub token, APK resolver, ecosyste.ms, and Libraries.io settings cards.

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
  "apk_resolver_enabled": true,
  "token_set": {
    "librariesio_api_key": false,
    "ecosystems_api_key": false
  },
  "language": "en",
  "json_indent": 4
}
```

- `validate_db_urls`: boolean — enable URL validation for cached repository URLs (default: `false`)
- `validate_sbom_refs`: boolean — enable URL validation for existing VCS references in SBOM files (default: `false`)
- `sbom_multiple_vcs_behavior`: string — behavior when SBOM component has multiple VCS references (`"keep-first"` or `"keep-all"`; default: `"keep-first"`)
- `url_validation_timeout`: integer — timeout in seconds for HEAD and git ls-remote checks (1–60, default: `5`)
- `revalidation_cooldown_hours`: integer — cooldown in hours for trusted resolver entries (0–720, default: `24`; `0` disables cooldown)
- `librariesio_enabled`: boolean — whether the libraries.io resolver is active
- `ecosystems_enabled`: boolean — whether the ecosyste.ms resolver is active (default: `true`)
- `apk_resolver_enabled`: boolean — whether the APK resolver (Alpine Linux) is active as the last fallback (default: `true`)
- `ecosystems_max_requests_per_second`: float — rate limit for ecosyste.ms API requests (0.1–100, default: `2.0`)
- `retry_max_attempts`: integer — maximum HTTP retry attempts for fallback resolvers (1–10, default: `3`)
- `retry_base_cooldown_seconds`: float — base wait between retries in seconds (0.5–120, default: `5.0`)
- `log_level`: string — application log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`; default: `"INFO"`)
- `batch_semaphore_limit`: integer — maximum number of concurrent resolution requests in batch mode (1–100, default: `10`)
- `connectivity_url`: string — URL used for connectivity probes (default: `"https://github.com"`)
- `connectivity_timeout`: integer — timeout in seconds for connectivity probes (1–30, default: `2`)
- `job_ttl_hours`: integer — time-to-live in hours for async job records (1–720, default: `24`)
- `token_set.librariesio_api_key`: boolean — whether an API key is configured
- `token_set.ecosystems_api_key`: boolean — whether an ecosyste.ms API key is configured
- `language`: string — UI language (`"en"` or `"ru"`; default: `"en"`)
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

All fields optional. Only provided fields are updated.

- `validate_db_urls`: optional bool — enable/disable URL validation for cached repository URLs.
- `validate_sbom_refs`: optional bool — enable/disable URL validation for existing VCS references in SBOM files.
- `sbom_multiple_vcs_behavior`: optional string — behavior when SBOM component has multiple VCS references (`"keep-first"` or `"keep-all"`).
- `url_validation_timeout`: optional int — timeout in seconds for HEAD and git ls-remote checks (1–60).
- `revalidation_cooldown_hours`: optional int — cooldown in hours for trusted resolver entries (0–720, 0 disables cooldown).
- `librariesio_enabled`: optional bool — enable/disable the libraries.io resolver.
- `librariesio_api_key`: optional string|null — libraries.io API key. Set to `null` to clear the key. Empty string is ignored. Non-empty values are validated via the libraries.io API and rejected with `400 invalid_token` if invalid.
- `ecosystems_enabled`: optional bool — enable/disable the ecosyste.ms resolver.
- `apk_resolver_enabled`: optional bool — enable/disable the APK resolver (Alpine Linux) as the last fallback.
- `ecosystems_api_key`: optional string|null — ecosyste.ms API key (for higher rate limits). Set to `null` to clear the key. Empty string is ignored.
- `ecosystems_max_requests_per_second`: optional float — rate limit for ecosyste.ms API requests (0.1–100).
- `retry_max_attempts`: optional int — maximum HTTP retry attempts for fallback resolvers (1–10).
- `retry_base_cooldown_seconds`: optional float — base wait between retries in seconds (0.5–120).
- `log_level`: optional string — application log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`).
- `batch_semaphore_limit`: optional int — maximum concurrent resolution requests in batch mode (1–100).
- `job_ttl_hours`: optional int — time-to-live for async job records in hours (1–720).
- `connectivity_url`: optional string — URL for connectivity probes.
- `connectivity_timeout`: optional int — timeout in seconds for connectivity probes (1–30).
- `language`: optional string — UI language (`"en"` or `"ru"`).
- `json_indent`: optional int — number of spaces for JSON indentation in downloaded files (`1`, `2`, or `4`).

#### Response (200)

Returns the full updated settings object (same format as `GET /api/v1/settings`).

#### Error Response (400) — invalid token

```json
{
  "error": "invalid_token"
}
```

---

### `POST /api/v1/settings/clear-validation-cache`

Clear the in-memory URL validation cache, forcing re-validation on the next URL check.

#### Response (200)

```json
{ "status": "ok" }
```

---

### `POST /api/v1/jobs/sbom-enrich`

Asynchronously enrich a CycloneDX SBOM file via a background job. Accepts the same parameters as `POST /api/v1/resolve/sbom` but returns immediately with a job ID instead of blocking.

#### Request

`multipart/form-data` with field `file` containing a CycloneDX JSON file.

- Maximum file size: 200 MB (configurable via `SBOM_MAX_FILE_SIZE`)
- File must be valid JSON with `bomFormat: "CycloneDX"`
- Optional field `remove_unresolved_no_subcomponents` (boolean, default: `false`)
- Optional field `ignore_patterns` (JSON string, default: `null`) — JSON array of `{"field": "...", "pattern": "..."}` objects

#### Success Response (202)

```json
{
  "job_id": "a1b2c3d4-...",
  "status": "queued"
}
```

#### Error Response (400) — invalid JSON

```json
{ "error": "invalid_json" }
```

#### Error Response (413) — file too large

```json
{
  "error": "file_too_large",
  "max_size_mb": 200
}
```

#### Error Response (503) — job queue unavailable

```json
{
  "error": "job_queue_unavailable"
}
```

---

### `GET /api/v1/jobs`

List background enrichment jobs.

#### Query Parameters

- `limit`: integer, max results (default: `20`)
- `offset`: integer, pagination offset (default: `0`)

#### Response (200)

```json
{
  "jobs": [
    {
      "job_id": "a1b2c3d4-...",
      "type": "sbom-enrich",
      "status": "queued",
      "progress_current": 0,
      "progress_total": 0,
      "input_filename": "sbom.json",
      "summary": null,
      "error_message": null,
      "created_at": "2026-07-11T12:00:00Z",
      "started_at": null,
      "finished_at": null
    }
  ]
}
```

---

### `GET /api/v1/jobs/{job_id}`

Get the current status and results of a background enrichment job.

#### Response (200)

```json
{
  "job_id": "a1b2c3d4-...",
  "type": "sbom-enrich",
  "status": "completed",
  "progress_current": 10,
  "progress_total": 10,
  "input_filename": "sbom.json",
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
    }
  ],
  "error_message": null,
  "created_at": "2026-07-11T12:00:00Z",
  "started_at": "2026-07-11T12:00:01Z",
  "finished_at": "2026-07-11T12:00:10Z"
}
```

- `status`: one of `queued`, `running`, `completed`, `failed`, `cancelled`
- `summary` and `results` are `null` until the job completes

#### Error Response (404)

```json
{ "error": "job_not_found" }
```

---

### `GET /api/v1/jobs/{job_id}/result`

Download the enriched SBOM file for a completed job.

#### Response (200)

Content-Type: `application/json`. Returns the enriched SBOM file.

#### Error Response (400) — result not ready

```json
{
  "error": "result_not_ready",
  "status": "running"
}
```

#### Error Response (404)

```json
{ "error": "job_not_found" }
```

#### Error Response (404) — result file missing

```json
{ "error": "result_file_not_found" }
```

---

### `POST /api/v1/jobs/{job_id}/cancel`

Request cancellation of a running job.

#### Response (200)

```json
{ "job_id": "a1b2c3d4-...", "status": "cancelled" }
```

#### Error Response (404)

```json
{ "error": "job_not_found" }
```

#### Error Response (409) — job already in terminal state

```json
{
  "error": "job_already_terminal",
  "status": "completed"
}
```

---

### `DELETE /api/v1/jobs/{job_id}`

Delete a job record and its associated result file.

#### Response (200)

```json
{ "job_id": "a1b2c3d4-...", "deleted": true }
```

#### Error Response (404)

```json
{ "error": "job_not_found" }
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
  "error": "invalid_json"
}
```

#### Error Response (400) — invalid SBOM format

```json
{
  "error": "invalid_sbom",
  "detail": "Missing required field: bomFormat"
}
```

#### Error Response (413) — file too large

```json
{
  "error": "file_too_large",
  "max_size_mb": 200
}
```

#### Validation Error (422) — missing file field

Standard FastAPI/Pydantic 422 response.

---

## Enrichment Algorithm

1. Recursively walk all `components[]` arrays (including nested `components` inside components)
2. For each component that has a `purl` AND (has no `externalReferences` OR has no `vcs`/`source-distribution` type in `externalReferences`): mark as needing enrichment
3. If `validate_existing_refs=true`: for components with `vcs`/`source-distribution` externalReferences, validate the URL via HEAD + git ls-remote; `INVALID` and `NETWORK_ERROR` results remove the ref and may trigger re-resolution (if all refs invalid, `needs_enrichment=True`); `RATE_LIMITED` leaves the component unchanged
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
| PURL not found on PATCH | 404 | `purl_not_found` |
| Invalid CSV (missing columns, wrong format) | 400 | `invalid_csv` |
| CSV too large | 413 | `file_too_large` |
| Invalid libraries.io API key on settings save | 400 | `invalid_token` |
| Images list conversion: invalid JSON | 400 | `invalid_json` |
| Images list conversion: invalid SBOM format | 400 | `invalid_sbom` |
| Images list conversion: file too large | 413 | `file_too_large` |
| Images list conversion: missing file field | 422 | (Pydantic validation) |
| Network unavailable (GitHub connectivity check failed) | 503 | `network_unavailable` |
| Job queue unavailable (no PostgreSQL) | 503 | `job_queue_unavailable` |
| Job not found | 404 | `job_not_found` |
| Job result not ready | 400 | `result_not_ready` |
| Job result file missing | 404 | `result_file_not_found` |
| Job already in terminal state (cancel) | 409 | `job_already_terminal` |

## Breaking Change Checklist

- [x] Removing `message` field from all error responses (replaced by structured fields: `detail` for technical context, `max_size_mb` for file size)
- [x] Renaming `not_found` error code to `purl_not_found` on PATCH 404
- [x] Changing the type or format of a response field
- [ ] Changing HTTP status codes for existing conditions
- [ ] Adding required request fields
- [ ] Changing the endpoint URL path
- [ ] Removing or renaming error codes in error responses
