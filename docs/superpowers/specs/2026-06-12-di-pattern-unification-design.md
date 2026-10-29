# DI Pattern Unification: Service Layer → Class

## Problem

В проекте одновременно используются три несовместимых DI-подхода:

| Где | Паттерн | Пример |
|---|---|---|
| `main.py` | Service Locator | `app.state.storage`, `app.state.resolvers`, `app.state.settings_store` |
| `service.py` | Parameter Bag | `resolve_purl(storage, resolvers, settings_store, resolver)` — все зависимости передаются в каждый вызов |
| `sbom_enrichment.py` | Constructor Injection | `SbomEnrichmentPipeline(storage, resolvers, settings_store)` — зависимости declared once |

**Ключевые проблемы:**

1. **`resolve_batch()` — pass-through anti-pattern**: ре-пассирует все 5 параметров без изменений, просто пробрасывая их в `resolve_purl()`:

   ```python
   async def resolve_batch(purls, storage, resolvers, settings_store=None, resolver=""):
       result = await resolve_purl(original, storage, resolvers, settings_store=settings_store, resolver=resolver)
   ```

2. **Route handlers извлекают зависимости из `app.state` и передают их в каждую функцию**:

   ```python
   result = await resolve_purl(
       purl=body.purl,
       storage=request.app.state.storage,
       resolvers=request.app.state.resolvers,
       settings_store=request.app.state.settings_store,
   )
   ```

3. **Несовместимость с `SbomEnrichmentPipeline`**: enrichment pipeline использует constructor injection, а service layer — parameter bag.

## Scope

- Только `src/purl_resolver/service.py` — превращается в класс `PurlResolutionService`
- `SbomEnrichmentPipeline` получает `PurlResolutionService` через constructor injection вместо прямых вызовов свободных функций
- Route handlers обращаются к `request.app.state.resolution_service` вместо ручного сбора зависимостей
- Тесты обновляются с bridge-слоем на переходный период
- Никакой поведенческой логики не меняется — чистый рефакторинг

## Design

### 1. `PurlResolutionService` Class

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

Параметры `storage`, `resolvers`, `settings_store` убраны из сигнатур всех трёх public-методов — берутся из `self`.

`_validate_cached_url()` остаётся private static method (доступен через `self`), его сигнатура не меняется.

### 2. Composition Root (main.py)

```python
from .service import PurlResolutionService

# В lifespan, после инициализации зависимостей:
app.state.resolution_service = PurlResolutionService(
    storage=app.state.storage,
    resolvers=app.state.resolvers,
    settings_store=app.state.settings_store,
)
```

### 3. Route handlers (routes/resolve.py)

```python
# Было
result = await resolve_purl(purl=body.purl, storage=..., resolvers=..., settings_store=...)

# Стало
result = await request.app.state.resolution_service.resolve_purl(purl=body.purl)
```

### 4. SbomEnrichmentPipeline

Добавляется `resolution_service: PurlResolutionService` в constructor injection:

```python
class SbomEnrichmentPipeline:
    def __init__(
        self,
        storage: Storage,
        resolvers: list[Resolver],
        settings_store: SettingsStore | None = None,
        resolution_service: PurlResolutionService | None = None,
    ) -> None:
        ...
        self._resolution_service = resolution_service
```

Вызовы в `process()`:

```python
# Было
resolved = await resolve_batch(unique_purls, self._storage, self._resolvers, settings_store=..., resolver=...)
await store_preexisting_references(components, self._storage, resolver=...)

# Стало
resolved = await self._resolution_service.resolve_batch(unique_purls, resolver=...)
await self._resolution_service.store_preexisting_references(components, resolver=...)
```

### 5. Bridge-слой (переходный период)

Свободные функции остаются как bridge-обёртки до полного перевода всех call sites:

```python
async def resolve_purl(purl, storage, resolvers, settings_store=None, resolver=""):
    svc = PurlResolutionService(storage, resolvers, settings_store)
    return await svc.resolve_purl(purl, resolver=resolver)
```

Это позволяет тестам и call sites обновляться итеративно, без "big bang" коммита.

### 6. Тесты

- Тесты используют bridge-обёртки на первом этапе (гарантирует работоспособность)
- После перевода всех call sites — bridge удаляется
- В тестах инстанцируется `PurlResolutionService(mock_storage, [mock_resolver])` напрямую
- Рекомендуется добавить pytest-фикстуру `resolution_service` для сокращения boilerplate

## Data Flow

```
HTTP Request
  └─ Route handler (routes/resolve.py)
       └─ request.app.state.resolution_service.resolve_purl(purl)
            ├─ validate(purl)
            ├─ storage.lookup(purl_key)
            │    ├─ cache hit → _validate_cached_url → возврат
            │    └─ cache miss → resolver chain → storage.store → возврат
            └─ return ResolveResult

SBOM Enrichment
  └─ SbomEnrichmentPipeline.process(sbom_data)
       ├─ collect_components
       ├─ self._resolution_service.resolve_batch(purls)
       ├─ self._resolution_service.store_preexisting_references(components)
       └─ enrich + report
```

## Bridge Cleanup Order

1. Step 1: `service.py` → класс + bridge-обёртки
2. Step 2: `main.py` → создание `PurlResolutionService` в lifespan
3. Step 3: `routes/resolve.py` → вызов через `resolution_service`
4. Step 4: `sbom_enrichment.py` → constructor injection + вызовы через `_resolution_service`
5. Step 5: Тесты → обновление call sites
6. Step 6: bridge-обёртки удалены

## Affected Files

### Source files

| File | Change |
|---|---|
| `src/purl_resolver/service.py` | Free functions → `PurlResolutionService` class + bridge |
| `src/purl_resolver/routes/resolve.py` | `resolve_purl(...)` → `resolution_service.resolve_purl(...)` |
| `src/purl_resolver/sbom_enrichment.py` | Constructor + delegates to `_resolution_service` |
| `src/purl_resolver/main.py` | Add `PurlResolutionService(storage, resolvers, settings_store)` in lifespan |

### Test files

| File | Call sites |
|---|---|
| `tests/test_storage.py` | 10 calls `resolve_purl()` |
| `tests/test_service_validation.py` | 13 calls `resolve_purl()`, 12 calls `_validate_cached_url()` |
| `tests/test_resolve_batch.py` | 6 calls `resolve_batch()` |
| `tests/test_sbom_integration.py` | 2 `resolve_batch()`, 1 `store_preexisting_references()` |
| `tests/test_db_admin.py` | 1 `resolve_batch()`, 1 `store_preexisting_references()` |
| `tests/test_librariesio_integration.py` | 3 calls `resolve_purl()` |

### Spec files

| File | Change |
|---|---|
| `specs/architecture/layers.md` | Update Service Layer section — `PurlResolutionService` class |
| `specs/domains/purl-resolution.md` | Update service layer description |

## Risk Assessment

| Фактор | Оценка |
|---|---|
| **Risk** | Moderate — меняет вызывающий код в routes, sbom_enrichment.py и тестах |
| **Effort** | ~2-3 hours — 8 source + 5 test files |
| **Behavioural change** | None — чистый рефакторинг |
| **Testing** | Bridge-слой обеспечивает итеративное обновление |
| **Rollback** | Bridge-обёртки обеспечивают мгновенный rollback |