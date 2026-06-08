# Implementation Plan: Async Resolver Translation

**Spec:** `docs/superpowers/specs/2026-06-08-async-resolver-design.md`

## Overview

Перевод Resolver interface и всех реализаций в async для устранения блокировки event loop при параллельных HTTP-запросах.

## Tasks

### Task 1: Update Resolver Interface to Async

**Files:**
- `src/purl_resolver/resolver/interface.py` (modify)
- `tests/test_resolver_interface.py` (modify)

**Steps:**
1. Изменить `Resolver.resolve()` на `async def resolve()` в `interface.py`
2. Обновить `DummyResolver` в `test_resolver_interface.py` — сделать `async def resolve()`
3. Запустить тесты: `.venv/bin/pytest tests/test_resolver_interface.py -v`
4. Commit: `refactor: make Resolver.resolve() async`

---

### Task 2: Update Purl2RepoResolver to Async

**Files:**
- `src/purl_resolver/resolver/purl2repo.py` (modify)
- `tests/test_purl2repo_resolver.py` (modify)

**Steps:**
1. Добавить `import asyncio` в `purl2repo.py`
2. Изменить `resolve()` на `async def resolve()`
3. Обернуть `purl2repo_resolve()` в `asyncio.to_thread()`
4. Обновить тесты в `test_purl2repo_resolver.py`:
   - Добавить `@pytest.mark.asyncio` ко всем тестам
   - Сделать тесты async: `async def test_...`
   - Добавить `await` к вызовам `resolver.resolve()`
5. Запустить тесты: `.venv/bin/pytest tests/test_purl2repo_resolver.py -v`
6. Commit: `refactor: make Purl2RepoResolver async with asyncio.to_thread`

---

### Task 3: Update EcosystemsResolver to Async

**Files:**
- `src/purl_resolver/resolver/ecosystems.py` (modify)
- `tests/test_ecosystems_resolver.py` (modify)

**Steps:**
1. Изменить `httpx.Client` на `httpx.AsyncClient` в `__init__()`
2. Изменить `resolve()` на `async def resolve()`
3. Добавить `await` к `self._client.get()`
4. Обновить тесты в `test_ecosystems_resolver.py`:
   - Заменить `MagicMock(spec=httpx.Client)` на `AsyncMock(spec=httpx.AsyncClient)`
   - Добавить `@pytest.mark.asyncio` ко всем тестам
   - Сделать тесты async и добавить `await` к вызовам `r.resolve()`
5. Запустить тесты: `.venv/bin/pytest tests/test_ecosystems_resolver.py -v`
6. Commit: `refactor: make EcosystemsResolver async with httpx.AsyncClient`

---

### Task 4: Update LibrariesIoResolver to Async

**Files:**
- `src/purl_resolver/resolver/librariesio.py` (modify)
- `tests/test_librariesio_resolver.py` (modify)

**Steps:**
1. Добавить `import asyncio` в `librariesio.py`
2. Изменить `httpx.Client` на `httpx.AsyncClient` в `__init__()`
3. Изменить `resolve()` на `async def resolve()`
4. Изменить `_rate_limit_wait()` на `async def _rate_limit_wait()`
5. Заменить `time.sleep()` на `await asyncio.sleep()` в `_rate_limit_wait()`
6. Добавить `await` к `self._client.get()` и `self._rate_limit_wait()`
7. Обновить тесты в `test_librariesio_resolver.py`:
   - Заменить `MagicMock(spec=httpx.Client)` на `AsyncMock(spec=httpx.AsyncClient)`
   - Добавить `@pytest.mark.asyncio` ко всем тестам
   - Сделать тесты async и добавить `await` к вызовам `r.resolve()`
   - Для `TestRateLimiting.test_minimum_interval_between_requests` использовать `await` и `asyncio.sleep()` если нужно
8. Запустить тесты: `.venv/bin/pytest tests/test_librariesio_resolver.py -v`
9. Commit: `refactor: make LibrariesIoResolver async with asyncio.sleep for rate limiting`

