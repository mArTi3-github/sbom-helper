# PURL Source Repository Resolver — Черновик архитектуры

## 1. Цель проекта

Веб-приложение и API-сервис для сопоставления Package URL (PURL) с соответствующим репозиторием исходного кода.

Система должна:
- принимать один PURL и возвращать repository URL;
- предоставлять confidence/evidence для результата;
- поддерживать максимально возможное количество экосистем;
- предоставлять удобный REST API;
- предоставлять web UI;
- поддерживать дальнейшее расширение архитектуры и подключение новых резолверов в будущем.

---

## 2. Основные принципы MVP

- **Минимальный стек**: FastAPI + Jinja2 (одна HTML-страница). Без Next.js, PostgreSQL, Redis, Docker Compose — всё это Phase 2+.
- **purl2repo как Primary Resolver**: преобразует PURL в repository_url с confidence и evidence из коробки.
- **purl2src как Fallback Resolver** (future): зарезервирован для phase 3, не входит в MVP.
- **API-first**: все endpoint'ы спроектированы так, чтобы будущий фронтенд (Next.js или иной) подключался без изменений.
- **Кэш**: встроенный файловый кэш purl2repo (`use_cache=True`). Redis — в Phase 2.

---

## 3. Functional Requirements (MVP)

- Сопоставление одного PURL → repository URL
- Возврат confidence (строка: high/medium/low), evidence, warnings, repository_kind, repository_type, version_reference
- Обработка ошибок:
  - Invalid PURL / Unsupported ecosystem → **400**
  - No repository found → **200** с `repository_url: null`
  - Upstream error (таймаут, недоступность registry) → **502**

---

## 4. Технологический стек

### Backend

| Компонент | Технология |
|---|---|
| API Framework | FastAPI |
| Язык | Python 3.11+ |
| Валидация | Pydantic v2 |
| Config | Pydantic Settings (env vars + .env) |
| Primary Resolver | purl2repo |
| API Docs | OpenAPI (встроен в FastAPI) |
| Тестирование | pytest (интеграционные тесты, без моков) |

### Frontend (MVP)

| Компонент | Технология |
|---|---|
| Шаблоны | Jinja2 |
| Стилизация | Vanilla CSS (или минимальный Tailwind CDN) |
| JS | Vanilla JS (fetch API) |

---

## 5. Архитектура MVP

```
+-----------------------------------------------+
|  Docker Container                              |
|  +---------------------------+                 |
|  |     HTTP Client           |                 |
|  |  (Browser, curl, scripts) |                 |
|  +------------+--------------+                 |
|               |                                |
|               v                                |
|  +------------------------+                    |
|  |   FastAPI (один сервис)|                    |
|  |                        |                    |
|  |   POST /api/v1/resolve |                    |
|  |   GET /health          |                    |
|  |   GET / (HTML page)    |                    |
|  +------------------------+                    |
|               |                                |
|               v                                |
|  +------------------------+                    |
|  |   purl2repo            |                    |
|  |   (Python library)     |                    |
|  +------------------------+                    |
+-----------------------------------------------+
```

В MVP нет:
- Отдельного API Gateway / BFF — FastAPI выполняет обе роли.
- PostgreSQL — результаты не сохраняются.
- Redis — кэширование через файловый кэш purl2repo.
- Docker Compose используется для оркестрации одного сервиса (без БД, Redis, reverse proxy).

---

## 6. API Design

### Endpoints

```
POST /api/v1/resolve
GET /health
GET /
```

### Request

```json
{
  "purl": "pkg:pypi/requests@2.31.0"
}
```

### Success Response (200)

```json
{
  "purl": "pkg:pypi/requests@2.31.0",
  "repository_url": "https://github.com/psf/requests",
  "repository_type": "github",
  "repository_kind": "source_code",
  "confidence": "high",
  "evidence": ["homepage from PyPI metadata"],
  "warnings": [],
  "version_reference": "https://github.com/psf/requests/tree/v2.31.0"
}
```

