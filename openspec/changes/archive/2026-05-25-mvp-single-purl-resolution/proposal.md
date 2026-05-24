## Why

PURL-to-repository resolution is a manual, slow process in SBOM management. Users need a fast, reliable API and web UI to map Package URLs to their source code repositories. The MVP delivers this core capability using purl2repo as the primary resolver — no database, no Redis, no complex infrastructure.

## What Changes

- New FastAPI service with three endpoints: `POST /api/v1/resolve`, `GET /health`, `GET /`
- Integration with purl2repo library for PURL → repository URL resolution
- Canonical JSON response format (not a proxy of purl2repo internals)
- Single HTML page with form input and readable result card
- Error handling: 400 (invalid PURL), 200 with null (unresolved), 502 (upstream error)
- File-based caching via purl2repo built-in cache
- Three integration tests (success, 400, unresolved)

## Capabilities

### New Capabilities
- `purl-resolution`: Core single-PURL resolution via REST API. Accepts PURL string, returns repository URL with confidence, evidence, warnings, repository kind/type, and version reference.
- `web-ui`: Single HTML page with a form for PURL input and a result card showing repository URL (clickable), confidence, evidence, and expandable details.

### Modified Capabilities
<!-- No existing capabilities to modify -->

## Impact

- New Python project with FastAPI and purl2repo as primary dependencies
- No changes to existing infrastructure (no Docker, no database in MVP)
- Future extensibility preserved: new resolvers, database caching, and richer UI can be added without breaking the API contract