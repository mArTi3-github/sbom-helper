## Context

A thin FastAPI service that wraps purl2repo and exposes a REST API plus a minimal HTML UI. No database, no Redis, no Docker in MVP. The project follows `src/` layout per Python packaging standards.

## Goals / Non-Goals

**Goals:**
- FastAPI service with `POST /api/v1/resolve`, `GET /health`, `GET /`
- purl2repo integration with canonical JSON response format
- Single HTML page with form + result card
- Pydantic Settings for configuration (env vars + .env)
- File-based caching via purl2repo built-in cache
- Three integration tests (success, 400, unresolved)

**Non-Goals:**
- Database storage (PostgreSQL — Phase 2)
- Distributed caching (Redis — Phase 2)
- Batch resolution (Phase 2)
- Multi-resolver architecture (Phase 3)
- Docker/containerization (Phase 2)
- Playwright E2E tests (Phase 2)
- Separate frontend framework (Next.js — Phase 2+)

## Decisions

- **purl2repo as primary resolver**: returns repository URLs with confidence, evidence, and repository kind natively. purl2src (download URLs) is reserved as a future fallback.
- **Canonical response format**: API response is a stable JSON schema independent of purl2repo internals. This allows changing resolvers without breaking API consumers.
- **Vanilla JS + Jinja2 for UI**: no frontend framework in MVP. The HTML page fetches `/api/v1/resolve` via `fetch()` and renders the result with plain JS. Future frontend (Next.js) will consume the same API endpoints.
- **Error handling hybrid**: 400 for invalid PURL/unsupported ecosystem, 200 with `repository_url: null` for unresolved, 502 for upstream errors.
- **Pydantic Settings for config**: `timeout`, `use_cache`, and other purl2repo settings from environment variables with `.env` support for local development.
- **Integration tests without mocks**: tests call the real purl2repo against live PyPI/npm/Cargo registries. This gives confidence that the integration actually works and catches registry API changes.

## Risks / Trade-offs

- **Live registry dependency in tests**: integration tests require network access and may be flaky if registries are slow. Mitigation: set generous timeouts, mark tests as `@pytest.mark.integration` so they can be skipped in fast-feedback loops.
- **purl2repo is the single point of failure**: if purl2repo has a bug or drops ecosystem support, the entire service is affected. Mitigation: this is acceptable for MVP; multi-resolver with fallback is Phase 3.
- **No persistent storage**: cached results are lost on service restart (file cache survives but is per-host). Mitigation: acceptable for MVP; PostgreSQL is Phase 2.