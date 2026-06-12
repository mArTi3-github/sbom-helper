# Unify DI Pattern: Service Layer → Class

## Executive Summary

Превратить `src/purl_resolver/service.py` из набора свободных функций (parameter bag anti-pattern) в класс с constructor injection. Это устраняет несовместимость трёх DI-подходов в проекте и приводит service layer к единому паттерну, уже используемому `SbomEnrichmentPipeline` и `DbAdminService`.

---

## Problem

В проекте одновременно используются три несовместимых DI-подхода:

| Где | Паттерн | Пример |
|-----|---------|--------|
| `main.py` | Service Locator | `app.state.storage`, `app.state.resolvers`, `app.state.settings_store` |
| `service.py` | Parameter Bag | `resolve_purl(storage, resolvers, settings_store, resolver)` — все зависимости передаются в каждый вызов |
| `sbom_enrichment.py` | Constructor Injection | `SbomEnrichmentPipeline(storage, resolvers, settings_store)` — зависимости declared once |

**Ключевые проблемы:**

1. **`resolve_batch()` — pass-through anti-pattern**: ре-пассирует все 5 параметров без изменений, просто пробрасывая их в `resolve_purl()`:

   ```python
   async def resolve_batch(purls, storage, resolvers, settings_store=None, resolver=""):
       ...
       result = await resolve_purl(original, storage, resolvers,
                                    settings_store=settings_store, resolver=resolver)
   ```

2. **Route handlers извлекают зависимости из `app.state` и передают их в каждую функцию**:

   ```python
   # routes/resolve.py
   result = await resolve_purl(
       purl=body.purl,
       storage=request.app.state.storage,
       resolvers=request.app.state.resolvers,
       settings_store=request.app.state.settings_store,
   )
   ```

3. **Несовместимость с `SbomEnrichmentPipeline`**: enrichment pipeline использует constructor injection, а service layer — parameter bag. Это затрудняет рефакторинг и увеличивает когнитивную нагрузку.

---

## Solution

### 1. Превратить `service.py` в класс `PurlResolutionService`

```python
class PurlResolutionService:
    def __init__(
        self,
        storage: Storage,
        resolvers: list[Resolver],
        settings_store: SettingsStore | None = None,
    ) -> None:
        self._storage = storage
        self._resolvers = resolvers
        self._settings_store = settings_store

    async def resolve_purl(self, purl: str, resolver: str = "") -> ResolveResult: ...
    async def resolve_batch(self, purls: list[str], resolver: str = "") -> dict[str, ResolveResponse]: ...
    async def store_preexisting_references(self, components: list[SbomComponent], resolver: str = "") -> None: ...
```

### 2. Обновить Composition Root (`main.py`)

```python
from .service import PurlResolutionService

# В lifespan:
app.state.resolution_service = PurlResolutionService(
    storage=app.state.storage,
    resolvers=app.state.resolvers,
    settings_store=app.state.settings_store,
)
```

### 3. Обновить route handlers

```python
# routes/resolve.py — было
result = await resolve_purl(
    purl=body.purl,
    storage=request.app.state.storage,
    resolvers=request.app.state.resolvers,
    settings_store=request.app.state.settings_store,
)

# routes/resolve.py — стало
result = await request.app.state.resolution_service.resolve_purl(purl=body.purl)
```

---

## Affected Files

### Source files (8)

| File | Change |
|------|--------|
| `src/purl_resolver/service.py` | Free functions → `PurlResolutionService` class |
| `src/purl_resolver/routes/resolve.py` | `resolve_purl(...)` → `resolution_service.resolve_purl(...)` |
| `src/purl_resolver/sbom_enrichment.py` | `resolve_batch(...)` → `resolution_service.resolve_batch(...)` и `store_preexisting_references(...)` → `resolution_service.store_preexisting_references(...)` |
| `src/purl_resolver/main.py` | Добавить `PurlResolutionService(storage, resolvers, settings_store)` в lifespan |

### Test files (5)

| File | Количество call sites |
|------|-----------------------|
| `tests/test_storage.py` | 10 вызовов `resolve_purl()` |
| `tests/test_service_validation.py` | 13 вызовов `resolve_purl()`, 12 вызовов `_validate_cached_url()` |
| `tests/test_resolve_batch.py` | 6 вызовов `resolve_batch()` |
| `tests/test_sbom_integration.py` | 2 вызова `resolve_batch()`, 1 вызов `store_preexisting_references()` |
| `tests/test_db_admin.py` | 1 вызов `resolve_batch()`, 1 вызов `store_preexisting_references()` |
| `tests/test_librariesio_integration.py` | 3 вызова `resolve_purl()` |

