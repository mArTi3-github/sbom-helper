# DB Admin — Design Spec

## Description

Add a database administration page to the sbom-helper web UI. The page allows viewing, editing, filtering, importing, and exporting the `resolved_purls` table — the PURL-to-repository-URL mapping cache.

## Key Files

- `src/purl_resolver/templates/db-admin.html` — new admin page (Jinja2 + inline JS)
- `src/purl_resolver/router.py` — new API endpoints for DB admin operations
- `src/purl_resolver/storage/interface.py` — extended Storage ABC with new methods
- `src/purl_resolver/storage/postgres.py` — PostgresCache implementation of new methods
- `src/purl_resolver/storage/inmemory.py` — InMemoryCache implementation of new methods
- `src/purl_resolver/schemas.py` — new Pydantic models for admin API

## Architecture

### Approach: Extend Storage Layer + new admin module

The design follows the existing architecture where the `Storage` interface is the single abstraction over the database. New query methods are added to the interface, implemented by both `PostgresCache` and `InMemoryCache`, and exposed through new API endpoints in `router.py`.

```
Browser
  |
  | HTTP (fetch)
  v
API Layer (router.py)
  |
  | Python call
  v
Storage Layer (interface.py → postgres.py / inmemory.py)
  |
  | asyncpg
  v
PostgreSQL (resolved_purls table)
```

No new layers or modules are introduced. The admin functionality lives entirely in the existing layer structure.

## Storage Layer Changes

### New Methods on `Storage` ABC

```python
@dataclass
class PurlFilters:
    search: str | None = None          # ILIKE match on purl
    resolver: str | None = None        # exact match on resolver
    confidence: str | None = None      # exact match on confidence
    date_from: date | None = None      # resolved_at >= date_from
    date_to: date | None = None        # resolved_at <= date_to

@dataclass
class PurlRow:
    purl: str
    repository_url: str
    repository_type: str | None
    repository_kind: str | None
    confidence: str | None
    evidence: list[str]
    warnings: list[str]
    version_reference: str | None
    resolver: str
    resolved_at: str  # ISO-8601

class Storage(ABC):
    # Existing
    async def lookup(self, purl: str) -> ResolveResponse | None: ...
    async def store(self, result: ResolveResponse) -> None: ...

    # New — admin operations
    async def list_purls(self, offset: int, limit: int, filters: PurlFilters, sort_by: str = "resolved_at", sort_order: str = "desc") -> list[PurlRow]: ...
    async def count_purls(self, filters: PurlFilters) -> int: ...
    async def update_purl(self, old_purl: str, purl: str, repository_url: str) -> bool: ...
    async def delete_purls(self, purls: list[str]) -> int: ...
    async def upsert_many(self, rows: list[dict]) -> tuple[int, int]: ...
```

### `update_purl` Semantics

When the PURL (primary key) changes, the operation is a transaction: DELETE old row + INSERT new row. When only `repository_url` changes, it is a simple UPDATE. Returns `True` if the row was found and updated, `False` if not found.

### `upsert_many` Semantics

Returns `(upserted_count, error_count)` where `upserted_count` is the number of rows successfully inserted/updated, and `error_count` is the number of rows that failed validation. Uses `ON CONFLICT (purl) DO UPDATE` — overwrites existing rows with imported data.

### `PostgresCache` Implementation

- `list_purls`: Dynamic SQL query with WHERE clauses built from `PurlFilters`. Uses `$N` parameter placeholders. ORDER BY `resolved_at DESC`. OFFSET/LIMIT for pagination.
- `count_purls`: Same WHERE clauses as `list_purls`, but `SELECT COUNT(*)`.
- `update_purl`: If PURL unchanged — `UPDATE ... SET repository_url = $1 WHERE purl = $2`. If PURL changed — `DELETE ... WHERE purl = $1; INSERT ... VALUES (...)` in a transaction.
- `delete_purls`: `DELETE FROM resolved_purls WHERE purl = ANY($1::text[])`. Returns number of deleted rows.
- `upsert_many`: `INSERT ... ON CONFLICT (purl) DO UPDATE SET ...` for each row in a transaction.

### `InMemoryCache` Implementation

All methods operate on the in-memory `_store` dict. Filtering is done in Python (list comprehension with predicate matching). This is only used in tests, so performance is not a concern.

## API Layer Changes

