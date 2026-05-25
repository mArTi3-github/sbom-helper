## 1. Dockerfile

- [x] 1.1 Create `Dockerfile` with multi-stage build: dev stage (editable install, `.dev` deps, `--reload` CMD) and prod stage (non-editable install, non-root `app` user, HEALTHCHECK, `--no-reload` CMD)
- [x] 1.2 Verify prod build: `docker build --target=prod -t purl-resolver .` completes without errors
- [x] 1.3 Verify dev build: `docker build --target=dev -t purl-resolver:dev .` completes without errors

## 2. Docker Compose

- [x] 2.1 Create `docker-compose.yml` with app service: build config (target, context), port mapping, environment variables with `${VAR:-default}` pattern, health check, restart policy
- [x] 2.2 Add placeholder comments for future services (db, redis, reverse-proxy) as commented blocks under services

## 3. Development Override

- [x] 3.1 Create `docker-compose.override.yml` with dev target build and `./src` volume mount for hot-reload
- [x] 3.2 Verify dev mode: `docker compose up` starts the service with hot-reload working

## 4. Build Context

- [x] 4.1 Create `.dockerignore` excluding `.git`, `.venv`, `__pycache__`, `*.pyc`, `.env`, `.pytest_cache`, `.ruff_cache`
- [x] 4.2 Verify build context size: `docker build` output shows minimal context transfer