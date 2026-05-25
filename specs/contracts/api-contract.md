# HTTP API Contract

## Participants

- **Provider**: PURL Resolver service (FastAPI)
- **Consumer**: Any HTTP client (browser, curl, scripts, future frontend)

## Base URL

All API endpoints are served from the root path. No version prefix in the base URL — versioning is in the path (`/api/v1/`).

## Endpoints

### `POST /api/v1/resolve`

Resolve a single PURL to its repository URL.

#### Request

```json
{
  "purl": "pkg:pypi/requests@2.31.0"
}
```

- `purl`: required, non-empty string

#### Success Response (200) — resolved

```json
{
  "purl": "pkg:pypi/requests@2.31.0",
  "repository_url": "https://github.com/psf/requests",
  "repository_type": "github",
  "repository_kind": "source_code",
  "confidence": "high",
  "evidence": ["homepage from PyPI metadata"],
  "warnings": [],
  "version_reference": "https://github.com/psf/requests/tree/v2.31.0"
}
```

#### Success Response (200) — unresolved

```json
{
  "purl": "pkg:pypi/obscure-package@0.0.1",
  "repository_url": null,
  "repository_type": null,
  "repository_kind": null,
  "confidence": null,
  "evidence": [],
  "warnings": ["No repository URL found for this PURL"],
  "version_reference": null
}
```

#### Error Response (400) — invalid PURL

```json
{
  "error": "invalid_purl",
  "message": "PURL must start with 'pkg:'."
}
```

#### Error Response (502) — upstream error

```json
{
  "error": "upstream_error",
  "message": "Failed to resolve: registry API timeout"
}
```

#### Validation Error (422) — request body invalid

Standard FastAPI/Pydantic 422 response with field-level validation details.

### `GET /health`

Simple health check for monitoring and container orchestration.

#### Response (200)

```json
{
  "status": "ok"
}
```

### `GET /`

Serve the web UI HTML page.

#### Response (200)

Content-Type: `text/html`. Returns the Jinja2-rendered index page.

## Error Handling Rules

| Condition | HTTP Status | Error Code |
|---|---|---|
| Invalid PURL format | 400 | `invalid_purl` |
| Unsupported ecosystem | 400 | `invalid_purl` |
| Valid PURL, no repository found | 200 | — (`repository_url: null`) |
| purl2repo network/timeout error | 502 | `upstream_error` |
| Empty purl string | 422 | (Pydantic validation) |

## Breaking Change Checklist

- [ ] Removing or renaming a response field
- [ ] Changing the type or format of a response field
- [ ] Changing HTTP status codes for existing conditions
- [ ] Adding required request fields
- [ ] Changing the endpoint URL path
- [ ] Removing or renaming error codes in error responses
