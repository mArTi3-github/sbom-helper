# Found-by and Resolver Tracking

**Date:** 2026-06-10
**Status:** Approved

## Problem

When a source code link is returned in the web interface, users need to know *how* it was found — whether it came from the local database cache or was resolved fresh by a resolver, and which specific resolver (purl2repo, ecosyste.ms, libraries.io) was responsible.

Currently the `resolver` field exists in the database and API response but is not displayed in the PURL Resolver or SBOM Updater UIs. There is also no way to distinguish cache hits from fresh resolutions.

## Design

### 1. Schema — `found_by` field

Add a runtime-only field to `ResolveResponse` in `src/purl_resolver/schemas.py`:

```
class ResolveResponse(BaseModel):
    ...
    resolver: str = ""
    found_by: str = ""        # "local_db" | "resolver" | ""
    resolved_at: str = ""
```

Semantics:
- `found_by = "local_db"` — result served from cache; `resolver` shows who originally found it
- `found_by = "resolver"` — result found by a resolver in this request; `resolver` = resolver name
- `found_by = ""` — no result or error

This field is NOT stored in the database. It is computed at the service layer on each response. `PurlRow`, `UpsertRow`, `from_response()`, `to_resolve_response()` are not affected.

### 2. Service layer — `service.py`

**`resolve_purl()`** — two insertion points:

- **Cache hit** (after `_validate_cached_url`, before `return ResolveResult.ok(cached)`):
  ```python
  cached.found_by = "local_db"
  ```

- **Fresh resolver result** (alongside `resolver=r.name`):
  ```python
  response = ResolveResponse(..., resolver=r.name, found_by="resolver")
  ```

- **No result** (fallthrough — all resolvers returned None):
  No `found_by` needed (defaults to `""`).

**`resolve_batch()`** — type change:
  ```python
  # Before:
  async def resolve_batch(...) -> dict[str, str | None]:
  # After:
  async def resolve_batch(...) -> dict[str, ResolveResponse]:
  ```
  Returns the full `ResolveResponse` instead of just the URL string, so metadata propagates through the SBOM pipeline without additional DB lookups.

**`_validate_cached_url()`** — unchanged; `storage.store(cached)` does not use `found_by`.

### 3. SBOM pipeline

**`sbom_enrichment.py`** — extract URLs for `enrich_sbom()` (whose interface stays unchanged):
  ```python
  resolved = await resolve_batch(...)  # dict[str, ResolveResponse]
  resolved_urls = {k: v.repository_url for k, v in resolved.items() if v is not None}
  enrich_sbom(sbom_data, components, resolved_urls)
  ```

**`sbom/reporter.py`** — `build_report()` accepts `dict[str, ResolveResponse]`:
  ```python
  results.append({
      "purl": key,
      "status": "found",
      "repository_url": repo_url,
      "found_by": resolved[key].found_by if resolved.get(key) else "",
      "resolver": resolved[key].resolver if resolved.get(key) else "",
  })
  ```
  Not-found and removed results get empty strings.

**`sbom/enricher.py`** — no changes. Interface stays `dict[str, str]`.

### 4. PURL Resolver UI — `index.html`

Inside `renderSuccess()`, within the `details` `<dl>` block (after version_reference):

```javascript
${data.found_by ? "<dt>Found by</dt><dd>" + escapeHtml(data.found_by) + "</dd>" : ""}
${data.resolver ? "<dt>Resolver</dt><dd>" + escapeHtml(data.resolver) + "</dd>" : ""}
```

Displayed as two separate lines inside the "Show details" spoiler.

### 5. SBOM Updater UI — `sbom.html`

Add two columns to the results table `<thead>`:
```html
<th>Found by</th>
<th>Resolver</th>
```

In `<tbody>` rendering, add corresponding `<td>` cells populated from `r.found_by` and `r.resolver`.

### 6. Resolver self-identification

Each resolver already correctly fills the `resolver` field:
- `Purl2RepoResolver.name` → `"purl2repo"`
- `EcosystemsResolver.name` → `"ecosyste.ms"`
- `LibrariesIoResolver.name` → `"libraries.io"`
- SBOM pre-existing references are stored with `resolver="import-sbom"`
- CSV imports use `resolver="import-csv"`

No changes needed to resolver implementations.

### Files to modify

| File | Change |
|---|---|
| `src/purl_resolver/schemas.py` | Add `found_by` field |
| `src/purl_resolver/service.py` | Set `found_by` in cache hit and resolver paths; change `resolve_batch` return type |
| `src/purl_resolver/sbom_enrichment.py` | Extract URLs from rich response for `enrich_sbom` |
| `src/purl_resolver/sbom/reporter.py` | Include `found_by` and `resolver` in result dicts |
| `src/purl_resolver/templates/index.html` | Add Found by and Resolver rows to details |
| `src/purl_resolver/templates/sbom.html` | Add Found by and Resolver columns to table |