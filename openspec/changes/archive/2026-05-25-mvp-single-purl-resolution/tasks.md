## 1. Project Scaffolding

- [x] 1.1 Create `pyproject.toml` with project metadata, dependencies (fastapi, uvicorn, pydantic-settings, purl2repo), and dev dependencies (pytest, httpx)
- [x] 1.2 Create `src/purl_resolver/` package structure with `__init__.py`
- [x] 1.3 Create `.env.example` with documented config variables (PURL2REPO_TIMEOUT, PURL2REPO_USE_CACHE)

## 2. Configuration

- [x] 2.1 Implement `config.py` with Pydantic Settings model: `timeout`, `use_cache`, `strict`, `no_network`, `cache_dir`
- [x] 2.2 Load settings from environment variables with sensible defaults (timeout=15s, use_cache=True)

## 3. API Layer

- [x] 3.1 Implement `schemas.py` — Pydantic models for request (`ResolveRequest` with `purl: str`) and canonical response (`ResolveResponse` with all fields: purl, repository_url, repository_type, repository_kind, confidence, evidence, warnings, version_reference)
- [x] 3.2 Implement `router.py` — FastAPI router with three endpoints: `POST /api/v1/resolve`, `GET /health`, `GET /` (HTML)
- [x] 3.3 Implement resolve endpoint: call purl2repo.resolve(), map result to canonical response, handle errors (InvalidPurlError/UnsupportedEcosystemError → 400, NoRepositoryFoundError → 200 with null, ResolutionError/MetadataFetchError → 502)
- [x] 3.4 Implement health endpoint returning `{"status": "ok"}`
- [x] 3.5 Implement root endpoint serving Jinja2 template

## 4. Web UI

- [x] 4.1 Create `templates/index.html` — Jinja2 template with form (input field + submit button) and result area (hidden by default)
- [x] 4.2 Implement vanilla JS in the HTML page: fetch POST /api/v1/resolve on form submit, render result card with repository URL link, confidence badge, and "Show details" toggle
- [x] 4.3 Handle loading state (disable button, show spinner) and error states (400, 502, network failure) in the UI
- [x] 4.4 Handle unresolved state (repository_url: null) — show warning message from API response

## 5. Application Entry Point

- [x] 5.1 Implement `main.py` — create FastAPI app, include router, configure Jinja2 templates, add startup/shutdown events for purl2repo Resolver lifecycle
- [x] 5.2 Add `if __name__ == "__main__"` block for `uvicorn.run()` with configurable host/port

## 6. Integration Tests

- [x] 6.1 Write test for successful resolution: `POST /api/v1/resolve` with `pkg:pypi/requests@2.31.0` → assert HTTP 200, repository_url contains "github.com/psf/requests", confidence is non-empty string
- [x] 6.2 Write test for invalid PURL: `POST /api/v1/resolve` with `"not-a-purl"` → assert HTTP 400
- [x] 6.3 Write test for unresolved PURL: `POST /api/v1/resolve` with a valid but obscure PURL → assert HTTP 200 and repository_url is null
- [x] 6.4 Write test for health endpoint: `GET /health` → assert HTTP 200
- [x] 6.5 Write test for empty purl: `POST /api/v1/resolve` with `{"purl": ""}` → assert HTTP 422