---

## Implementation Plan

### Step 1: Service Layer — класс (service.py)

1. Создать класс `PurlResolutionService` с constructor injection:
   ```python
   def __init__(self, storage, resolvers, settings_store=None)
   ```
2. Перенести `_validate_cached_url()` как private method.
3. Перенести `resolve_purl()` как public method — убрать параметры `storage`, `resolvers`, `settings_store` (берутся из `self`).
4. Перенести `resolve_batch()` — убрать те же параметры.
5. Перенести `store_preexisting_references()` — убрать `storage`.
6. Сохранить свободные функции как **bridge-обёртки** для обратной совместимости (см. Compatibility Strategy ниже).

### Step 2: Composition Root (main.py)

1. Импортировать `PurlResolutionService`.
2. В `lifespan`, после создания storage/resolvers/settings_store:
   ```python
   app.state.resolution_service = PurlResolutionService(
       storage=app.state.storage,
       resolvers=app.state.resolvers,
       settings_store=app.state.settings_store,
   )
   ```
3. Удалить bridge-обёртки после того, как все call sites переведены.

### Step 3: Route handlers (routes/resolve.py)

1. Заменить вызов `resolve_purl(purl, storage, resolvers, settings_store)` на `request.app.state.resolution_service.resolve_purl(purl)`.

### Step 4: SBOM Enrichment Pipeline (sbom_enrichment.py)

1. Добавить `resolution_service: PurlResolutionService` в constructor injection (рядом с существующими `storage`, `resolvers`, `settings_store`).
2. Заменить вызовы `resolve_batch(purls, storage, resolvers, settings_store=..., resolver=...)` на `self._resolution_service.resolve_batch(purls, resolver=...)`.
3. Заменить вызов `store_preexisting_references(components, storage, resolver=...)` на `self._resolution_service.store_preexisting_references(components, resolver=...)`.

### Step 5: Tests

Обновить все test files (см. таблицу Affected Files):
- Заменить `resolve_purl(purl, storage, resolvers, ...)` на `PurlResolutionService(storage, resolvers, ...).resolve_purl(purl, ...)`
- Аналогично для `resolve_batch` и `store_preexisting_references`

### Step 6: Cleanup

1. Удалить bridge-обёртки (свободные функции) из `service.py`.
2. Заменить оставшиеся импорты свободных функций на импорт класса.

---

## Compatibility Strategy

На время переходного периода свободные функции остаются как bridge-обёртки:

```python
# service.py
async def resolve_purl(purl, storage, resolvers, settings_store=None, resolver=""):
    svc = PurlResolutionService(storage, resolvers, settings_store)
    return await svc.resolve_purl(purl, resolver=resolver)
```

Это позволяет тестам и call sites обновляться итеративно, без "big bang" коммита.

---

## Callsite Catalog

### Current call sites for `resolve_purl()`

