# sbom-helper

A web application and API service for enriching and validating CycloneDX SBOMs with source code repository references.

## Features

- **PURL → Repository URL resolution** — find the VCS repository URL matching a given Package URL (PURL)
- **SBOM enrichment** — add missing `externalReferences` (type `vcs`) to all components in a CycloneDX SBOM, and validate existing VCS references
- **Container image list generation** — extract container components from an SBOM into a dedicated machine-readable format, with deduplication and FSTEC compliance checks
- **Database administration** — browse, search, edit, delete, import, and export PURL → repository mappings via CSV

## Table of Contents

- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [Supported PURL Types](#supported-purl-types)
- [Settings](#settings)
- [Web UI Sections](#web-ui-sections)
- [Tech Stack](#tech-stack)
- [Requirements](#requirements)
- [Setup](#setup)
- [Updating](#updating)
- [API Reference](#api-reference)
- [Security Notes](#security-notes)
- [Planned Features](#planned-features)
- [License](#license)

## Quick Start

### Requirements

- git
- Docker + Docker Compose

### Setup

```bash
git clone https://github.com/mArTi3-github/sbom-helper.git
cd sbom-helper
docker compose up -d
```

The web UI will be accessible at `https://<ip-address>:8443/` (port 8443 on all network interfaces by default).

### Viewing logs

```bash
docker compose logs --follow
# Exit: CTRL-C
```

### Updating

```bash
./scripts/update.sh         # pulls latest code, rebuilds, redeploys
./scripts/update.sh -v      # verbose mode
```

## Architecture

The core functionality of sbom-helper revolves around resolving `PURL → repository URL`. The resolver chain works as follows:

1. **Validate input** — the PURL is checked against the [Package URL specification](https://github.com/package-url/purl-spec)
2. **Query sources sequentially** (first match wins):
   - **Local database** — cache of previously resolved PURL → VCS URL mappings
   - **[purl2repo](https://github.com/tonylturner/purl2repo)** — open-source resolver for common PURL types
   - **[ecosyste.ms](https://ecosyste.ms/)** — open package registry API (enabled by default)
   - **[libraries.io](https://libraries.io/)** — open source package discovery API (optional, requires API key)
   - **[APK Resolver (Alpine Linux)](https://github.com/alpinelinux/aports)** — last-resort fallback for `pkg:apk/...` PURLs, returns the aports repo URL (enabled by default)
3. **Validate the found URL** — checks if the URL points to a VCS repository using git, svn, hg (Mercurial), and fossil probes
4. **Cache and return** — on success, the mapping is stored in the local database and the URL is returned

## Supported PURL Types

| PURL Type | purl2repo | ecosyste.ms | libraries.io | apk |
|---|:---:|:---:|:---:|:---:|
| `apk` | | | | ✓ |
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
- Support for a PURL type does not guarantee a 100 % resolution rate — it means the resolver chain is capable of processing that type
- **purl2repo** is always enabled as the primary resolver
- **ecosyste.ms** is enabled by default as a fallback
- **libraries.io** is optional and requires an API key, configured via Settings
- **APK resolver** is enabled by default as the last fallback — resolves any `pkg:apk/...` PURL to `https://github.com/alpinelinux/aports` (no API key required)

## Settings

Key settings available in the web UI (`/settings`):

| Setting | Recommended | Description |
|---|---|---|
| `Validate DB URLs` | Enabled | Validates cached repository URLs before returning them. Invalid URLs are deleted and re-resolved through the chain |
| `GitHub Personal Access Token` | Active token | Increases GitHub API rate limits from 60 to 5000 requests/hour. [Create a token](https://github.com/settings/tokens) |
| `Enable APK resolver (Alpine Linux)` | Enabled | Last-resort fallback for Alpine Linux APK packages (`pkg:apk/...`). Always returns `https://github.com/alpinelinux/aports`. No API key required. |
| `Enable libraries.io resolver` + `API key` | Enabled + active key | Enables search across the public libraries.io database. Increases rate limits from 10 to 60 requests/min. [Get a key](https://libraries.io/account) |
| `Enable ecosyste.ms resolver` + `API key` | Enabled + active key | Enables search across the public ecosyste.ms database. Rate limits are dynamic. [Get a key](https://ecosyste.ms/account/api_key) |

Additional settings (URL validation timeout, retry config, batch concurrency, job TTL, log level, connectivity checks) are available in the Settings UI.

**Browser-only settings:** language (English/Russian) and UI theme (light/dark) are stored locally per user.

Server settings are persisted in `data/settings.json`.

## Web UI Sections
### PURL Resolver (`/purl-resolver`)

Accepts one or more PURLs (one per line) and returns the corresponding source code repository URLs in a results table. The returned URL points to the project-level repository, not a specific version.

### SBOM Enricher (`/sbom-updater`)
Accepts a CycloneDX SBOM and returns an enriched SBOM with VCS repository URLs added to all components (recursively).

Two options are available:
- **Ignore patterns** — specify component attributes to skip (e.g., exclude proprietary components with known patterns in `purl`, `group`, or `name`)
- **Remove unresolved leaves** — automatically remove leaf components (those without subcomponents) for which no URL was found. Use with caution.

Processing is asynchronous: each SBOM is handled as a separate job with status tracking, cancellation support, and result download. Job results are stored on the server with a configurable TTL (default: 24 hours).

### Container Images List Converter (`/images-list-converter`)
Accepts a CycloneDX SBOM and extracts all components with `type: "container"` into a new `components` list, deduplicated by `purl`. The generated list is checked against FSTEC requirements (fields: `name`, `version`, `properties`, sub-`components`).

### Database Admin (`/db-admin`)
Manage the local PURL → repository URL mapping database:
- Search and filter records
- Edit PURL or Repository URL values
- Delete records
- Export selected rows as CSV
- Import data from CSV

## Tech Stack

**Backend:**
- Language: Python 3.12
- FastAPI (API framework), Pydantic v2 (data validation), Uvicorn (ASGI server with HTTPS)
- purl2repo (primary resolver), httpx (HTTP client), asyncpg (PostgreSQL), diskcache (URL validation cache), packageurl-python (PURL parsing)
- VCS probes: git, subversion, mercurial, fossil

**Frontend:**
- Language: TypeScript
- Vue 3 + Vite, vue-i18n (en/ru), Pinia (state management), Vue Router

**Infrastructure:**
- Docker + Docker Compose
- Python 3.12-slim (app), postgres:16-alpine (database), node:20-alpine (frontend build)

**Testing:**
- Backend: pytest
- Frontend: vitest + @vue/test-utils

## API Reference

An interactive OpenAPI/Swagger UI is available at `/docs` when the server is running.

## Security Notes

sbom-helper does **not** implement authentication or access control. Protect the service at the infrastructure level — do not expose it to the internet or untrusted networks.

## Planned Features

**Major features:**
- Web UI wrappers for [sbom-checker](https://gitlab.community.ispras.ru/sdl-tools/sbom-checker) CLI tools (ISP RAS)
- GOST field consistency validation (`GOST:attack_surface`, `GOST:security_function` between parent and child components) with auto-fix suggestions
- Additional resolvers for `deb` and other package types; LLM-based resolver with internet search
- Direct source archive download links (`"type": "source-distribution"`) when no VCS repository is available

**Minor improvements:**
- Batch PURL resolution in the UI
- Real-time progress reporting during SBOM enrichment
- Manual record creation in the DB Admin section
- SBOM-based import of PURL → repository mappings into the local DB
- Alternative repository URLs storage (fallbacks when the primary URL becomes invalid)
- Configurable caching of failed resolution/validation attempts
- Structured debug logging with a dedicated UI section
- Version information display in the web UI

## Dev Stand Deployment

After making changes to `frontend/` or `src/`:

```bash
# 1. Rebuild the frontend
cd frontend && npm run build && cd ..

# 2. If pyproject.toml dependencies changed, rebuild the container:
docker compose build --no-cache

# 3. Restart the container:
docker compose up -d
```

Steps 1 and 3 are sufficient for frontend-only or Python source changes (the `src/` directory is mounted as a volume in dev mode).

## Specs

Project specifications live in `specs/`. Start with `specs/INDEX.md`.

## License

Apache 2.0
