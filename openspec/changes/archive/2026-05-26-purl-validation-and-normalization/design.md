## Context

The sbom-helper application currently delegates all PURL validation to the purl2repo library. The purl2repo `InvalidPurlError` surfaces only at the resolver stage, coupling validation to a specific resolver implementation. Storage cache keys use the full PURL string including version and qualifiers, causing cache misses when the same package is queried with different versions. The project plans to support multiple resolvers (purl2repo, LLM-based, purl2src), requiring resolver-agnostic pre-validation and normalized cache keys.

## Goals / Non-Goals

**Goals:**
- Application-level PURL validation using the official `packageurl-python` library, independent of any resolver
- Normalized cache keys (`scheme:type/namespace/name`) for cross-version cache deduplication
- Resolvers receive the full original PURL (with version, qualifiers, subpath) for their own processing
- API response `purl` field returns the normalized form
- New `PurlValidationError` exception — resolver-agnostic, separate from purl2repo's errors
- All existing functionality preserved (resolvers, caching, graceful degradation, error handling)

**Non-Goals:**
- Batch PURL processing endpoint (future)
- SBOM ingestion with repository enrichment (future)
- Migration of existing DB records (manual TRUNCATE only)
- Changes to the web UI (templates/index.html)

## Decisions

1. **Library**: `packageurl-python` (official purl-spec Python implementation, v0.17.6). Provides `PackageURL.from_string()` for parsing/validation and structured access to all PURL components. Chosen over a custom regex parser for spec compliance and zero maintenance burden.

2. **Module structure**: `src/purl_resolver/purl_utils/` with:
   - `__init__.py` — exports `PurlComponents`, `PurlValidationError`, `validate()`, `normalize()`
   - `PurlComponents` dataclass — `scheme`, `type`, `namespace | None`, `name`, `version | None`, `qualifiers | None`, `subpath | None`
   - `PurlValidationError(Exception)` — raised on invalid PURL format
   - `validate(purl: str) -> PurlComponents` — wraps `PackageURL.from_string()`, catches `ValueError` and raises `PurlValidationError`
   - `normalize(components: PurlComponents) -> str` — builds `scheme:type/namespace/name` (namespace only if present)

3. **Validation timing**: In `service.py`, before any storage lookup or resolver call. If `PurlValidationError` is raised, immediately return HTTP 400 with `{"error": "invalid_purl", "message": "..."}`.

4. **Cache key strategy**: Use normalized form for both `storage.lookup()` and `storage.store()`. The `ResolveResponse.purl` field stores the normalized form. Original PURL is passed unmodified to the resolver.

5. **Error origin ambiguity**: HTTP 400 (`invalid_purl`) can now originate from two places — `purl_utils` (early format validation) or purl2repo (ecosystem-specific validation). Both use the same HTTP status and error code; the error message clarifies the source.

6. **No new config**: Validation and normalization are always enabled — part of the system contract. No toggle parameter added.

## Risks / Trade-offs

- **[Cache staleness]** Existing DB records with versioned keys (`pkg:pypi/requests@2.31.0`) won't match new normalized lookups (`pkg:pypi/requests`). → **Mitigation**: Manual `TRUNCATE resolved_purls;` on deploy. Acceptable since no production data exists.
- **[Error source confusion]** `invalid_purl` error from `purl_utils` vs purl2repo looks identical to the client. → **Acceptable**: The client only needs to know the PURL is invalid; internal origin is irrelevant to the API contract.
- **[Performance]** Double validation — `purl_utils` validates PURL format, then purl2repo also validates ecosystem. → **Acceptable**: Format validation is a fast regex-free library call; ecosystem validation is the slower path and only runs if format passes.