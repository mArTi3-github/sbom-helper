# Architecture Refactoring — Design Spec

## Description

Three focused refactoring tasks to address architectural friction identified in the architecture review:
1. Extract CSV import/export logic from router into a dedicated `csv_io` module
2. Replace untyped `dict[str, object]` in `upsert_many` with typed `UpsertRow` dataclass
3. Eliminate `PurlRowResponse` — use `ResolveResponse` as the single API boundary type

## Key Files

- Create: `src/purl_resolver/csv_io.py` — new CSV I/O module
- Modify: `src/purl_resolver/router.py` — delegate to csv_io, remove CSV parsing logic
- Modify: `src/purl_resolver/storage/interface.py` — add `UpsertRow` dataclass, update `upsert_many` signature
- Modify: `src/purl_resolver/storage/inmemory.py` — read typed `UpsertRow` fields, remove dict parsing
- Modify: `src/purl_resolver/storage/postgres.py` — read typed `UpsertRow` fields, remove dict parsing
- Modify: `src/purl_resolver/schemas.py` — remove `PurlRowResponse`, update `PurlListResponse`
- Modify: `tests/test_db_admin.py` — update tests for new interfaces

## Candidate 1: csv_io Module

### Architecture

New file `src/purl_resolver/csv_io.py` with three pure functions:

```python
def detect_delimiter(text: str) -> str:
    """Detect CSV delimiter (';' or ',') from header line."""

def parse_csv_import(text: str) -> tuple[list[UpsertRow], list[dict]]:
    """Parse CSV text into UpsertRow objects and error list."""

def render_csv_export(rows: list[PurlRow]) -> str:
    """Render PurlRow objects as semicolon-delimited CSV string."""
```

Dependencies: only `csv`, `io`, `json` from stdlib. No FastAPI, Storage, or Pydantic imports.

### Data Flow — Import

```
HTTP request (raw bytes)
  → router: decode UTF-8-sig
  → csv_io.parse_csv_import(text) → (rows: list[UpsertRow], errors: list[dict])
  → router: call storage.upsert_many(rows)
  → router: return ImportResponse
```

### Data Flow — Export

```
HTTP request
  → router: build PurlFilters from query params
  → storage.list_purls() → list[PurlRow]
  → csv_io.render_csv_export(rows) → str
  → router: return Response(content=csv_bytes, media_type="text/csv")
```

### Invariants

- CSV delimiter is always semicolon (`;`)
- BOM is handled by `utf-8-sig` decoding in router (before csv_io)
- JSONB fields (evidence, warnings) serialized as JSON strings within quoted CSV cells
- Empty trailing lines are handled by csv.DictReader (no special processing needed)

## Candidate 2: UpsertRow Dataclass

### Architecture

New dataclass in `storage/interface.py`:

```python
@dataclass
class UpsertRow:
    purl: str
    repository_url: str
    repository_type: str | None = None
    repository_kind: str | None = None
    confidence: str | None = None
    evidence: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    version_reference: str | None = None
    resolver: str = "purl2repo"
```

### Interface Change

```python
# Before
async def upsert_many(self, rows: list[dict[str, object]]) -> tuple[int, int]: ...

# After
async def upsert_many(self, rows: list[UpsertRow]) -> tuple[int, int]: ...
```

### Impact

- InMemoryCache: reads `row.purl`, `row.repository_url`, etc. directly — removes ~30 lines of `str(row.get(...))` and `json.loads()` parsing
- PostgresCache: same — removes ~30 lines of field extraction
- csv_io.parse_csv_import: constructs `UpsertRow` from CSV dict once
- router import endpoint: simplified to `storage.upsert_many(rows)`

## Candidate 3: Eliminate PurlRowResponse

### Architecture

- Delete `PurlRowResponse` class from `schemas.py`
- Change `PurlListResponse.rows` from `list[PurlRowResponse]` to `list[ResolveResponse]`
- Router `list_purls_endpoint` converts `PurlRow` → `ResolveResponse` (instead of `PurlRowResponse`)

### Resulting Type Hierarchy

```
Resolution (resolver/interface.py)     — resolver output
  ↓ thin adapter
ResolveResponse (schemas.py)          — API boundary + storage internal
  ↑ used directly
PurlListResponse.rows                 — API response wrapper
```

Two types instead of four. `PurlRow` (storage internal dataclass) remains for DB query results.

### Conversion

```python
# In router list_purls_endpoint
ResolveResponse(
    purl=r.purl,
    repository_url=r.repository_url,
    repository_type=r.repository_type,
    repository_kind=r.repository_kind,
    confidence=r.confidence,
    evidence=r.evidence,
    warnings=r.warnings,
    version_reference=r.version_reference,
)
```

## Testing Strategy

- csv_io functions tested with pure unit tests (no FastAPI TestClient)
- UpsertRow tested via existing InMemoryCache tests
- PurlRowResponse removal tested via existing API endpoint tests
- All 117 existing tests must continue to pass

## Invariants

- CSV format remains semicolon-delimited
- All existing API endpoints maintain identical response shapes
- Storage interface changes are backward-compatible within the session (no migrations)
- No new dependencies introduced
