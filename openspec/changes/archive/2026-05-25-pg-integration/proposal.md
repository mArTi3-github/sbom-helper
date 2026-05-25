## Why

После MVP результаты резолвинга PURL→repository URL нигде не сохраняются. Каждый повторный запрос одного и того же PURL вызывает purl2repo заново, что приводит к избыточным HTTP-запросам к registry API и замедлению ответа. Требуется персистентное хранилище успешных результатов резолвинга с проверкой перед вызовом резолвера.

## What Changes

- Добавление PostgreSQL как storage layer для результатов резолвинга
- Новый модуль `storage/` с абстрактным протоколом и двумя реализациями: asyncpg и in-memory
- Новый модуль `service.py` для оркестрации lookup → resolver → store
- Изменение `router.py`: вызов `service.resolve_purl()` вместо прямого вызова purl2repo
- Добавление `StorageSettings` в конфигурацию (префикс `DB_`)
- FastAPI lifespan для управления connection pool asyncpg
- Docker Compose: новый сервис `db` (postgres:16-alpine) с volume, healthcheck, depends_on
- SQL-схема `resolved_purls` и автосоздание таблицы при старте
- Graceful degradation: при отказе БД резолвер продолжает работать без кэширования
- Новые тесты: unit (in-memory storage), integration (с реальной БД), обновление существующих API-тестов

## Capabilities

### New Capabilities
- `resolution-storage`: Персистентное хранение результатов успешного резолвинга PURL→repository_url в PostgreSQL. Включает lookup перед вызовом резолвера и сохранение после успешного разрешения.

### Modified Capabilities
- `purl-resolution`: Добавлен шаг DB lookup перед вызовом purl2repo. При наличии результата в БД резолвер не вызывается. При успешном резолвинге результат сохраняется в БД.
- `layers`: Добавлены Storage Layer (модуль `storage/`) и Service Layer (`service.py`). Обновлены правила импортов.
- `api-contract`: Добавлена конфигурация подключения к PostgreSQL (`DB_URL`) через переменные окружения.

## Impact

- **Код**: `src/purl_resolver/` — новые модули `storage/`, `service.py`; изменения в `config.py`, `main.py`, `router.py`
- **Инфраструктура**: новый сервис PostgreSQL в docker-compose.yml, named volume, healthcheck
- **Зависимости**: добавлен `asyncpg` в pyproject.toml
- **Тесты**: новые тесты для storage layer, обновление существующих API-тестов
- **Документация**: ADR-0002, обновление CONTEXT.md
