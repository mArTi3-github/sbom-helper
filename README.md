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
- [Database backup and restore](#database-backup-and-restore)
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
cp .env.example .env
# For a manual `docker compose up`, set a non-empty SearXNG secret first.
# `scripts/update.sh` generates it automatically if missing.
sed -i "s/^SEARXNG_SECRET=.*/SEARXNG_SECRET=$(openssl rand -hex 32)/" .env
docker compose up -d
```

`docker compose up -d` starts the `app`, `db`, and `searxng` services. `scripts/update.sh` auto-generates `SEARXNG_SECRET` in `.env` when it is missing or empty. If you start the stack manually with `docker compose` and skip that, SearXNG starts with its built-in default key (`ultrasecretkey`); that is fine for this internal, non-exposed service but is not a real secret.

The web UI will be accessible at `https://<ip-address>:8443/` (port 8443 on all network interfaces by default).

### SearXNG (internal web search)

SearXNG is a bundled compose service that gives the LLM resolver real web search. It has no published port and is reachable only from the internal compose network at `SEARXNG_URL` (default `http://searxng:8080`). Its configuration in `searxng/settings.yml` enables the JSON API and disables the rate limiter, both required for tool calls from the app.

The app reaches SearXNG over that internal URL; no API key or external search service is involved. When the app runs outside Docker (bare `.venv`), SearXNG is normally unavailable, and the LLM resolver degrades to answering from the model's own knowledge while returning a tool error to the model.

### Upgrade note

The `searxng` service is always part of the compose stack, so the stack needs a non-empty `SEARXNG_SECRET` even when the LLM resolver is disabled. Existing deployments upgrading via `scripts/update.sh` get it generated automatically (added to `.env` if missing); manual `docker compose` users must set it themselves. The SearXNG image tag is `searxng/searxng:latest` and is intentionally unpinned; it may change behavior between restarts.

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

### Database backup and restore

Full backups of the `resolved_purls` (PURL → repository URL mappings) and `purl_source_archives` (source archive link cache) tables are created and restored on the host. A backup set is two files that share one timestamp:

```bash
./scripts/db_backup.sh                                  # creates backups/sbom_purls_<UTC>.csv.gz and backups/sbom_source_archives_<UTC>.csv.gz
./scripts/db_restore.sh backups/sbom_purls_<UTC>.csv.gz backups/sbom_source_archives_<UTC>.csv.gz
./scripts/db_restore.sh backups/sbom_purls_<UTC>.csv.gz backups/sbom_source_archives_<UTC>.csv.gz --mode replace --yes
```

`db_restore.sh` accepts one file or both, in any order: the table is detected from the exact CSV header. An older backup containing only the PURL mapping file still restores. The default restore mode is `merge`: rows already present in the target database are kept, and only missing PURLs are added. `--mode replace` replaces each restored table independently and deletes rows missing from the backup; without `--yes` it asks for confirmation. The script prints the mode, each file, and the `inserted/skipped/total` counts per table. Run `./scripts/db_backup.sh --help` and `./scripts/db_restore.sh --help` for all options.

## Architecture

The core functionality of sbom-helper revolves around resolving `PURL → repository URL`. The resolver chain works as follows:

1. **Validate input** — each PURL is checked against the [Package URL specification](https://github.com/package-url/purl-spec)
2. **Query sources sequentially** (first match wins):
   - **Local database** — cache of previously resolved PURL → VCS URL mappings
   - **[purl2repo](https://github.com/tonylturner/purl2repo)** — open-source resolver for common PURL types
   - **[deps.dev](https://deps.dev/)** — Google package metadata API, no API key required (enabled by default) — Maven, npm, Go, PyPI, NuGet, Cargo, RubyGems
   - **[ecosyste.ms](https://ecosyste.ms/)** — open package registry API (enabled by default)
   - **[libraries.io](https://libraries.io/)** — open source package discovery API (optional, requires API key)
   - **[APK Resolver (Alpine Linux)](https://github.com/alpinelinux/aports)** — fallback for `pkg:apk/...` PURLs, returns the aports repo URL (enabled by default)
   - **[LLM Resolver]** — optional last-resort resolver: an OpenAI-compatible LLM that calls `web_search` (backed by the bundled SearXNG service) and `web_fetch` tools to find and verify the repository URL (disabled by default)
3. **Validate the found URL** — checks if the URL points to a VCS repository using git, svn, hg (Mercurial), and fossil probes
4. **Cache and return** — on success, the mapping is stored in the local database and the URL is returned

Each resolver after purl2repo can be enabled or disabled independently in Settings. The LLM resolver, when enabled, is always tried last.

## Supported PURL Types

| PURL Type | purl2repo | deps.dev | ecosyste.ms | libraries.io | apk |
|---|:---:|:---:|:---:|:---:|:---:|
| `apk` | | | | | ✓ |
| `bitbucket` | ✓ | | | |
| `cargo` | ✓ | ✓ | ✓ | ✓ |
| `composer` | | | ✓ | ✓ |
| `conda` | | | ✓ | ✓ |
| `cpan` | | | ✓ | ✓ |
| `cran` | | | ✓ | ✓ |
| `gem` | | ✓ | ✓ | ✓ |
| `generic` | ✓ | | | ✓ |
| `github` | ✓ | | | |
| `golang` | ✓ | ✓ | ✓ | ✓ |
| `hackage` | | | ✓ | ✓ |
| `hex` | | | ✓ | ✓ |
| `huggingface` | ✓ | | | |
| `maven` | ✓ | ✓ | ✓ | ✓ |
| `mlflow` | ✓ | | | |
| `npm` | ✓ | ✓ | ✓ | ✓ |
| `nuget` | ✓ | ✓ | ✓ | ✓ |
| `pub` | | | ✓ | ✓ |
| `pypi` | ✓ | ✓ | ✓ | ✓ |
| `swift` | | | ✓ | ✓ |

**Notes:**
- Support for a PURL type does not guarantee a 100 % resolution rate — it means the resolver chain is capable of processing that type
- **purl2repo** is always enabled as the primary resolver
- **deps.dev** is enabled by default, no API key required
- **ecosyste.ms** is enabled by default as a fallback
- **libraries.io** is optional and requires an API key, configured via Settings
- **APK resolver** is enabled by default — resolves any `pkg:apk/...` PURL to `https://github.com/alpinelinux/aports` (no API key required)
- **LLM resolver** is optional and disabled by default; when enabled it is always tried last and performs real web search through the bundled SearXNG service

## Settings

Key settings available in the web UI (`/settings`):

| Setting | Recommended | Description |
|---|---|---|
| `Validate DB URLs` | Enabled | Validates cached repository URLs before returning them. Invalid URLs are deleted and re-resolved through the chain |
| `GitHub Personal Access Token` | Active token | Increases GitHub API rate limits from 60 to 5000 requests/hour. [Create a token](https://github.com/settings/tokens) |
| `Enable deps.dev resolver` | Enabled | Searches the deps.dev package metadata API for Maven, npm, Go, PyPI, NuGet, Cargo, and RubyGems packages. No API key required. |
| `Enable APK resolver (Alpine Linux)` | Enabled | Fallback for Alpine Linux APK packages (`pkg:apk/...`). Always returns `https://github.com/alpinelinux/aports`. No API key required. |
| `Enable libraries.io resolver` + `API key` | Enabled + active key | Enables search across the public libraries.io database. [Get a key](https://libraries.io/account) |
| `Enable ecosyste.ms resolver` + `API key` | Enabled + active key | Enables search across the public ecosyste.ms database. [Get a key](https://ecosyste.ms/account/api_key) |
| `Enable LLM resolver` + `Base URL` + `API key` + `Model` | Disabled | Optional last-resort resolver: an OpenAI-compatible LLM with web search finds the repository URL. Requires a compatible endpoint and API key. The model calls `web_search` through the bundled SearXNG service and `web_fetch` to verify candidate URLs. |
| `Max search rounds` (LLM resolver) | 3 | Maximum tool-calling rounds per LLM attempt (1–10, default 3). Each round may execute one or more `web_search`/`web_fetch` calls. When the limit is exhausted, the resolver stops retrying that PURL. |
| `Verify TLS certificate` + `CA bundle path` (LLM resolver) | On + empty | Controls TLS verification of the LLM endpoint. For an internal LLM behind a corporate CA, set `CA bundle path` to a mounted PEM file with the root/intermediate CA. Turning `Verify TLS certificate` off disables verification — use only as a temporary fallback. |

Additional settings (URL validation timeout, retry config, batch concurrency, batch size limit, job TTL, log level, connectivity checks) are available in the Settings UI.

For an internal LLM endpoint whose certificate is signed by a corporate CA, set the LLM resolver's `CA bundle path` to a mounted PEM file containing the root/intermediate CA; the `Verify TLS certificate` toggle can be turned off only as a temporary fallback. Setting a CA bundle makes httpx trust ONLY that bundle (it replaces, rather than augments, the default system trust store), so a public endpoint would then fail verification unless its CA is also included in the bundle.

**Browser-only settings:** language (English/Russian) and UI theme (light/dark) are stored locally per user.

Server settings are persisted in `data/settings.json`.

## Web UI Sections
### PURL Resolver (`/purl-resolver`)

Accepts one or more PURLs (one per line) in a text area and returns the corresponding source code repository URLs in a results table — one row per input PURL, in input order. The returned URL points to the project-level repository, not a specific version.

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
- purl2repo (primary resolver), httpx (HTTP client), openai (LLM resolver client), asyncpg (PostgreSQL), diskcache (URL validation cache), packageurl-python (PURL parsing)
- VCS probes: git, subversion, mercurial, fossil

**Frontend:**
- Language: TypeScript
- Vue 3 + Vite, vue-i18n (en/ru), Pinia (state management), Vue Router

**Infrastructure:**
- Docker + Docker Compose
- Python 3.12-slim (app), postgres:16-alpine (database), searxng/searxng (internal web search for the LLM resolver), node:20-alpine (frontend build)

**Testing:**
- Backend: pytest
- Frontend: vitest + @vue/test-utils

## API Reference

An interactive OpenAPI/Swagger UI is available at `/docs` when the server is running.

## Security Notes

sbom-helper does **not** implement authentication or access control. Protect the service at the infrastructure level — do not expose it to the internet or untrusted networks.

The LLM resolver's `web_fetch` tool makes outbound requests to URLs proposed by the model, so it enforces a security boundary:

- Only `http` and `https` URLs are fetched.
- Every hostname is resolved and every resolved address is checked on each hop; non-global (including CGNAT/shared, private, loopback, link-local, reserved, multicast, unspecified) addresses are rejected.
- Redirects are followed manually (at most 3) and the scheme plus IP checks are re-applied on every hop.
- Response bodies are capped at 512 KiB and each request has a 15-second timeout; only visible text (at most 8000 characters) is returned to the model.
- Fetches use a separate HTTP client with default TLS verification, independent of the LLM endpoint's `Verify TLS certificate` / `CA bundle path` settings.

The `searxng` service is not exposed outside the compose network and has no published port. Its `SEARXNG_SECRET` is auto-generated into `.env` by `scripts/update.sh` (set it manually before a manual `docker compose up`).

## Planned Features

**Major features:**
- Web UI wrappers for [sbom-checker](https://gitlab.community.ispras.ru/sdl-tools/sbom-checker) CLI tools (ISP RAS)
- GOST field consistency validation (`GOST:attack_surface`, `GOST:security_function` between parent and child components) with auto-fix suggestions
- Additional resolvers for `deb` and other package types
- Direct source archive download links (`"type": "source-distribution"`) when no VCS repository is available

**Minor improvements:**
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