### New Endpoints

#### `GET /api/v1/db/purls`

List PURLs with pagination and filtering.

Query parameters:
- `page` (int, default 1, min 1)
- `page_size` (int, default 50, min 1, max 500)
- `search` (str, optional) — text search on PURL (ILIKE pattern)
- `resolver` (str, optional) — exact match filter
- `confidence` (str, optional) — exact match filter
- `date_from` (ISO date, optional) — `resolved_at >= date_from`
- `date_to` (ISO date, optional) — `resolved_at <= date_to`
- `sort_by` (str, optional, default `"resolved_at"`) — column name to sort by (one of: `purl`, `repository_url`, `resolver`, `confidence`, `resolved_at`)
- `sort_order` (str, optional, default `"desc"`) — `"asc"` or `"desc"`

Response (200):
```json
{
  "rows": [
    {
      "purl": "pkg:pypi/requests",
      "repository_url": "https://github.com/psf/requests",
      "repository_type": "github",
      "repository_kind": "source_code",
      "confidence": "high",
      "evidence": ["homepage from PyPI metadata"],
      "warnings": [],
      "version_reference": null,
      "resolver": "purl2repo",
      "resolved_at": "2026-05-30T12:00:00Z"
    }
  ],
  "total": 1234,
  "page": 1,
  "page_size": 50
}
```

#### `PATCH /api/v1/db/purls/{purl:path}`

Edit a PURL row. The `purl` path parameter is URL-encoded (FastAPI `:path` converter handles slashes).

Request body:
```json
{
  "purl": "pkg:pypi/requests",
  "repository_url": "https://github.com/psf/requests"
}
```

Both fields are optional — send only what changed. If `purl` is omitted, only `repository_url` is updated. If `purl` is provided and differs from the path parameter, the row is re-keyed (DELETE old + INSERT new).

Response (200): `{ "ok": true }`
Response (404): `{ "error": "not_found", "message": "PURL not found" }`

#### `DELETE /api/v1/db/purls`

Bulk delete.

Request body:
```json
{ "purls": ["pkg:pypi/requests", "pkg:npm/express"] }
```

Response (200): `{ "deleted": 2 }`

#### `POST /api/v1/db/import`

Import CSV file.

`multipart/form-data` with fields:
- `file` — CSV file
- `strategy` — `"upsert"` or `"skip_existing"`

CSV must have headers. Required columns: `purl`, `repository_url`. Optional: all other `resolved_purls` columns.

Response (200):
```json
{
  "imported": 100,
  "skipped": 5,
  "errors": [
    { "row": 3, "error": "missing purl" },
    { "row": 7, "error": "invalid purl format: must start with 'pkg:'" }
  ]
}
```

#### `GET /api/v1/db/export`

Export CSV. Accepts the same filter and sort query parameters as `GET /api/v1/db/purls` (no pagination — exports all matching rows).

Response: `Content-Type: text/csv`, `Content-Disposition: attachment; filename="resolved_purls_export.csv"`

All 10 columns are exported. JSONB fields (evidence, warnings) are serialized as JSON strings within CSV cells.

#### `GET /db-admin`

Serve the admin page HTML.

Response (200): `Content-Type: text/html`. Jinja2-rendered `db-admin.html`.

## Frontend Design

### Page Structure (`db-admin.html`)

The page follows the same patterns as existing `index.html` and `sbom.html`: Jinja2 template, inline `<style>` block, inline `<script>` block at the bottom.

#### Navigation Bar

Links to all three pages: `/` (PURL Resolver), `/sbom-updater` (SBOM Updater), `/db-admin` (Database). Consistent across all pages.

#### Filter Panel

Form with:
- Text input: "Search by PURL" (applied as ILIKE pattern)
- Dropdown: Resolver (populated from distinct values in DB, or hardcoded: `purl2repo`, `llm`, etc.)
- Dropdown: Confidence (`high`, `medium`, `low`, `any`)
- Date input: From (resolved_at >=)
- Date input: To (resolved_at <=)
- Buttons: "Apply", "Reset"

On Apply: fetch `GET /api/v1/db/purls` with filter params, re-render table.

#### Column Configuration

Above the table, a row of checkboxes to toggle visible columns. Default visible: PURL, repository_url, resolver. All 10 columns available.

#### Data Table

