# ADR-0005: ecosyste.ms as fallback resolver

## Context

purl2repo does not support all ecosystems. libraries.io improves coverage but requires an API key for reasonable rate limits. A free, no-auth data source is needed to improve coverage further.

## Decision

Add ecosyste.ms as a fallback resolver between purl2repo and libraries.io. It is:
- Enabled by default (no API key required)
- Tried only after purl2repo fails to find a repository URL
- Uses `httpx` (synchronous) with a 15-second timeout
- Errors are logged as warnings and do not interrupt processing (graceful degradation)
- Optional API key for higher rate limits (no validation — API does not distinguish valid/invalid keys)

## Consequences

- Improved PURL resolution coverage for ecosystems not supported by purl2repo
- Enabled by default — no configuration needed for basic usage
- Graceful degradation: ecosyste.ms outages do not affect the primary resolver
- Resolver chain order: purl2repo → ecosyste.ms → libraries.io
- Resolver name stored in DB results distinguishes resolution source
