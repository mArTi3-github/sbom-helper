В проекте **sbom-helper** выявлены следующие значимые архитектурные недостатки (от наиболее критичных к менее):

---

### 🔴 Высокая серьезность

1. **Глобальное мутабельное состояние `_RateLimitTracker`** (`url_validator.py:82-108`)
   - Классовые переменные `_count` / `_cooldown_until` — глобальное состояние, не потокобезопасное.
   - Приводит к недетерминированным тестам; требуется `reset()` в фикстурах.
   - *Решение:* сделать инстансным, внедрять через параметры `validate_url()`.

2. **`PurlResolutionService` нарушает SRP** (`service.py:22-220`)
   - Отвечает за: валидацию URL, кэш, обход резолверов, построение ответов, storage, batch-резолв, pre-existing refs.
   - Метод `_validate_cached_url` (33-82) смешивает cooldown, URL validation, обновление репозитория, storage, ошибки.
   - *Решение:* разбить на несколько сервисов с одной ответственностью.

3. **Broad `except Exception` в множестве мест**
   - `purl_utils/__init__.py:51` — bare except, проглатывает все ошибки нормализации.
   - `url_validator.py:132,275-277,303-305,396-397,417-418` — return None при любом исключении в VCS-пробах.
   - `service.py:106,165` — silent suppression ошибок storage.
   - *Решение:* ловить конкретные исключения, логировать или пробрасывать.

---

### 🟡 Средняя серьезность

4. **Чтение JSON-файла настроек на каждый запрос** (`service.py:43,127`, `sbom_enrichment.py:77`)
   - 100-300 I/O операций на батч PURL (каждый вызов `settings_store.load()`).
   - *Решение:* добавить TTL-кэш в `SettingsStore`.

5. **`SbomEnrichmentPipeline` дублирует зависимости** (`sbom_enrichment.py:52-62`)
   - Конструктор принимает `storage`, `resolvers`, `settings_store` + `resolution_service`, хотя последний уже содержит всё первое.
   - *Решение:* оставить только `resolution_service`, получать всё через него.

6. **Дублирование валидации размера файла** (`routes/resolve.py:46-53`, `routes/images_list.py:19-29`)
   - Одинаковые проверки `max_file_size` в двух роутах.
   - *Решение:* вынести в общий хелпер/декоратор.

7. **Circular import в `_rebuild_resolvers()`** (`routes/settings.py:43-50`)
   - Late imports чтобы избежать циклической зависимости — индикатор грязного dependency flow.
   - *Решение:* вынести в отдельный `AppConfigService` или в `service.py`.

8. **`InMemoryCache` игнорирует date-фильтры** (`storage/inmemory.py:46-55`)
   - `_matches_filters()` не проверяет `date_from`/`date_to`, в отличие от Postgres-реализации.
   - *Решение:* добавить фильтрацию по датам.

---

### 🟢 Низкая серьезность

9. **I/O на уровне импорта модуля** (`main.py:84`)
   - `_find_spa_dir()` вызывается при import, а не в lifespan.
   - *Решение:* перенести в lifespan.

10. **Hardcoded operational values**
    - `_BATCH_SEMAPHORE_LIMIT = 10` (`service.py:19`)
    - API URL ecosyste.ms / libraries.io (вшиты в код).
    - Rate limit thresholds (`url_validator.py:21-22`).

11. **Dead code**: `ServiceTokens` dataclass (`settings_store.py:14-16`) — не используется нигде.

12. **`isinstance(str)` dead condition** (`storage/postgres.py:86-91`) — поля `evidence`/`warnings` уже `list[str]` по типам, проверка на str — мертвый код.

13. **Frontend: нет единого state management**, DatabaseAdmin.vue (964 строк, ~800 CSS), дублирование обработки ошибок в `client.ts`.

---

Полный список с файлами и строками — в результатах исследования. Если вы одобрите, я подготовлю пошаговый план рефакторинга с приоритетами.
