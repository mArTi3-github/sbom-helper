## Why

The PURL Resolver currently runs directly via uvicorn with a local .env file and manual dependency setup. Containerization ensures consistent environments across development and production, simplifies onboarding, and establishes the infrastructure pattern for future services (PostgreSQL, Redis, reverse proxy).

## What Changes

- New `Dockerfile` with multi-stage build (dev + prod targets)
- New `docker-compose.yml` configuring the app service with env vars, health check, and restart policy
- New `docker-compose.override.yml` for development (volume mount, hot-reload)
- New `.dockerignore` excluding build artifacts from the Docker context
- No changes to application code or API behaviour

## Capabilities

### New Capabilities
- `container-deployment`: Docker-based packaging and orchestration for the PURL Resolver service. Supports development (hot-reload, volume mounts) and production (non-root user, health check, no-dev deps) modes.

### Modified Capabilities
<!-- No existing capabilities — this is purely an infrastructure change -->

## Impact

- Four new files: `Dockerfile`, `docker-compose.yml`, `docker-compose.override.yml`, `.dockerignore`
- No changes to `src/`, `tests/`, `pyproject.toml`, or any existing code
- Development workflow changes from `uvicorn purl_resolver.main:app --reload` to `docker compose up`
- `PURL2REPO_*` env vars now also configurable via `${VAR:-default}` in compose file
- Future services (db, redis, proxy) can be added as new blocks under `services:` without restructuring