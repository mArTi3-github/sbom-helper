# PURL URL Validation and SBOM Enrichment Fixes — Design

## Problem Summary

When a PURL exists in the local database with an incorrect repository URL:

1. **PURL Resolver** returns the incorrect URL from cache without validation (or with stale validation state)
2. **SBOM Updater** enriches SBOM with the incorrect URL; on subsequent uploads, the component is skipped entirely, creating a permanent staleness trap

Root causes identified:
- "today-cooldown" skips URL validation for all cache entries resolved today, even entries from untrusted/import resolvers
- Rate-limit cooldown returns `VALID` instead of `RATE_LIMITED`, masking invalid URLs
- SBOM pipeline has no mechanism to re-validate VCS references that were previously enriched

## Components

### A. Cooldown logic in `_validate_cached_url()`

**File:** `src/purl_resolver/service.py`

**Current behavior:**
```python
if resolved_date == datetime.now().date():
    return cached
```

**New behavior:**
- Trusted resolvers set: `{"purl2repo", "ecosyste.ms", "libraries.io"}`
- If `cached.resolver` is in trusted set AND elapsed time since `resolved_at` < `cooldown_hours`: skip validation (return cached)
- If `cached.resolver` is NOT in trusted set (e.g. `"import-sbom"`, `"import-csv"`, empty): always validate, no cooldown
- Cooldown period is configurable via `cooldown_hours` setting (default 24, 0 = no cooldown)

**Configuration:**
- New field in `AppSettings`: `revalidation_cooldown_hours: int = Field(default=24, ge=0, le=720)`
- UI: new input in "URL Validation" card in Settings page
- Label/description: "Cooldown period (hours) — re-validation of cached URLs from resolvers is skipped within this window. Imported entries are always re-validated regardless of cooldown."

### B. Rate-limit cooldown returns RATE_LIMITED

**File:** `src/purl_resolver/url_validator.py`

**Current:**
```python
if _RateLimitTracker.is_in_cooldown():
    return UrlValidationResult.VALID
```

**New:**
```python
if _RateLimitTracker.is_in_cooldown():
    return UrlValidationResult.RATE_LIMITED
```

**Impact:** `_validate_cached_url()` handles RATE_LIMITED by preserving cache WITHOUT updating `resolved_at`. After cooldown expires (60s), the next request performs a real validation. Invalid URLs are never masked.

### C. SBOM Updater — validate existing VCS references checkbox

**Files:** `src/purl_resolver/sbom/collector.py`, `src/purl_resolver/sbom_enrichment.py`, `src/purl_resolver/templates/sbom.html`

**New parameter:** `validate_existing_refs: bool = False` in `SbomEnrichmentPipeline.process()`

**Flow when `validate_existing_refs=True`:**
1. After `collect_components()`, filter components with `needs_enrichment=False` AND non-empty `existing_references`
2. For each such component, call `validate_url()` on the VCS URL from `existing_references`
3. If result is `INVALID`: set `needs_enrichment=True`, clear `existing_references = []`, add PURL to `purls_to_resolve`
4. If result is `NETWORK_ERROR` or `RATE_LIMITED`: leave as-is (don't break valid references due to transient errors)
5. If result is `VALID`: leave as-is

**UI:** New checkbox in sbom.html: "Проверять существующие VCS-ссылки в SBOM"

### D. Settings — cooldown_hours parameter

**Files:** `src/purl_resolver/settings_store.py`, `src/purl_resolver/routes/settings.py`, `src/purl_resolver/templates/settings.html`

**AppSettings new field:**
```python
revalidation_cooldown_hours: int = Field(default=24, ge=0, le=720)
```

0 = no cooldown (always validate regardless of resolver).

## Invariants

- Trusted resolvers list (`purl2repo`, `ecosyste.ms`, `libraries.io`) is a module-level constant in `service.py`
- Cooldown is measured from `resolved_at`, not from current request time
- `cooldown_hours=0` disables cooldown entirely (every request validates)
- Empty/unknown/None resolver always triggers validation
- RATE_LIMITED results never update `resolved_at`
- SBOM existing-ref validation only runs when checkbox is checked (default: off)

## Files Changed

| File | Change |
|------|--------|
| `src/purl_resolver/service.py` | Cooldown logic with resolver check + trusted resolvers constant |
| `src/purl_resolver/url_validator.py` | `VALID` → `RATE_LIMITED` during rate cooldown |
| `src/purl_resolver/sbom_enrichment.py` | New `validate_existing_refs` param + validation loop |
| `src/purl_resolver/sbom/collector.py` | No changes (validation done in pipeline, not collector) |
| `src/purl_resolver/settings_store.py` | New `revalidation_cooldown_hours` field |
| `src/purl_resolver/routes/settings.py` | Expose new setting in API |
| `src/purl_resolver/routes/resolve.py` | Pass `validate_existing_refs` from form data |
| `src/purl_resolver/templates/sbom.html` | New checkbox for existing refs validation |
| `src/purl_resolver/templates/settings.html` | New input for cooldown hours |
| `tests/test_service_validation.py` | Tests for new cooldown logic |
| `tests/test_url_validator.py` | Tests for RATE_LIMITED cooldown |
| `tests/test_sbom_enricher.py` | Tests for existing-refs validation |
| `specs/domains/purl-resolution.md` | Update invariants for new cooldown behavior |
| `specs/architecture/layers.md` | No changes |

## Testing Strategy

### Unit tests

- `test_service_validation.py`:
  - Trusted resolver + within cooldown → validation skipped
  - Trusted resolver + outside cooldown → validation runs
  - Untrusted resolver + within cooldown → validation runs
  - Untrusted resolver + outside cooldown → validation runs
  - cooldown_hours=0 → always validates regardless of resolver
  - RATE_LIMITED does not update resolved_at

- `test_url_validator.py`:
  - During rate cooldown, returns RATE_LIMITED not VALID

- `test_sbom_enricher.py`:
  - validate_existing_refs=True + INVALID VCS ref → marked for re-resolution
  - validate_existing_refs=True + VALID VCS ref → left as-is
  - validate_existing_refs=True + NETWORK_ERROR → left as-is
  - validate_existing_refs=False → no validation of existing refs

- `test_settings_store.py`:
  - Default revalidation_cooldown_hours is 24
  - Can serialize/deserialize correctly