---

### Task 5: Update Service Layer to Await Resolvers

**Files:**
- `src/purl_resolver/service.py` (modify)
- `tests/helpers.py` (modify)
- `tests/test_storage.py` (modify)
- `tests/test_resolve_batch.py` (modify)
- `tests/test_service_validation.py` (modify)

**Steps:**
1. В `service.py` изменить `resolution = r.resolve(purl)` на `resolution = await r.resolve(purl)` (строка 108)
2. В `helpers.py` изменить `FakeResolver.resolve()` на `async def resolve()`
3. В `test_service_validation.py`:
   - Изменить `resolver.resolve = MagicMock(...)` на `resolver.resolve = AsyncMock(...)` (строка 43)
   - Обновить `resolver.resolve.assert_called_once()` если нужно (для AsyncMock работает так же)
4. Запустить все сервисные тесты: `.venv/bin/pytest tests/test_storage.py tests/test_resolve_batch.py tests/test_service_validation.py -v`
5. Commit: `refactor: update service layer to await async resolvers`

---

### Task 6: Update Integration Tests

**Files:**
- `tests/test_api.py` (modify if needed)
- `tests/test_sbom_integration.py` (modify if needed)
- `tests/test_main.py` (modify if needed)

**Steps:**
1. Проверить что `FakeResolver` используется корректно (уже async после Task 5)
2. Запустить API тесты: `.venv/bin/pytest tests/test_api.py -v`
3. Запустить SBOM интеграционные тесты: `.venv/bin/pytest tests/test_sbom_integration.py -v`
4. Запустить main тесты: `.venv/bin/pytest tests/test_main.py -v`
5. Исправить любые ошибки
6. Commit: `test: update integration tests for async resolvers`

---

### Task 7: Run Full Test Suite and Verify

**Files:**
- None (verification only)

**Steps:**
1. Запустить все тесты: `.venv/bin/pytest tests/ -v`
2. Исправить любые оставшиеся ошибки
3. Проверить что все тесты проходят
4. Commit: `test: verify all tests pass with async resolvers`

---

### Task 8: Manual Verification of Parallel Requests

**Files:**
- None (manual testing)

**Steps:**
1. Запустить приложение: `.venv/bin/python -m purl_resolver.main`
2. В одном браузере загрузить большой SBOM файл
3. В другой вкладке открыть Settings или DB Admin
4. Убедиться что параллельные запросы обрабатываются без задержек
5. Задокументировать результаты в commit message или PR description

---

### Task 9: Update Documentation

**Files:**
- `specs/architecture/layers.md` (modify)
- `specs/domains/purl-resolution.md` (modify)
- `docs/adr/` (create new ADR if needed)

**Steps:**
1. Обновить `specs/architecture/layers.md`:
   - Указать что `Resolver.resolve()` теперь async
   - Указать что ecosyste.ms и libraries.io используют `httpx.AsyncClient`
2. Обновить `specs/domains/purl-resolution.md`:
   - Указать что resolver chain теперь полностью async
3. Создать ADR-0006 если нужно (опционально):
   - Описать решение использовать async для resolvers
   - Объяснить trade-offs
4. Commit: `docs: update specs for async resolver architecture`

---

## Success Criteria

- [ ] Все существующие тесты проходят
- [ ] Event loop не блокируется во время HTTP-запросов resolvers
- [ ] Rate limiting для libraries.io (1 req/sec) работает корректно
- [ ] Rate limit tracking в url_validator.py работает корректно
- [ ] Параллельные запросы (SBOM + Settings + DB Admin) обрабатываются одновременно
- [ ] Нет регрессии в SBOM enrichment функциональности

## Notes

- Использовать `.venv/bin/pytest` для запуска тестов (не системный Python)
- Все тесты должны быть async где вызывают async функции
- `AsyncMock` из `unittest.mock` для мокирования async методов
- `@pytest.mark.asyncio` для всех async тестов
