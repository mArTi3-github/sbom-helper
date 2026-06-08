# sbom-helper

Resolve Package URLs (PURLs) to source code repository URLs with confidence scoring and evidence.

## Quick Start

```bash
docker compose up -d
```

```bash
curl -X POST http://localhost:8000/api/v1/resolve \
  -H "Content-Type: application/json" \
  -d '{"purl":"pkg:pypi/requests@2.31.0"}'
```

For development with hot-reload:

```bash
docker compose -f docker-compose.yml -f docker-compose.override.yml up
```

## API

| Endpoint | Description |
|---|---|
| `POST /api/v1/resolve` | Resolve a PURL to its repository URL |
| `POST /api/v1/resolve/sbom` | Enrich a CycloneDX SBOM with VCS references (optional: remove unresolved components) |
| `GET /api/v1/db/purls` | List PURLs with pagination and filtering |
| `PATCH /api/v1/db/purls/{purl}` | Edit a PURL row |
| `DELETE /api/v1/db/purls` | Bulk delete PURL rows |
| `POST /api/v1/db/import` | Import PURLs from CSV (semicolon delimiter) |
| `GET /api/v1/db/export` | Export PURLs to CSV (semicolon delimiter) |
| `GET /health` | Health check |
| `GET /api/v1/settings` | Get application settings |
| `PATCH /api/v1/settings` | Update application settings |
| `GET /` | Web UI — PURL resolver |
| `GET /sbom-updater` | Web UI — SBOM enrichment |
| `GET /db-admin` | Web UI — Database administration |
| `GET /settings` | Web UI — Application settings |

## Supported PURL Types

| PURL Type | purl2repo | ecosyste.ms | libraries.io |
|---|:---:|:---:|:---:|
| `bitbucket` | ✓ | | |
| `cargo` | ✓ | ✓ | ✓ |
| `composer` | | ✓ | ✓ |
| `conda` | | ✓ | ✓ |
| `cpan` | | ✓ | ✓ |
| `cran` | | ✓ | ✓ |
| `gem` | | ✓ | ✓ |
| `generic` | ✓ | | ✓ |
| `github` | ✓ | | |
| `golang` | ✓ | ✓ | ✓ |
| `hackage` | | ✓ | ✓ |
| `hex` | | ✓ | ✓ |
| `huggingface` | ✓ | | |
| `maven` | ✓ | ✓ | ✓ |
| `mlflow` | ✓ | | |
| `npm` | ✓ | ✓ | ✓ |
| `nuget` | ✓ | ✓ | ✓ |
| `pub` | | ✓ | ✓ |
| `pypi` | ✓ | ✓ | ✓ |
| `swift` | | ✓ | ✓ |

**Notes:**
- **purl2repo** is the primary resolver (always enabled)
- **ecosyste.ms** is enabled by default as a fallback and accepts any valid PURL via its lookup API
- **libraries.io** is an optional fallback (requires API key, configured via Settings)

## Stack

**Backend:** FastAPI, Pydantic, purl2repo, ecosyste.ms, libraries.io  
**UI:** Jinja2, vanilla JS  
**Infrastructure:** Docker, Docker Compose  
**Python:** 3.11+

## Status

Core features complete: PURL resolution, SBOM enrichment (including storage of pre-existing VCS references and optional removal of unresolved components without subcomponents), and database administration (view, edit, filter, import/export via CSV, bulk delete). CSV uses semicolon delimiter with BOM handling.

**Optional resolvers:** ecosyste.ms is enabled by default as a fallback resolver after purl2repo. libraries.io can be enabled as an additional fallback (requires API key), configured via the Settings page (`/settings`). Supports: Cargo, Composer (Packagist), Conda, CPAN, CRAN, Gem (RubyGems), Generic (GitHub), Go, Hackage, Hex, Maven, NPM, NuGet, Pub, PyPI, Swift (SwiftPM).

See `specs/INDEX.md` for full documentation and `project_plan.md` for upcoming phases.

## Specs

Project specifications live in `specs/`. Start with `specs/INDEX.md`.

## License

Apache 2.0