```
routes/resolve.py:28     — resolve_purl(body.purl, storage, resolvers, settings_store)
tests/test_storage.py:77      — resolve_purl("pkg:...", storage, [resolver])
tests/test_storage.py:97      — resolve_purl("pkg:...", storage, [resolver])
tests/test_storage.py:119     — resolve_purl("pkg:...", storage, [resolver])
tests/test_storage.py:153     — resolve_purl("pkg:...", broken_storage, [resolver])
tests/test_storage.py:181     — resolve_purl("pkg:...", broken_storage, [resolver])
tests/test_storage.py:198     — resolve_purl("pkg:...", storage, [resolver])
tests/test_storage.py:212     — resolve_purl("not-a-purl", storage, [resolver])
tests/test_storage.py:225     — resolve_purl("pkg:...", storage, [resolver])
tests/test_storage.py:242     — resolve_purl("pkg:...", storage, [resolver_a, resolver_b])
tests/test_storage.py:264     — resolve_purl("pkg:...", storage, [resolver_a, resolver_b])
tests/test_service_validation.py:26    — resolve_purl("pkg:...", mock_storage, [resolver], mock_settings_store)
tests/test_service_validation.py:37    — resolve_purl("pkg:...", mock_storage, [resolver], settings_store=None)
tests/test_service_validation.py:91    — resolve_purl("pkg:...", mock_storage, [], settings_store=mock_settings_store)
tests/test_service_validation.py:103   — resolve_purl("pkg:...", mock_storage, [resolver], settings_store=mock_settings_store)
tests/test_service_validation.py:114   — resolve_purl("pkg:...", mock_storage, [], settings_store=mock_settings_store)
tests/test_service_validation.py:126   — resolve_purl("pkg:...", mock_storage, [], settings_store=mock_settings_store)
tests/test_service_validation.py:139   — resolve_purl("pkg:...", mock_storage, [], settings_store=settings_store)
tests/test_service_validation.py:154   — resolve_purl("pkg:...", mock_storage, [], settings_store=mock_settings_store)
tests/test_service_validation.py:164   — resolve_purl("pkg:requests", mock_storage, [])
tests/test_service_validation.py:180   — resolve_purl("pkg:...", storage=storage, resolvers=[], settings_store=settings_store)
tests/test_service_validation.py:498   — resolve_purl("pkg:...", mock_storage, [first, second], mock_settings_store)
tests/test_service_validation.py:525   — resolve_purl("pkg:...", mock_storage, [resolver], mock_settings_store)
tests/test_service_validation.py:549   — resolve_purl("pkg:...", mock_storage, [resolver], mock_settings_store)
tests/test_service_validation.py:575   — resolve_purl("pkg:...", mock_storage, [resolver], mock_settings_store)
tests/test_service_validation.py:601   — resolve_purl("pkg:...", mock_storage, [resolver], settings_store)
tests/test_librariesio_integration.py:42  — resolve_purl(...)
tests/test_librariesio_integration.py:71  — resolve_purl(...)
tests/test_librariesio_integration.py:100 — resolve_purl(...)
```

### Current call sites for `resolve_batch()`

```
sbom_enrichment.py:119 — resolve_batch(unique_purls, self._storage, self._resolvers, settings_store=..., resolver=...)
tests/test_resolve_batch.py:34  — resolve_batch(purls, storage, [resolver])
tests/test_resolve_batch.py:48  — resolve_batch(purls, storage, [resolver])
tests/test_resolve_batch.py:60  — resolve_batch(purls, storage, [resolver])
tests/test_resolve_batch.py:67  — resolve_batch([], storage, [resolver])
tests/test_resolve_batch.py:80  — resolve_batch(purls, storage, [resolver])
tests/test_resolve_batch.py:95  — resolve_batch(purls, storage, [resolver])
tests/test_sbom_integration.py:401 — resolve_batch([...], storage_with_file_url, fake_empty_resolvers, settings_store=...)
tests/test_db_admin.py:368 — resolve_batch(purls_to_resolve, storage, [resolver])
```

### Current call sites for `store_preexisting_references()`

```
sbom_enrichment.py:126 — store_preexisting_references(components, self._storage, resolver=...)
tests/test_db_admin.py:369 — store_preexisting_references(components, storage)
```

---

## Risk Assessment

| Фактор | Оценка | Комментарий |
|--------|--------|-------------|
| **Risk** | **Moderate** | Меняет вызывающий код во всех routes, sbom_enrichment.py и тестах |
| **Effort** | **~2-3 hours** | 8 source files + 5 test files |
| **Behavioural change** | None | Чистый рефакторинг, логика не меняется |
| **Testing** | Bridge layer позволяет итеративное обновление |
| **Rollback** | Bridge-обёртки обеспечивают мгновенный rollback — старый API продолжает работать |

### Митигация рисков

1. **Bridge-слой**: свободные функции остаются как обёртки до полного перевода всех call sites.
2. **Пошаговый подход**: каждый шаг изолирован и тестируется отдельно.
3. **Тесты**: после каждого шага — `pytest tests/ -x`.

---

## Testing Strategy

1. Bridge-обёртки гарантируют, что старые тесты продолжают работать немедленно после Step 1.
2. После Steps 2-4 (обновление call sites) — тесты перестают использовать bridge.
3. После Step 5 (cleanup bridge) — все тесты используют только `PurlResolutionService`.
4. Запуск полного набора тестов после каждого шага: `.venv/bin/pytest tests/ -x --tb=short`.

---

## Dependencies

- Рефакторинг `service.py` не зависит от других изменений в проекте.
- `DbAdminService` (уже реализован) — независим, не затрагивается.
- `validate_url_with_retry()` (уже реализована) — вызывается изнутри `PurlResolutionService`, не требует изменений.
- `SOURCE_REF_TYPES` (уже переименован) — не затрагивается.

