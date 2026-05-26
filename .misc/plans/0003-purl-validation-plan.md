# Proposal: Application-level PURL Preprocessing & Validation

## Motivation

PURL validation currently depends on purl2repo's own validation logic. As the system plans to support multiple resolvers (purl2repo, LLM-based, purl2src, etc.), validation must be lifted to the application level — resolver-agnostic, spec-compliant, and independent of any particular backend.

## Resolved Decisions

### 1. Normalized PURL as cache key

Cache key format: `scheme:type/namespace/name` (namespace only if present).

| Component in original PURL | Included in normalized form? |
|---|---|
| scheme ("pkg") | Yes |
| type | Yes |
| namespace | Yes, if present |
| name | Yes |
| version | No |
| qualifiers | No |
| subpath | No |

**Rationale**: Deduplicates cache entries for the same package across versions. A single lookup covers all queries for that package regardless of version.

### 2. Original PURL passed to resolvers

Resolvers receive the **original, unmodified** PURL string. purl2repo uses `version` for `version_reference`; future LLM resolvers may use qualifiers for disambiguation.

### 3. No `original_purl` in response

API response returns `purl` = normalized form. The original PURL is not exposed to the client.

### 4. New module: `src/purl_resolver/purl_utils/`

Responsibilities:
- `validate(purl: str) -> PurlComponents` — parse & validate, raise `PurlValidationError` on failure
- `normalize(components: PurlComponents) -> str` — produce `scheme:type/namespace/name`
- Uses `packageurl-python` (official purl-spec Python library)

### 5. New exception: `PurlValidationError`

Separate from `InvalidPurlError` (purl2repo's exception). Defined in `purl_utils/`.
Ensures the validation layer has zero dependency on any resolver.

### 6. Architecture placement

```
API Layer (router.py) → Service Layer (service.py) → purl_utils (validate+normalize) → storage.lookup(normalized_key)
                                                                                       → resolver.resolve(original_purl)
```

Validation happens **before** any resolver call and **before** storage lookup.

### 7. Flow (new)

```
1. API Layer receives raw PURL string
2. Service Layer calls purl_utils.validate(purl_str)
   └── PurlValidationError → return HTTP 400
3. Service Layer calls purl_utils.normalize(components) → purl_key
4. storage.lookup(purl_key)
   └── cache hit → return stored result (purl field in response = purl_key)
5. resolver.resolve(original_purl_str)
6. storage.store(response with purl = purl_key)
7. Return ResolveResponse with purl = purl_key
```

### 8. PostgreSQL changes

- Primary key `purl` now contains the normalized form
- Existing DB records (with versioned keys like `pkg:pypi/requests@2.31.0`) become stale
- Migration: manual `TRUNCATE resolved_purls;` — acceptable since data volume is negligible
- No new columns added

### 9. Configuration

No new config parameters. Validation and normalization are always enabled — part of the system contract.

### 10. API contract

- HTTP 400 (`invalid_purl`) can now originate from two places:
  - `purl_utils` → early validation (before any resolver)
  - purl2repo → ecosystem-specific validation
- `purl` field in response → normalized form

## Task Checklist

- [ ] Add `packageurl-python` to project dependencies
- [ ] Create `src/purl_resolver/purl_utils/__init__.py`
- [ ] Create `PurlValidationError` exception class in `purl_utils/`
- [ ] Create `PurlComponents` dataclass in `purl_utils/`
- [ ] Implement `validate()` — wrap `PackageURL.from_string()`
- [ ] Implement `normalize()` — build `scheme:type/namespace/name`
- [ ] Modify `service.py`:
  - [ ] Call `purl_utils.validate()` first → return 400 on failure
  - [ ] Call `purl_utils.normalize()` → use result as cache key
  - [ ] Pass original PURL string to resolver
  - [ ] Store result with normalized purl as key
- [ ] Update `schemas.py` — `ResolveResponse.purl` receives normalized form
- [ ] Update PostgresCache — no structural changes (purge existing data)
- [ ] Update spec documents:
  - [ ] `specs/domains/purl-resolution.md` — new flow diagram, new types, new invariants
  - [ ] `specs/architecture/layers.md` — add purl_utils layer, update import rules
  - [ ] `specs/contracts/api-contract.md` — note that purl is normalized in response
  - [ ] `specs/META.md` — add purl_utils to File Organization
  - [ ] `specs/INDEX.md` — add task-to-spec mapping for purl validation
- [ ] Update `CONTEXT.md` — terms added
- [ ] Create `docs/adr/0003-purl-validation-and-normalization.md` — done
- [ ] Update `tests/test_api.py` — verify normalized purl in response
- [ ] Update `tests/test_storage.py` — verify normalized key in cache roundtrip

## Future Scope (not in this change)

- Batch PURL processing endpoint
- SBOM ingestion with repository enrichment