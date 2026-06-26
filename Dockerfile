FROM node:20-alpine AS frontend-build
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build


FROM python:3.12-slim AS dev

WORKDIR /app

RUN addgroup --system --gid 1001 app && \
    adduser --system --uid 1001 --gid 1001 app

RUN apt-get update && \
    apt-get install -y --no-install-recommends git subversion mercurial openssl && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY src/ ./src/

RUN pip install --no-cache-dir -e ".[dev]" && \
    rm -rf /root/.cache

COPY scripts/ ./scripts/
COPY --from=frontend-build /frontend/dist/ /app/frontend/dist/
RUN bash scripts/generate-ssl-cert.sh && \
    chown -R app:app /app

EXPOSE 8443

ENTRYPOINT ["/app/scripts/entrypoint.sh"]

CMD ["uvicorn", "purl_resolver.main:app", "--host", "0.0.0.0", "--port", "8443", \
     "--ssl-keyfile", "/app/ssl/server.key", "--ssl-certfile", "/app/ssl/server.crt", "--reload"]


FROM python:3.12-slim AS prod

WORKDIR /app

RUN addgroup --system --gid 1001 app && \
    adduser --system --uid 1001 --gid 1001 app

RUN apt-get update && \
    apt-get install -y --no-install-recommends git subversion mercurial openssl && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY src/ ./src/

RUN pip install --no-cache-dir . && \
    rm -rf /root/.cache

COPY scripts/ ./scripts/
COPY --from=frontend-build /frontend/dist/ /app/frontend/dist/
RUN bash scripts/generate-ssl-cert.sh && \
    chown -R app:app /app

EXPOSE 8443

ENTRYPOINT ["/app/scripts/entrypoint.sh"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request, ssl; ctx=ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE; urllib.request.urlopen('https://localhost:8443/health', context=ctx)"

CMD ["uvicorn", "purl_resolver.main:app", "--host", "0.0.0.0", "--port", "8443", \
     "--ssl-keyfile", "/app/ssl/server.key", "--ssl-certfile", "/app/ssl/server.crt"]
