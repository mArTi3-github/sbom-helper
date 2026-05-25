# PURL Resolver

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
| `GET /health` | Health check |
| `GET /` | Web UI |

## Stack

**Backend:** FastAPI, Pydantic, purl2repo  
**UI:** Jinja2, vanilla JS  
**Infrastructure:** Docker, Docker Compose  
**Python:** 3.11+

## Status

MVP — single PURL resolution with file-based caching.  
See `specs/INDEX.md` for full documentation and `project_plan.md` for upcoming phases.

## Specs

Project specifications live in `specs/`. Start with `specs/INDEX.md`.

## License

Apache 2.0