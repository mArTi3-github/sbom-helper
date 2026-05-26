## Why

PURL validation currently depends entirely on the purl2repo library. As the system plans to support multiple resolvers (LLM-based, purl2src, etc.), validation must be lifted to the application level — resolver-agnostic, spec-compliant, and independent of any particular backend. Additionally, caching by the full PURL string (including version/qualifiers) causes unnecessary cache misses when the same package is queried under different versions.

## What Changes

- **New `purl-utils` module** — application-level PURL parsing, validation, and normalization using the official `packageurl-python` library
- **Normalized cache keys** — PURLs are reduced to `scheme:type/namespace/name` form for use as storage lookups, enabling cache deduplication across versions
- **Validation before resolvers** — invalid PURLs are caught early by `purl-utils` and return HTTP 400 before any resolver is called
- **Original PURL passed to resolvers** — resolvers receive the full original PURL string (with version, qualifiers, subpath) for their own processing
- **`purl` field in API response** — now returns the normalized form instead of the original PURL
- **New exception `PurlValidationError`** — resolver-agnostic validation error, separate from purl2repo's `InvalidPurlError`
- **DB schema** — existing records become stale; manual `TRUNCATE` required (no production data)

## Capabilities

### New Capabilities
- `purl-validation`: Application-level PURL parsing, validation against the purl-spec specification, and normalization to `scheme:type/namespace/name` form. Uses the official `packageurl-python` library.

### Modified Capabilities
- `purl-resolution`: Resolution flow changes — validation now happens before any resolver call; cache key is the normalized PURL form; response `purl` field returns normalized form.

## Impact

- **New dependency**: `packageurl-python` added to requirements
- **New module**: `src/purl_resolver/purl_utils/` — standalone, resolver-agnostic
- **Modified layer**: `src/purl_resolver/service.py` — integrates validation/normalization before storage lookup and resolver call
- **Modified layer**: `src/purl_resolver/schemas.py` — `ResolveResponse.purl` stores normalized form
- **DB**: existing `resolved_purls` records need manual cleanup
- **Specs**: `specs/domains/purl-resolution.md`, `specs/architecture/layers.md`, `specs/contracts/api-contract.md` updated
- **Tests**: existing integration and unit tests updated to verify normalized purl in responses and cache keys