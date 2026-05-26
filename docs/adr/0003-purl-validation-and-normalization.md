# ADR-0003: Application-level PURL validation and normalized cache keys

## Context

PURL validation was previously delegated entirely to purl2repo. As the system plans to support multiple resolvers (LLM-based, purl2src, etc.), validation must be resolver-agnostic. Additionally, caching by the full PURL string (including version/qualifiers) caused unnecessary cache misses when the same package was queried under different versions. The official `packageurl-python` library was chosen over a custom parser because it guarantees spec compliance without maintenance burden.

## Decision

Introduce a `purl_utils/` module between the Service Layer and resolvers that:
1. Parses and validates PURLs using `packageurl-python`
2. Normalizes PURLs to `scheme:type/namespace/name` for use as cache keys
3. Passes the original (unmodified) PURL string to resolvers
4. Raises `PurlValidationError` (separate from purl2repo's `InvalidPurlError`) on invalid input

## Consequences

- Cache deduplication: `pkg:pypi/requests@2.31.0` and `pkg:pypi/requests@3.0.0` share one cache entry
- Resolver output preserves full PURL metadata (version for `version_reference`, qualifiers for type-specific resolution)
- validation is resolver-agnostic — new resolvers receive pre-validated PURLs
- Existing DB records with versioned keys become stale; manual TRUNCATE needed once