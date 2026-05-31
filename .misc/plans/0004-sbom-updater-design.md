# Plan 0004 — SBOM-updater: Enrich CycloneDX SBOM with Repository URLs

## Motivation

Добавить возможность загружать CycloneDX SBOM (JSON), автоматически находить для его компонентов ссылки на репозитории исходных текстов (VCS), обогащать SBOM этими ссылками и отдавать результат пользователю через Web UI.

## Decisions

| # | Question | Decision |
|---|---|---|
| 1 | Формат входного SBOM | **Только CycloneDX JSON**. SPDX и XML не поддерживаются в MVP. |
| 2 | Глубина обхода components | **Рекурсивный обход без ограничения глубины**. Вложенные `components[]` обрабатываются рекурсивно. |
| 3 | Критерий отбора компонентов | Обрабатываем компоненты, у которых: (а) поле `externalReferences` отсутствует, ИЛИ (б) поле `externalReferences` есть, но среди элементов нет `type=vcs` и `type=source-distribution`. |
| 4 | Архитектурная интеграция | **Единый модуль `sbom/` внутри `purl_resolver/`**. Новый эндпоинт `POST /api/v1/resolve/sbom`. Переиспользует `service.resolve_purl()`. |
| 5 | Web UI | **Отдельная страница `/sbom-updater`** с формой загрузки файла и таблицей результатов. На главной странице `GET /` — ссылка на раздел. |
| 6 | Формат ответа Web UI | **Таблица**: PURL → статус (found/not found) → repository URL (если найден). Кнопка "Скачать обогащённый SBOM". |
| 7 | Дедупликация PURL в SBOM | **Да**. Все PURL нормализуются к `scheme:type/namespace/name`, уникализируются. Резолвятся только уникальные. Найденная ссылка применяется ко всем компонентам с совпадающим нормализованным PURL (независимо от version/qualifiers). |
| 8 | Лимит размера файла | **200 MB**. |
| 9 | Обработка ошибок компонента | **Fault-tolerant**. Если PURL компонента не парсится — пропускаем, логируем, продолжаем. Финальный отчёт показывает кол-во пропущенных. |
| 10 | Сохранение существующих externalReferences | **Да**. Новый элемент `{"type": "vcs", "url": "..."}` добавляется в конец существующего массива. Старые ссылки не удаляются. |
| 11 | Алгоритм поиска репозитория | **purl2repo + локальная БД**. Если purl2repo не находит — "not found". |

## Architecture

```
                    ┌─────────────────────────────────────────────────────┐
                    │                    FastAPI App                       │
                    │  ┌──────────────────────────────────────────────┐   │
                    │  │               router.py                       │   │
                    │  │  POST /api/v1/resolve       (существующий)    │   │
                    │  │  POST /api/v1/resolve/sbom  (НОВЫЙ)           │   │
                    │  │  GET  /sbom-updater         (НОВЫЙ)           │   │
                    │  └──────────┬───────────────────────────────────┘   │
                    │             │                                      │
                    │  ┌──────────▼──────────────────────────────────┐   │
                    │  │           service.py                         │   │
                    │  │  resolve_purl()              (существующий)  │   │
                    │  └─────────────────────────────────────────────┘   │
                    │             │                                      │
                    │  ┌──────────▼──────────────────────────────────┐   │
                    │  │           sbom/                              │   │
                    │  │  parser.py       — парсинг CycloneDX JSON   │   │
                    │  │  collector.py    — рекурсивный сбор PURL    │   │
                    │  │  enricher.py     — вставка externalReferences│   │
                    │  │  reporter.py     — формирование отчёта      │   │
                    │  └─────────────────────────────────────────────┘   │
                    │                                                   │
                    │  purl_utils/  storage/  resolvers/ (существующие) │
                    └─────────────────────────────────────────────────────┘
```

## Flow

