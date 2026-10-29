# HTTPS Self-Signed Certificate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable HTTPS with a self-signed certificate for the sbom-helper Docker deployment.

**Architecture:** Generate a self-signed SSL certificate during Docker build using openssl. Configure uvicorn to use the certificate via `--ssl-keyfile` and `--ssl-certfile`. Update healthcheck to use HTTPS. Add optional SSL support for local development via environment variables.

**Tech Stack:** Python, openssl, uvicorn, Docker, Docker Compose

---

### Task 1: Create SSL certificate generation script

**Files:**
- Create: `scripts/generate-ssl-cert.sh`

- [ ] **Step 1: Create the scripts directory**

Run: `mkdir -p scripts`

- [ ] **Step 2: Write the certificate generation script**

Create `scripts/generate-ssl-cert.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

SSL_DIR="/app/ssl"
mkdir -p "$SSL_DIR"

openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout "$SSL_DIR/server.key" \
  -out "$SSL_DIR/server.crt" \
  -days 365 \
  -subj "/CN=localhost" \
  -addext "subjectAltName=IP:127.0.0.1,DNS:localhost"

chmod 600 "$SSL_DIR/server.key"
chmod 644 "$SSL_DIR/server.crt"

echo "SSL certificate generated in $SSL_DIR"
```

- [ ] **Step 3: Make the script executable**

Run: `chmod +x scripts/generate-ssl-cert.sh`

- [ ] **Step 4: Commit**

```bash
git add scripts/generate-ssl-cert.sh
git commit -m "feat: add SSL certificate generation script"
```

---

### Task 2: Update Dockerfile with SSL support

**Files:**
- Modify: `Dockerfile`

- [ ] **Step 1: Update dev stage**

Edit `Dockerfile` — replace the dev stage with:

```dockerfile
FROM python:3.12-slim AS dev

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends openssl && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY src/ ./src/
COPY scripts/ ./scripts/

RUN pip install --no-cache-dir -e ".[dev]"
RUN bash scripts/generate-ssl-cert.sh

EXPOSE 8443

CMD ["uvicorn", "purl_resolver.main:app", "--host", "0.0.0.0", "--port", "8443", \
     "--ssl-keyfile", "/app/ssl/server.key", "--ssl-certfile", "/app/ssl/server.crt", "--reload"]
```

- [ ] **Step 2: Update prod stage**

Edit `Dockerfile` — replace the prod stage with:

```dockerfile
FROM python:3.12-slim AS prod

WORKDIR /app

RUN addgroup --system --gid 1001 app && \
    adduser --system --uid 1001 --gid 1001 app

RUN apt-get update && \
    apt-get install -y --no-install-recommends openssl && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY src/ ./src/
COPY scripts/ ./scripts/

RUN pip install --no-cache-dir . && \
    rm -rf /root/.cache

RUN bash scripts/generate-ssl-cert.sh && \
    chown -R app:app /app

USER app

EXPOSE 8443

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request, ssl; ctx=ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE; urllib.request.urlopen('https://localhost:8443/health', context=ctx)"

CMD ["uvicorn", "purl_resolver.main:app", "--host", "0.0.0.0", "--port", "8443", \
     "--ssl-keyfile", "/app/ssl/server.key", "--ssl-certfile", "/app/ssl/server.crt"]
```

- [ ] **Step 3: Commit**

```bash
git add Dockerfile
git commit -m "feat: enable HTTPS in Dockerfile with self-signed cert"
```

---

### Task 3: Update docker-compose.yml

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1: Update port mapping and healthcheck**

Edit `docker-compose.yml` — change the app service:

```yaml
volumes:
  pgdata:

services:
  app:
    build:
      context: .
      target: ${BUILD_TARGET:-prod}
    image: sbom-helper:latest
    container_name: sbom-helper
    depends_on:
      db:
        condition: service_healthy
    ports:
      - "${PORT:-8443}:8443"
    volumes:
      - ./data:/app/data
    environment:
      - PURL2REPO_TIMEOUT=${PURL2REPO_TIMEOUT:-15.0}
      - PURL2REPO_USE_CACHE=${PURL2REPO_USE_CACHE:-true}
      - PURL2REPO_STRICT=false
      - PURL2REPO_NO_NETWORK=false
      - DB_URL=postgresql://sbom:${DB_PASSWORD:-sbom}@db:5432/sbom
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request, ssl; ctx=ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE; urllib.request.urlopen('https://localhost:8443/health', context=ctx)"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s
    restart: unless-stopped

  db:
    image: postgres:16-alpine
    container_name: sbom-db
    environment:
      POSTGRES_USER: sbom
      POSTGRES_PASSWORD: ${DB_PASSWORD:-sbom}
      POSTGRES_DB: sbom
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U sbom"]
      interval: 3s
      timeout: 3s
      retries: 5
    restart: unless-stopped
```

- [ ] **Step 2: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: switch docker-compose to HTTPS port 8443"
```

---

### Task 4: Add optional SSL support in main.py for local development

**Files:**
- Modify: `src/purl_resolver/main.py`

- [ ] **Step 1: Update main() function to support optional SSL**

Edit `src/purl_resolver/main.py` — replace the `main()` function:

```python
def main() -> None:
    import os

    ssl_keyfile = os.environ.get("SSL_KEYFILE")
    ssl_certfile = os.environ.get("SSL_CERTFILE")

    kwargs: dict = {
        "host": "0.0.0.0",
        "port": 8443,
        "reload": True,
    }

    if ssl_keyfile and ssl_certfile:
        kwargs["ssl_keyfile"] = ssl_keyfile
        kwargs["ssl_certfile"] = ssl_certfile

    uvicorn.run("purl_resolver.main:app", **kwargs)
```

- [ ] **Step 2: Commit**

```bash
git add src/purl_resolver/main.py
git commit -m "feat: add optional SSL support for local development"
```

---

### Task 5: Verify the implementation

**Files:**
- None (verification only)

- [ ] **Step 1: Build and start the Docker containers**

Run: `docker compose up --build -d`

Expected: Both containers start, healthcheck passes

- [ ] **Step 2: Verify healthcheck passes**

Run: `docker compose ps`

Expected: `sbom-helper` shows `healthy` status

- [ ] **Step 3: Verify HTTPS access**

Run: `curl -k https://localhost:8443/health`

Expected: `{"status": "ok"}`

- [ ] **Step 4: Verify HTTP is not accessible**

Run: `curl -s http://localhost:8443/health 2>&1 || true`

Expected: Connection refused or error (no HTTP listener)

- [ ] **Step 5: Stop containers**

Run: `docker compose down`