### Unresolved Response (200)

```json
{
  "purl": "pkg:pypi/obscure-package@0.0.1",
  "repository_url": null,
  "repository_type": null,
  "repository_kind": null,
  "confidence": null,
  "evidence": [],
  "warnings": ["No repository URL found for this PURL"],
  "version_reference": null
}
```

### Error Response (400)

```json
{
  "error": "invalid_purl",
  "message": "Invalid PURL format or unsupported ecosystem"
}
```

### Upstream Error (502)

```json
{
  "error": "upstream_error",
  "message": "Failed to resolve: registry API timeout"
}
```

---

## 7. Структура проекта

```
purl-resolver/
├── Dockerfile                 # Multi-stage build (dev + prod)
├── docker-compose.yml         # Orchestration (prod default + future services)
├── docker-compose.override.yml# Dev overrides (volume mount, hot-reload)
├── .dockerignore              # Minimal build context
├── src/
│   └── purl_resolver/
│       ├── __init__.py
│       ├── main.py            # FastAPI app, endpoints
│       ├── config.py          # Pydantic Settings
│       ├── schemas.py         # Pydantic models for request/response
│       ├── router.py          # API routes
│       └── templates/
│           └── index.html     # Single HTML page
├── tests/
│   └── test_api.py            # Integration tests
├── specs/
│   ...
├── docs/
│   └── adr/
│       └── 0001-purl2repo-as-primary-resolver.md
├── CONTEXT.md
├── WORKFLOW.md
├── project_plan.md
└── pyproject.toml
```

---

## 8. Стратегия кэширования (MVP)

- **File-based cache**: встроенный кэш purl2repo (`use_cache=True`) в `~/.cache/purl2repo/`.
- **TTL**: управляется purl2repo (по умолчанию кэширует HTTP-ответы).
- **Без Redis**: добавление Redis — Phase 2.

---

## 9. Стратегия тестирования (MVP)

- **pytest** + FastAPI TestClient
- Три интеграционных теста (без моков purl2repo):
  - Валидный PURL → 200 с repository_url
  - Невалидный PURL → 400
  - Неизвестный PURL → 200 с repository_url: null
- E2E (Playwright) — Phase 2.

---

## 10. Security considerations (MVP)

- Input validation через Pydantic (поле `purl: str`, не пустое)
- Timeout на вызов purl2repo (через config: `PURL2REPO_TIMEOUT`)
- Rate limiting — Phase 2

---

## 11. Этапы разработки

### Phase 1 — MVP (текущий)
- FastAPI с одним endpoint `POST /api/v1/resolve`
- GET /health
- GET / (HTML-страница с формой + карточка результата)
- Интеграция purl2repo
- Интеграционные тесты
- File-based cache purl2repo
- Docker multi-stage Dockerfile (dev + prod)
- Docker Compose для единого сервиса с health check и hot-reload dev режимом

### Phase 2
- PostgreSQL для хранения результатов (lookup до purl2repo)
- Redis для distributed caching
- Batch processing (POST /api/v1/resolve/batch)
- Rate limiting
- Метрики (Prometheus + Grafana)

### Phase 3
- Multi-resolver architecture (LLM-resolver, purl2src как fallback)
- Advanced scoring
- Admin dashboard
- Обработка SBOM-файлов
- Валидация сопоставления PURL и repository URL

---

## 12. Resolved Open Questions

| Вопрос | Решение |
|---|---|
| Какой resolver использовать? | purl2repo (primary), purl2src (future fallback) |
| Нужна ли CLI-обёртка? | Нет — хватает встроенного CLI purl2repo |
| Нужна ли async batch-обработка в MVP? | Нет — batch в Phase 2 |
| Какой стек для UI? | Jinja2 + vanilla JS (без Next.js в MVP) |
| Какая архитектура MVP? | Один FastAPI-сервис (без БД, Redis, Docker) |
| Error handling | 400 / 200 с null / 502 |