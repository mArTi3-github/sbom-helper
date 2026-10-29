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
   - Для `TestRateLimiting.test_minimum_interval_between_requests` использовать `await`
8. Запустить тесты: `.venv/bin/pytest tests/test_librariesio_resolver.py -v`
9. Commit: `refactor: make LibrariesIoResolver async with asyncio.sleep for rate limiting`

---

### Task 5: Update Service Layer to Await Resolvers

**Files:**
- `src/purl_resolver/service.py` (modify)
- `tests/helpers.py` (modify)
- `tests/test_storage.py` (modify if needed)
- `tests/test_resolve_batch.py` (modify if needed)
- `tests/test_service_validation.py` (modify)

**Steps:**
1. В `service.py` изменить `resolution = r.resolve(purl)` на `resolution = await r.resolve(purl)`
2. В `helpers.py` изменить `FakeResolver.resolve()` на `async def resolve()`
3. В `test_service_validation.py`:
   - Изменить `resolver.resolve = MagicMock(...)` на `resolver.resolve = AsyncMock(...)`
4. Запустить все сервисные тесты: `.venv/bin/pytest tests/test_storage.py tests/test_resolve_batch.py tests/test_service_validation.py -v`
5. Commit: `refactor: update service layer to await async resolvers`

---

### Task 6: Update Integration Tests

**Files:**
- `tests/test_api.py` (verify)
- `tests/test_sbom_integration.py` (verify)
- `tests/test_main.py` (verify)

**Steps:**
1. Запустить API тесты: `.venv/bin/pytest tests/test_api.py -v`
2. Запустить SBOM интеграционные тесты: `.venv/bin/pytest tests/test_sbom_integration.py -v`
3. Запустить main тесты: `.venv/bin/pytest tests/test_main.py -v`
4. Исправить любые ошибки
5. Commit: `test: update integration tests for async resolvers`

---

### Task 7: Run Full Test Suite and Verify

**Files:** None (verification only)

**Steps:**
1. Запустить все тесты: `.venv/bin/pytest tests/ -v`
2. Исправить любые оставшиеся ошибки
3. Commit: `test: verify all tests pass with async resolvers`

---

### Task 8: Manual Verification of Parallel Requests

**Files:** None (manual testing)

**Steps:**
1. Запустить приложение
2. В одном браузере загрузить большой SBOM файл
3. В другой вкладке открыть Settings или DB Admin
4. Убедиться что параллельные запросы обрабатываются без задержек

---

### Task 9: Update Documentation

**Files:**
- `specs/architecture/layers.md` (modify)
- `specs/domains/purl-resolution.md` (modify)

**Steps:**
1. Обновить `specs/architecture/layers.md` — указать что `Resolver.resolve()` теперь async
2. Обновить `specs/domains/purl-resolution.md` — указать что resolver chain полностью async
3. Commit: `docs: update specs for async resolver architecture`

---

## Success Criteria

- [ ] Все существующие тесты проходят
- [ ] Event loop не блокируется во время HTTP-запросов resolvers
- [ ] Rate limiting для libraries.io (1 req/sec) работает корректно
- [ ] Rate limit tracking в url_validator.py работает корректно
- [ ] Параллельные запросы обрабатываются одновременно
- [ ] Нет регрессии в SBOM enrichment функциональности

## Notes

- Использовать `.venv/bin/pytest` для запуска тестов
- `AsyncMock` из `unittest.mock` для мокирования async методов
- `@pytest.mark.asyncio` для всех async тестов