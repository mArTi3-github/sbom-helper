## Context

The project lives in a directory named `sbom-helper` but every display-name reference says "PURL Resolver" or `purl-resolver`. This mismatch affects 8 files across documentation, metadata, Docker config, HTML templates, and the FastAPI app title. The Python package (`src/purl_resolver/`) stays as-is — renaming the importable module is not part of this change.

## Goals / Non-Goals

**Goals:**
- Consistent project name across all display-name references: `sbom-helper`
- All docs, specs, Docker metadata, HTML, and API title reflect the new name
- All existing tests continue to pass

**Non-Goals:**
- Renaming the Python package `purl_resolver` (import path, module string, directory structure) — that's a separate, much higher-risk change
- Changing the repository directory name (already `sbom-helper`)
- Functional behaviour changes

## Decisions

| # | Decision | Rationale |
|---|---|---|
| 1 | Rename `pyproject.toml` name field | Package appears under `sbom-helper` in `pip list`; downstream tooling reads this |
| 2 | Rename Docker image + container name | `docker-compose.yml` uses these; consumers pulling the image need consistency |
| 3 | Rename FastAPI title | Cosmetic but appears in OpenAPI docs served at `/docs` |
| 4 | Rename HTML `<title>` and `<h1>` | Cosmetic — user-facing browser tab and page heading |
| 5 | Rename README heading | First thing a developer sees when opening the repo |
| 6 | Rename specs headers | All 3 spec files reference "PURL Resolver" — keeps docs honest |
| 7 | Keep `src/purl_resolver/` as-is | Changing the importable package would break all imports, Docker CMD, uvicorn module string, and egg-info — zero functional benefit |

## Risks / Trade-offs

- **Docker image name change**: External consumers pulling `purl-resolver:latest` will break. Mitigation: the project is in MVP stage; no documented external consumers.
- **pyproject.toml name change**: `pip install -e .` will register the package as `sbom-helper` in the environment. Old egg-info will be stale — developer must reinstall. Mitigation: add to installation notes.