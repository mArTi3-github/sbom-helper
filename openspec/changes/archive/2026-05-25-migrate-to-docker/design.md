## Context

The PURL Resolver runs as a bare Python process via uvicorn. There is no containerization, no standardised development environment, and no health check mechanism for production monitoring. Future phases will add PostgreSQL, Redis, and a reverse proxy — the Docker setup must accommodate this growth without restructuring.

## Goals / Non-Goals

**Goals:**
- Multi-stage Dockerfile with dev and prod targets
- docker-compose.yml for the app service with env vars, health check, restart policy
- docker-compose.override.yml for development (volume mount, hot-reload)
- .dockerignore to keep build context minimal
- Prod stage runs as non-root user

**Non-Goals:**
- Adding PostgreSQL, Redis, or reverse proxy containers (Phase 2+)
- Docker Swarm or Kubernetes orchestration
- CI/CD pipeline changes
- Changes to application code or API behaviour

## Decisions

- **Single multi-stage Dockerfile**: dev stage for interactive development (editable install, `--reload`), prod stage for deployment (non-editable, non-root user, HEALTHCHECK). One file, two targets, no duplication.
- **python:3.12-slim**: official slim image provides glibc compatibility for purl2repo's native dependencies. Alpine (musl) risks incompatibility; distroless is premature complexity for this stage.
- **Env vars only (no .env in image)**: .env is a development-only convenience. Baking it into the image would leak configuration and break the twelve-factor app principle.
- **Compose file with `${VAR:-default}` pattern**: allows deployment-specific overrides (e.g., different ports, timeouts) without editing the compose file.
- **docker-compose.override.yml for dev**: Docker Compose automatically merges override files. Dev mode is a `docker compose up` away without flags.

## Risks / Trade-offs

- **purllib2repo cache is per-container**: file-based cache lives inside the container and is lost on restart. Mitigation: acceptable for MVP; Redis caching is Phase 2.
- **pyproject.toml changes invalidate Docker cache**: any change to pyproject.toml forces a full reinstall. Mitigation: separate COPY for pyproject.toml and src/ to at least cache the COPY layer itself.
- **Dev vs prod divergence**: dev uses editable install with `--reload`, prod uses non-editable. Mitigation: both stages start from the same base image and use identical dependency specs.