```
1. User opens GET /sbom-updater
2. User uploads CycloneDX JSON file (≤ 200 MB) via form
3. Server receives file, validates JSON structure, checks bomFormat/specVersion
4. sbom/parser.py parses the SBOM into an internal representation
5. sbom/collector.py recursively walks components[]:
   - Checks each component: has PURL? AND (externalReferences missing OR no vcs/source-distribution)
   - Normalizes PURL via purl_utils.normalize()
   - Collects unique normalized PURLs
   - Tracks original component paths for back-insertion
6. For each unique PURL:
   - service.resolve_purl() → storage + purl2repo
   - Records result (found with URL / not found)
7. sbom/enricher.py:
   - For each component that matched a resolved PURL:
     - Inserts {"type": "vcs", "url": "..."} into externalReferences[]
     - Preserves all existing references
   - Increments version field by 1
   - Updates metadata.timestamp
8. sbom/reporter.py builds result table
9. Response: HTML page with:
   - Summary line (e.g., "Найдено 8/12 PURL. Пропущено: 1")
   - Table: Normalized PURL → Status → Repository URL
   - Button "Скачать обогащённый SBOM" → downloads enriched JSON
```

## Files to Create

```
src/purl_resolver/
├── sbom/
│   ├── __init__.py              — exports
│   ├── parser.py                — CycloneDX JSON parsing & validation
│   ├── collector.py             — recursive PURL collection + dedup
│   ├── enricher.py              — insert externalReferences into SBOM
│   └── reporter.py              — build result table data
├── templates/
│   └── sbom.html                — NEW: upload form + results table
├── router.py                    — add GET /sbom-updater, POST /api/v1/resolve/sbom
├── config.py                    — add SbomSettings (max_file_size)
└── main.py                      — no changes needed (router already included)
```

## Files to Modify

- `src/purl_resolver/router.py` — add new routes
- `src/purl_resolver/config.py` — add SbomSettings
- `templates/index.html` — add link to /sbom-updater
- `src/purl_resolver/templates/` — ensure directory exists, add sbom.html

## API Contract

### GET /sbom-updater

Returns HTML page with upload form.

### POST /api/v1/resolve/sbom

Request: `multipart/form-data` with field `file` containing CycloneDX JSON.

Response (success, 200):
```json
{
  "summary": {
    "total_purls": 10,
    "found": 8,
    "not_found": 2,
    "skipped": 0
  },
  "results": [
    {
      "purl": "pkg:pypi/certifi",
      "status": "found",
      "repository_url": "https://github.com/certifi/python-certifi"
    },
    {
      "purl": "pkg:pypi/altgraph",
      "status": "not_found",
      "repository_url": null
    }
  ],
  "enriched_sbom": { ... }
}
```

Response (error, 400): `{"error": "invalid_sbom", "message": "..."}`

Response (error, 413): `{"error": "file_too_large", "message": "..."}`

## Test Files

Существующие тестовые файлы в `.misc/addictional_materials/`:
- `sbom_example_correct.json` — ожидается, что у `altgraph` reference уже есть, не будет изменён
- `sbom_example_missed_references.json` — у `altgraph` нет externalReferences → ожидается добавление; у `autoflake` есть некорректная ссылка → будет добавлена VCS

## Dependencies

- Никаких новых внешних зависимостей. CycloneDX парсится напрямую (это обычный JSON).
- Переиспользуется `purl_utils`, `service.resolve_purl()`, `storage`, `resolvers`.

## Testing Strategy

- Unit tests для `sbom/parser.py`, `collector.py`, `enricher.py`, `reporter.py`
- Integration test с реальным SBOM-файлом через TestClient
- Проверка, что файл > 200 MB отклоняется
- Проверка, что невалидный JSON отклоняется
- Проверка, что пропущенные компоненты не ломают обработку

## Future Scope

- LLM-резолвер для PURL, которые purl2repo не находит
- Асинхронная обработка больших файлов (background task)