- Checkbox column for row selection (bulk operations)
- Sortable headers (server-side sorting via `sort_by` and `sort_order` query parameters passed to `GET /api/v1/db/purls`)
- Each row displays selected columns
- "Edit" button per row enters row edit mode
- "Delete" button per row with confirmation dialog

#### Row Edit Mode

When "Edit" is clicked on a row:
- PURL and repository_url cells become `<input>` elements pre-filled with current values
- "Edit" button changes to "Save" + "Cancel"
- Other cells remain read-only
- On "Save": `PATCH /api/v1/db/purls/{old_purl}` with new values, re-fetch current page
- On "Cancel": revert to display mode

#### Pagination

- Page numbers: `< 1 2 3 ... N >`
- Page size dropdown: 25, 50, 100, 200
- Total row count displayed

#### Action Buttons

- **Export CSV**: `GET /api/v1/db/export` with current filters → triggers file download
- **Import CSV**: opens modal dialog
- **Delete Selected**: deletes all checked rows with confirmation → `DELETE /api/v1/db/purls`

#### Import Modal

- Drag-and-drop zone + file picker
- Radio buttons: "Upsert (overwrite existing)" / "Skip existing"
- "Upload" button → `POST /api/v1/db/import`
- Result display: imported count, skipped count, error list

### JavaScript Patterns

Consistent with existing pages:
- `fetch()` for all API calls
- `innerHTML` + `escapeHtml()` for rendering
- Module-scoped state variables (`let currentPage = 1; let currentFilters = {}; let selectedRows = new Set();`)
- Loading spinner during fetches
- Error messages displayed inline

### CSS

Same design language as existing pages:
- System font stack
- `#f5f5f5` background
- `#2563eb` blue accent
- Rounded cards with subtle shadows
- `max-width: 1200px` (wider than existing pages to accommodate the table)

## CSV Format

### Export Columns

```
purl,repository_url,repository_type,repository_kind,confidence,evidence,warnings,version_reference,resolver,resolved_at
```

- JSONB fields (evidence, warnings): JSON string in CSV cell, quoted
- `resolved_at`: ISO-8601 format
- Encoding: UTF-8

### Import Requirements

- Required columns: `purl`, `repository_url`
- Optional columns: all others (default to NULL or `purl2repo` for resolver)
- Encoding: UTF-8
- First row must be headers

### Import Validation

1. Skip rows with empty `purl` or empty `repository_url` (log as error with row number)
2. Validate PURL format (must start with `pkg:`)
3. Duplicate PURLs within the CSV: last occurrence wins
4. Strategy `"upsert"`: INSERT ... ON CONFLICT DO UPDATE
5. Strategy `"skip_existing"`: check existence before insert, skip if exists

## Error Handling

| Condition | HTTP Status | Error Code |
|---|---|---|
| Invalid pagination params | 422 | Pydantic validation |
| PURL not found on PATCH | 404 | `not_found` |
| Empty purls list on DELETE | 422 | Pydantic validation |
| Invalid CSV (no headers, wrong format) | 400 | `invalid_csv` |
| Missing required CSV columns | 400 | `invalid_csv` |
| CSV too large | 413 | `file_too_large` |

## Testing Strategy

### Integration Tests

- `test_db_admin_list_purls` — pagination, filtering, empty results
- `test_db_admin_update_purl` — edit repository_url, re-key PURL, not-found
- `test_db_admin_delete_purls` — single delete, bulk delete, empty list
- `test_db_admin_import_csv` — upsert strategy, skip strategy, validation errors, duplicates
- `test_db_admin_export_csv` — export all, export with filters, CSV format

### Test Infrastructure

Use existing `TestClient` + `FakeResolver` + `InMemoryCache` patterns. The `InMemoryCache` implementation of new methods enables hermetic testing without PostgreSQL.

## Invariants

- All admin operations go through the `Storage` interface — no direct SQL in the API layer
- The admin page does not affect existing pages or endpoints
- PURL primary key changes use DELETE + INSERT in a single transaction
- Import errors do not abort the entire import — partial success is returned
- Export includes all columns regardless of UI column visibility settings

## Configuration

No new configuration parameters. The admin page uses the same database connection as the resolver (via `storage_settings`).

## Navigation Update

All existing pages (`index.html`, `sbom.html`) must add a navigation link to `/db-admin`. The `db-admin.html` page includes links back to the other pages.
