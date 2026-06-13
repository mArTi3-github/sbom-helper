# sbom-helper

Resolve Package URLs (PURLs) to source code repository URLs with confidence scoring and evidence.

## Quick Start

```bash
docker compose up -d
```

Open `https://localhost:8443/` in your browser to access the SPA.

For development with hot-reload (src/ is mounted as a volume, changes apply on save):

```bash
docker compose up -d
```

Docker Compose automatically merges `docker-compose.override.yml`, switching the build target to `dev` with `--reload` and source code mounting. No `--build` needed for `src/` changes — uvicorn reloads automatically. Rebuild only when `pyproject.toml` (dependencies) or `frontend/` changes.

**Frontend development** (Vue 3 SPA at `frontend/`):

```bash
cd frontend
npm install
npm run build -- --watch    # auto-rebuild on changes
```

Then `docker compose up -d` (or `docker compose up --build` if the dist directory changed outside the container).

For production, exclude the override file:

```bash
docker compose -f docker-compose.yml up -d
```

## API

| Endpoint | Description |
|---|---|
| `POST /api/v1/resolve` | Resolve a PURL to its repository URL |
| `POST /api/v1/resolve/sbom` | Enrich a CycloneDX SBOM with VCS references (optional: remove unresolved components, validate existing VCS references) |
| `POST /api/v1/convert/images-list` | Convert a CycloneDX SBOM to a machine-readable list of Docker container images |
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
| `GET /images-list-converter` | Web UI — SBOM-to-images-list conversion |

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
**UI:** Vue 3 SPA (Vite, TypeScript, Vue Router) — replaces Jinja2 + vanilla JS  
**Infrastructure:** Docker, Docker Compose  
**Python:** 3.11+

## Status

Core features complete: PURL resolution, SBOM enrichment (including storage of pre-existing VCS references and optional removal of unresolved components without subcomponents), database administration (view, edit, filter, import/export via CSV, bulk delete), and SBOM-to-images-list conversion (promotes container components from CycloneDX SBOMs into a dedicated images list format with completeness flags). CSV uses semicolon delimiter with BOM handling.

**Optional resolvers:** ecosyste.ms is enabled by default as a fallback resolver after purl2repo. libraries.io can be enabled as an additional fallback (requires API key), configured via the Settings page (`/settings`). Supports: Cargo, Composer (Packagist), Conda, CPAN, CRAN, Gem (RubyGems), Generic (GitHub), Go, Hackage, Hex, Maven, NPM, NuGet, Pub, PyPI, Swift (SwiftPM).

**URL validation:** cached repository URLs can be validated via HTTP HEAD + git ls-remote (enabled via `validate_db_urls` setting in Settings). Invalid URLs are deleted from the cache and re-resolved via the resolver chain. Non-http/https URLs are rejected immediately. Validation respects resolver-based cooldown (configurable via `revalidation_cooldown_hours`). The SBOM Updater optionally validates existing VCS references in uploaded SBOMs.

See `specs/INDEX.md` for full documentation and `project_plan.md` for upcoming phases.

## Specs

Project specifications live in `specs/`. Start with `specs/INDEX.md`.

## License

Apache 2.0