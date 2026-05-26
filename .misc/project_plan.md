# PURL Source Repository Resolver — План развития

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

## 2. LLM-резолвер

### Описание

Подключение LLM (Large Language Model) в качестве резолвера для поиска репозитория по PURL. LLM может выполнять поиск в интернете и анализировать результаты, что особенно полезно для редких экосистем или пакетов, которые purl2repo не находит.

### Ключевые вопросы

- Какая LLM используется (GPT, Claude, локальная)?
- Как LLM получает доступ к интернет-поиску (search tool, browsing)?
- Какой формат промпта для LLM?
- Как обрабатывать неструктурированный ответ LLM (парсинг repository_url из текста)?
- Какой timeout для LLM-запроса?
- Нужен ли кэш для результатов LLM (отдельно от основного storage)?
- Должен ли LLM-резолвер использоваться как fallback после purl2repo или параллельно?
- Как оценивать confidence для результатов LLM?

### Зависимости

- Пакет для работы с LLM API (openai, anthropic и т.п.)
- Инструмент для веб-поиска (или встроенный browsing в LLM)

---

## 3. Пакетная обработка PURL

### Описание

Эндпоинт для обработки списка PURL за один запрос. Позволяет клиентам отправлять до N PURL за раз и получать массив результатов.

### API-дизайн (предварительно)

```
POST /api/v1/resolve/batch
```

```json
{
  "purls": ["pkg:pypi/requests@2.31.0", "pkg:npm/express@4.17.1"]
}
```

Ответ:
```json
{
  "results": [
    { "purl": "pkg:pypi/requests", "repository_url": "..." },
    { "purl": "pkg:npm/express", "repository_url": null, "warnings": ["..."] }
  ]
}
```

### Ключевые вопросы

- Максимальный размер batch?
- Обрабатывать последовательно или параллельно (asyncio.gather)?
- Должен ли сбой одного PURL ломать весь batch (fail-fast) или возвращать частичные результаты?
- Нужно ли логирование прогресса для больших batch?

### Зависимости

- Переиспользует `service.resolve_purl()` для каждого PURL
- Новая схема запроса/ответа в `schemas.py`

---

## 4. Обогащение SBOM-файлов

### Описание

Приём SBOM-файла (CycloneDX или SPDX), извлечение всех PURL компонентов, резолвинг каждого, добавление repository_url в результат.

### Формат

- **CycloneDX JSON** — PURL находятся в `metadata.component.purl` и `components[].purl`
- **SPDX JSON** — PURL находятся в `packages[].externalRefs[].referenceLocator` (где `referenceType = "purl"`)

### Архитектура (предварительно)

```
POST /api/v1/resolve/sbom
→ парсинг SBOM (определение формата CycloneDX/SPDX)
→ извлечение PURL-списка
→ batch-резолвинг (см. раздел 3)
→ возврат enriched SBOM (repository_url добавлен к каждому компоненту)
```

### Ключевые вопросы

- Какой формат ответа — enriched SBOM (исходный + repository_url) или плоский список результатов?
- Какой максимальный размер SBOM-файла?
- Нужна ли поддержка SPDX и CycloneDX одновременно?
- Нужна ли поддержка форматов, отличных от JSON (XML, tag-value)?
- Хранить ли enriched SBOM для повторных запросов?

### Зависимости

- Библиотека для парсинга SBOM (или ручной парсинг CycloneDX/SPDX)
- Batch-резолвинг из раздела 3
- Новый эндпоинт в `router.py`

---

## 5. Этапы разработки

### Выполнено

- FastAPI с endpoint `POST /api/v1/resolve`
- GET /health
- GET / (HTML-страница с формой + карточка результата)
- Интеграция purl2repo
- Интеграционные тесты (pytest, hermetic — без сети)
- Docker multi-stage Dockerfile (dev + prod)
- Docker Compose (app + PostgreSQL)
- PostgreSQL для хранения результатов (lookup до purl2repo)
- Service Layer (оркестрация: cache → resolver → store)
- Storage Layer (interface + PostgresCache + InMemoryCache)
- Graceful degradation при отказе БД
- Multi-resolver архитектура (список резолверов в `app.state.resolvers`)
- Application-level PURL validation (purl_utils, packageurl-python)
- Normalized cache keys (`scheme:type/namespace/name`)
- FakeResolver для hermetic тестов
- ADRs: purl2repo, PostgreSQL, purl validation

### Очередные задачи

- **LLM-резолвер** — интеграция LLM как дополнительного резолвера
- **Пакетная обработка** — эндпоинт `POST /api/v1/resolve/batch`
- **Обогащение SBOM** — приём SBOM-файла, резолвинг компонентов

### Будущие возможности

- Redis для distributed caching
- Rate limiting
- Метрики (Prometheus + Grafana)
- Admin dashboard
- Валидация сопоставления PURL и repository URL
