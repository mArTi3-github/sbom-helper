# ADR-0004: libraries.io as fallback resolver

## Context

purl2repo does not support all ecosystems. Some packages (especially in less common ecosystems) cannot be resolved. A secondary data source is needed to improve coverage.

## Decision

Add libraries.io as a fallback resolver in the resolver chain. It is:
- Disabled by default, enabled via Settings page (checkbox + API key)
- Tried only after purl2repo fails to find a repository URL
- Uses `httpx` (synchronous) with a 1-second rate limiter
- Errors are logged as warnings and do not interrupt processing (graceful degradation)
- API key validated via `GET /api/v1/platforms?api_key={key}` at save time

## Consequences

- Improved PURL resolution coverage for ecosystems not supported by purl2repo
- No impact on existing behavior when disabled (default state)
- Graceful degradation: libraries.io outages do not affect the primary resolver
- Rate limiting ensures compliance with libraries.io API limits (60 req/min with key)
- Resolver name stored in DB results distinguishes purl2repo vs libraries.io resolution
