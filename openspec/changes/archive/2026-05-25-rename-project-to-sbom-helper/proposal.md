## Why

The project is currently named "PURL Resolver" / `purl-resolver` everywhere except the repository directory name (`sbom-helper`). This inconsistency causes confusion — the project's future scope includes SBOM processing, batch resolution, and multi-resolver support, not just single PURL resolution. Renaming now avoids rebranding pain later when those features land.

## What Changes

### Display names & metadata
- `pyproject.toml`: project name `purl-resolver` → `sbom-helper`
- `docker-compose.yml`: image name `purl-resolver:latest` → `sbom-helper:latest`, container name `purl-resolver` → `sbom-helper`
- `src/purl_resolver/main.py`: FastAPI title `"PURL Resolver"` → `"sbom-helper"`
- `src/purl_resolver/templates/index.html`: page title and heading `"PURL Resolver"` → `"sbom-helper"`
- `README.md`: header `"PURL Resolver"` → `"sbom-helper"`

### Documentation
- `specs/META.md`: header and project reference updated
- `specs/WORKFLOW.md`: project reference updated
- `specs/contracts/api-contract.md`: provider description updated
- All internal file-path references in specs (e.g. `src/purl_resolver/...`) remain unchanged — they reference the Python package, not the project

### What does NOT change
- Python package name `purl_resolver` (`src/purl_resolver/`) — changing the package would break imports, egg-info, and the module path used in Docker CMD and uvicorn

## Capabilities

### New Capabilities
*(none — this is a rename, no new capabilities)*

### Modified Capabilities
*(none — spec-level behaviour is unchanged)*

## Impact

- **Docker image tag** changes from `purl-resolver:latest` to `sbom-helper:latest` — any external consumers pulling this image must update their references
- **pyproject.toml name** change affects how the package appears in `pip list` and any tooling that reads the project name
- No APIs, routes, response formats, or functional behaviour changes
