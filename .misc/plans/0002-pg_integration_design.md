# PostgreSQL Integration Design

## Motivation

Сохранять результаты успешного резолвинга PURL→repository URL в PostgreSQL. При повторном запросе того же PURL поиск сначала выполняется в БД; если результат не найден — вызывается резолвер.

## Architecture

```
                    ┌─────────────────────────────────────────────────┐
                    │                 FastAPI App                      │
                    │  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │
                    │  │ router   │→ │ service  │→ │ storage/     │  │
                    │  │ (HTTP)   │  │ (orch.)  │  │ postgres.py  │  │
                    │  └──────────┘  └────┬─────┘  └──────┬───────┘  │
                    │                     │               │          │
                    │                     ↓               │          │
                    │              ┌──────────┐           │          │
                    │              │ purl2repo │          │          │
                    │              │ (resolver)│          │          │
                    │              └──────────┘           │          │
                    └─────────────────────────────────────┼──────────┘
                                                          │
                    ┌─────────────────────────────────────┼──────────┐
                    │              Docker Network         │          │
                    │              ┌──────────┐           │          │
                    │              │ postgres │◄──────────┘          │
                    │              │ :5432    │                      │
                    │              └──────────┘                      │
                    └────────────────────────────────────────────────┘
```

## Flow

```
POST /api/v1/resolve
  │
  ├─ 1. service.resolve_purl(purl)
  │     │
  │     ├─ 2. storage.lookup(purl)
  │     │     ├── найдено → вернуть ResolveResponse (200)
  │     │     └── не найдено → продолжить
  │     │
  │     ├─ 3. purl2repo.resolve(purl)  (первый резолвер)
  │     │     ├── успех + repository_url не null
  │     │     │     └─ storage.store(result) → вернуть (200)
  │     │     ├── успех + repository_url null
  │     │     │     └─ вернуть (200), не пишем в БД
  │     │     └── ошибка
  │     │           └─ вернуть (400/502), не пишем в БД
  │     │
  │     └─ (future) другие резолверы в порядке приоритета
  │
  └─ router → JSONResponse
```

## Decisions

### Resolved Decisions

| # | Question | Decision |
|---|---|---|
| 1 | PostgreSQL, Redis или оба? | **Только PostgreSQL**. Redis отложен. |
| 2 | Библиотека для работы с БД | **asyncpg** напрямую (без ORM). Для одной таблицы ORM — overkill. При расширении схемы рефакторинг на SQLAlchemy тривиален (меняется один файл). |
| 3 | Что хранить в БД | **Только успешные результаты** (`repository_url` не null). Неуспешные не кэшируем — при повторном запросе резолвер вызывается снова. |
| 4 | Схема таблицы `resolved_purls` | `purl TEXT PK`, `repository_url TEXT`, `repository_type TEXT`, `repository_kind TEXT`, `confidence TEXT`, `evidence JSONB`, `warnings JSONB`, `version_reference TEXT`, `resolver TEXT NOT NULL`, `resolved_at TIMESTAMPTZ`. Набор полей расширяемый — новые колонки добавляются без ломки совместимости. |
| 5 | Колонка `resolver` | Добавлена (см. пункт 4). Для multi-resolver аналитики в будущем. |
| 6 | Тестирование | **Интерфейс (протокол) + in-memory fake для юнит-тестов + один smoke-тест с реальной БД.** |
| 7 | Структура модулей | Новый модуль `storage/` с тремя файлами: `interface.py` (протокол), `postgres.py` (asyncpg), `inmemory.py` (dict). |
| 8 | Оркестрация | Отдельный `service.py` с функцией `resolve_purl()`. Router (HTTP) → service (orchestration) → storage + resolvers. |
| 9 | Connection pool | FastAPI `lifespan` — pool создаётся в `app.state` при старте, закрывается при остановке. |
| 10 | Миграции | `CREATE TABLE IF NOT EXISTS` при старте приложения + `schema.sql` как source of truth в репозитории. Alembic — когда появятся ALTER TABLE. |
| 11 | Graceful degradation | При отказе БД сервис продолжает работать без кэширования (логируем ошибку, вызываем резолвер напрямую). |
| 12 | Docker Compose | Добавлен сервис `db: postgres:16-alpine` с named volume и healthcheck. `app` зависит от `db` через `depends_on: condition: service_healthy`. |
| 13 | Секреты | Пароль БД через `${DB_PASSWORD}` в docker-compose.yml. Dev — `.env` (не в git). Prod — внешнее хранилище (Docker secrets / Kubernetes Secrets / HashiCorp Vault) — возможно, будет добавлено в будущем, сейчас не нужно. |
| 14 | Конфигурация | Отдельный класс `StorageSettings` с префиксом `DB_`. Переменная `DB_URL`. Не смешивается с настройками purl2repo (`PURL2REPO_*`). |
| 15 | Файловый кэш purl2repo | Оставлен включённым. Кэширует HTTP-ответы registry API (другой уровень, не конфликтует с БД). |
| 16 | Schema creation | Auto-create on startup + schema.sql for reference |

### Future Expansion

- **Multi-resolver**: `service.py` итерирует список резолверов, storage общий для всех. Новый резолвер = реализовать протокол + добавить в список.
- **Batch resolve**: переиспользует `service.resolve_purl()` в цикле.
- **SBOM enrichment**: переиспользует `service.resolve_purl()` для каждого purl в SBOM.

## Configuration

### New Settings Class

```python
class StorageSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DB_")
    url: str = "postgresql://sbom:sbom@localhost:5432/sbom"
    pool_min_size: int = 2      # future
    pool_max_size: int = 10     # future
```

### docker-compose.yml additions

```yaml
volumes:
  pgdata:

services:
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

  app:
    depends_on:
      db:
        condition: service_healthy
    environment:
      - DB_URL=postgresql://sbom:${DB_PASSWORD:-sbom}@db:5432/sbom
```

## SQL Schema

```sql
CREATE TABLE IF NOT EXISTS resolved_purls (
    purl             TEXT PRIMARY KEY,
    repository_url   TEXT NOT NULL,
    repository_type  TEXT,
    repository_kind  TEXT,
    confidence       TEXT,
    evidence         JSONB DEFAULT '[]',
    warnings         JSONB DEFAULT '[]',
    version_reference TEXT,
    resolver         TEXT NOT NULL DEFAULT 'purl2repo',
    resolved_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

## File Structure Changes

```
src/purl_resolver/
├── config.py              ← + StorageSettings
├── main.py                ← + lifespan (pool init/close)
├── service.py             ← NEW — orchestration logic
├── router.py              ← calls service.py, not purl2repo directly
├── schemas.py             ← unchanged
├── storage/
│   ├── __init__.py        ← NEW
│   ├── interface.py       ← NEW — abstract protocol
│   ├── postgres.py        ← NEW — asyncpg implementation
│   ├── inmemory.py        ← NEW — dict-based (tests)
│   └── schema.sql         ← NEW — source of truth for DDL
├── templates/
│   └── index.html
```

## Testing Strategy

- **Unit tests**: `storage/inmemory.py`, `service.py` — быстрые, без Docker
- **Integration test**: один тест с реальной БД (через TestContainers или локальный контейнер)
- **Existing API tests**: обновлены — передают `InMemoryCache` в app, проверяют, что повторный запрос возвращает кэшированный результат

## ADR

Создан отдельный ADR: `docs/adr/0002-postgres-for-resolution-storage.md`.