# SPA Mount Reliability — Упрощение раздачи статики фронтенда

## Проблема

При `pip install .` (prod-сборка Docker) `__file__` модуля `purl_resolver.main` ведёт в
`/usr/local/lib/python3.12/site-packages/purl_resolver/main.py`, а не в
`/app/src/purl_resolver/main.py`. Путь до `frontend/dist` вычисляется неверно,
SPA-staticfiles mount не добавляется, и `GET /` возвращает `{"detail":"Not Found"}`.

Предыдущее решение (importlib.resources + три fallback'а + package_data) было
переусложнено: один из путей гарантированно падал в dev из-за volume mount,
`except Exception: pass` глотал диагностику, а dist дублировался в образе.

## Решение

Использовать единственный путь `/app/frontend/dist` как канонический.
В Docker (оба stage — dev и prod) frontend dist копируется туда на этапе сборки.
Volume mount `./src:/app/src` этот путь не затеняет.

### Детали

1. **`main.py`**: функция `_find_spa_dir()` проверяет только `/app/frontend/dist`.
   Если директория не найдена — `logger.warning` без fallback'ов.
2. **`pyproject.toml`**: package-data возвращается к исходному `storage/schema.sql`.
3. **`Dockerfile`**: удаляется лишний `COPY --from=frontend-build ... ./src/purl_resolver/static/`.
   Существующий `COPY --from=frontend-build ... /app/frontend/dist/` остаётся.
4. **`docker-compose.override.yml`**: добавляется опциональный volume
   `./frontend/dist:/app/frontend/dist` для dev-режима, чтобы изменения
   фронтенда на хосте сразу подхватывались без пересборки образа.

### Инварианты

- Docker dev (с volume mount overlay): dist есть в `/app/frontend/dist` → работает
- Docker dev (без overlay): dist есть в `/app/frontend/dist` из образа → работает
- Docker prod: dist есть в `/app/frontend/dist` из образа → работает
- Если dist нигде нет → `logger.warning`, mount не добавляется, API работает

## Файлы для изменения

- `src/purl_resolver/main.py` — упростить `_find_spa_dir`
- `Dockerfile` — удалить лишний COPY в `./src/purl_resolver/static/`
- `pyproject.toml` — убрать `"static/**"` из package-data
- `docker-compose.override.yml` — добавить `./frontend/dist:/app/frontend/dist`
