# Plan 0001 — Migrate to Docker

## Why

Containerize the PURL Resolver for consistent development and production environments. Phase 1 (MVP) ships as a standalone FastAPI service; the Docker setup must accommodate future services (PostgreSQL, Redis, reverse proxy) without restructuring.

## Decisions

| # | Decision | Choice |
|---|---|---|
| 1 | Number of containers in this phase | One — FastAPI app only |
| 2 | Base image | `python:3.12-slim` |
| 3 | Dockerfile approach | Single multi-stage Dockerfile (dev + prod targets) |
| 4 | Config in container | Env vars only (no .env inside image) |
| 5 | Non-root user | `app` user (uid=1001) in prod stage |
| 6 | Dev stage | Volume-mount src/ for hot-reload, `--reload` flag |
| 7 | Health check | HTTP GET `/health` via Python urllib |

## Files to Create

- `Dockerfile` — multi-stage (dev, prod)
- `docker-compose.yml` — prod by default, placeholder comments for future services
- `docker-compose.override.yml` — dev overrides (target: dev, volume mount, reload)
- `.dockerignore` — exclude .git, .venv, caches, .env

## Dockerfile Structure

```
python:3.12-slim
├── dev stage
│   ├── Install dev deps (editable, ".[dev]")
│   ├── Volume-mount src/ at runtime for hot-reload
│   └── CMD: uvicorn --reload
│
└── prod stage
    ├── Create non-root `app` user
    ├── Copy src/ + pyproject.toml
    ├── pip install --no-cache-dir (non-editable, no dev)
    ├── USER app
    ├── HEALTHCHECK on /health
    └── CMD: uvicorn (no --reload)
```

## docker-compose.yml Shape

```yaml
services:
  app:
    build:
      context: .
      target: ${BUILD_TARGET:-prod}
    image: purl-resolver:latest
    ports:
      - "${PORT:-8000}:8000"
    environment:
      - PURL2REPO_TIMEOUT=${PURL2REPO_TIMEOUT:-15.0}
      - PURL2REPO_USE_CACHE=${PURL2REPO_USE_CACHE:-true}
      - PURL2REPO_STRICT=false
      - PURL2REPO_NO_NETWORK=false
    healthcheck:
      test: ["CMD", "python", "-c", "..."]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s
    restart: unless-stopped

  # db:      (Phase 2)
  # redis:   (Phase 2)
  # proxy:   (Phase 2+)
```

## Future Extensibility

- New services are added as new blocks under `services:` — no restructuring needed
- Prod target stays as default (`BUILD_TARGET=prod`); dev uses override file
- Env vars pattern (`${VAR:-default}`) allows per-deployment overrides without editing compose file