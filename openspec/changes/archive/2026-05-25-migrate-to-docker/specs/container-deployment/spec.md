## ADDED Requirements

### Requirement: Application runs in Docker container
The application SHALL be packaged as a Docker container with multi-stage build supporting development and production modes.

#### Scenario: Production image builds successfully
- **WHEN** builder runs `docker build --target=prod -t purl-resolver .`
- **THEN** image is created with Python 3.12-slim base, non-root `app` user, and health check configured

#### Scenario: Development image builds successfully
- **WHEN** builder runs `docker build --target=dev -t purl-resolver:dev .`
- **THEN** image is created with editable dependency install suitable for hot-reload development

### Requirement: Health check endpoint is monitored
The production container SHALL have a Docker HEALTHCHECK instruction that verifies the service is running.

#### Scenario: Health check passes
- **WHEN** container is running and the service is healthy
- **THEN** `docker inspect` SHALL show `"Status": "healthy"` for the container

#### Scenario: Health check fails on service down
- **WHEN** the service inside the container stops responding
- **THEN** Docker SHALL mark the container as unhealthy after the configured retries and timeout

### Requirement: Container runs as non-root user
The production container SHALL run the application process under a non-root user for security.

#### Scenario: Process runs as app user
- **WHEN** container starts in production mode
- **THEN** the uvicorn process SHALL run under UID 1001 (app user)

### Requirement: Configuration via environment variables
The container SHALL accept all configuration through environment variables at runtime.

#### Scenario: Custom timeout configured via env var
- **WHEN** container starts with `PURL2REPO_TIMEOUT=30.0`
- **THEN** the application SHALL use 30 second timeout for purl2repo requests

#### Scenario: Default values used when env vars omitted
- **WHEN** container starts without specifying `PURL2REPO_TIMEOUT`
- **THEN** the application SHALL use the default value of 15.0

### Requirement: Docker Compose orchestrates the service
The project SHALL provide a docker-compose.yml that configures the app service with ports, environment, health check, and restart policy.

#### Scenario: Service starts via docker compose
- **WHEN** user runs `docker compose up -d`
- **THEN** the app service SHALL start on port 8000 with configured environment variables

#### Scenario: Development overrides are applied automatically
- **WHEN** user runs `docker compose up` (without specifying override file)
- **THEN** Docker Compose SHALL automatically merge `docker-compose.override.yml`, mounting `./src` as a volume for hot-reload

#### Scenario: Custom port via environment variable
- **WHEN** user runs `PORT=8080 docker compose up -d`
- **THEN** the app service SHALL be accessible on host port 8080

### Requirement: Build context is minimal
The .dockerignore SHALL exclude unnecessary files from the Docker build context.

#### Scenario: Build context excludes .git and caches
- **WHEN** builder runs `docker build`
- **THEN** the build context SHALL NOT include `.git`, `.venv`, `__pycache__`, `.pytest_cache`, or `.env` files