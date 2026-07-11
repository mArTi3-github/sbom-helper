# PURL Source Repository Resolver

Веб-приложение и API-сервис для сопоставления Package URL (PURL) с репозиторием исходного кода.

## Language

**PURL**:
Package URL — стандартизированная строка, идентифицирующая программный пакет (напр. `pkg:pypi/requests@2.31.0`).
_Avoid_: Package URL целиком, purl-строка

**Primary Resolver**:
Библиотека `purl2repo`, которая преобразует PURL в repository URL, confidence, evidence и repository_kind. Основной резолвер, первый в цепочке резолверов (Resolver Chain).

**Fallback Resolver**:
Резолверы, вызываемые после Primary Resolver, если он не нашёл repository URL. Включают EcosystemsResolver (ecosyste.ms, fallback #1, включён по умолчанию) и LibrariesIoResolver (libraries.io, fallback #2, опционально, требует API key). Резолверы опрашиваются последовательно; первый успешный возвращает результат.

**Repository URL**:
Ссылка на VCS-репозиторий с исходным кодом (напр. `https://github.com/psf/requests`).
_Avoid_: Source URL, download URL, tarball URL

**Download URL**:
Ссылка на архив/тарбол с исходным кодом (напр. `https://registry.npmjs.org/express/-/express-4.17.1.tgz`).
_Avoid_: Repository URL, VCS URL

**Resolution**:
Процесс сопоставления PURL с repository URL.

**Invalid PURL Error**:
HTTP 400 — переданная строка не является валидным PURL или экосистема не поддерживается.

**Unresolved PURL**:
HTTP 200, `repository_url: null` — PURL валиден, но репозиторий не найден.

**Upstream Error**:
HTTP 502 — внутренняя ошибка purl2repo (сетевой таймаут, недоступность registry API).

**Storage Layer**:
Модуль `storage/`, отвечающий за персистентное хранение результатов резолвинга. Абстрагирован за протоколом (`interface.py`) с реализациями `PostgresCache` и `InMemoryCache`.

**Service Layer**:
Модуль `service.py`, реализующий оркестрацию: валидация PURL → нормализация → lookup в БД → вызов резолверов → сохранение результата. Изолирует business logic от HTTP-слоя.

**DB Cache Hit**:
Сценарий, при котором результат резолвинга PURL найден в PostgreSQL. Резолвер не вызывается.

**DB Cache Miss**:
Сценарий, при котором результат не найден в PostgreSQL. Резолвер вызывается, и при успехе результат сохраняется в БД.

**Normalized PURL**:
PURL, приведённый к минимальной форме `scheme:type/namespace/name` (namespace включается только если он присутствует в исходном PURL). Используется как ключ для кеширования и поиска в БД. Все опциональные компоненты (version, qualifiers, subpath) отбрасываются.

**PurlValidationLayer**:
Модуль `purl_utils/`, отвечающий за парсинг, валидацию и нормализацию PURL перед передачей резолверам. Использует библиотеку `packageurl-python`. Не зависит от какого-либо конкретного резолвера.

**PurlValidationError**:
Исключение, выбрасываемое `purl_utils` при невалидном PURL. Отличается от `InvalidPurlError` (определён в `resolver/interface.py`, выбрасывается резолверами) — это resolver-agnostic ошибка валидации на уровне приложения. Приводит к HTTP 400.

**PurlComponents**:
Структура данных, представляющая разобранный PURL на составные части: scheme, type, namespace, name, version, qualifiers, subpath.

**Safe Normalize**:
Функция `safe_normalize(purl) → str` в `purl_utils`. Оборачивает `validate()` + `normalize()` с обработкой исключений — при ошибке парсинга возвращает оригинальный PURL как есть. Устраняет дублирование логики нормализации в различных модулях.

**SBOM Module**:
Группа модулей `sbom/`, реализующих обработку CycloneDX SBOM: `parser.py` (валидация JSON-формата), `collector.py` (рекурсивный обход компонентов и выявление нуждающихся в обогащении), `enricher.py` (вставка VCS-ссылок в `externalReferences`), `remover.py` (удаление неразрешимых компонентов из SBOM), `reporter.py` (построение отчёта о результатах). Модуль импортирует `purl_utils` для нормализации PURL; не зависит от Storage или Resolver напрямую.

**SBOM Enrichment**:
Процесс обогащения CycloneDX SBOM-файла. Принимает на вход JSON-файл, находит компоненты без VCS/source-distribution ссылок в `externalReferences`, резолвит их PURL через существующий Service Layer, вставляет найденные ссылки и возвращает обогащённый SBOM вместе с отчётом (summary + results table).

**Batch Resolution**:
Функция `resolve_batch(purls, storage, resolvers) → dict` в Service Layer. Параллельно резолвит список PURL через `asyncio.gather()` с ограничением конкурентности (semaphore=10). Возвращает словарь `normalized_purl → ResolveResponse` только для успешных резолвингов.

**EcosystemsResolver**:
Резолвер, использующий API `packages.ecosyste.ms` для поиска repository URL по PURL. Включён по умолчанию в настройках. Первый fallback-резолвер в цепочке. Возвращает `confidence: "medium"`.

**LibrariesIoResolver**:
Резолвер, использующий API `libraries.io` для поиска repository URL по PURL. Опциональный, требует API key в настройках. Второй fallback-резолвер в цепочке. Возвращает `confidence: "medium"`.

**Resolver Chain**:
Цепочка резолверов, реализованная в `resolver/factory.py`: `Purl2RepoResolver → EcosystemsResolver → LibrariesIoResolver`. Резолверы вызываются последовательно (через `for r in resolvers` в `service.py`). Первый резолвер, вернувший `repository_url`, считается успешным; остальные не вызываются.

**URL Validator**:
Модуль `url_validator.py`, реализующий валидацию repository URL с помощью HTTP HEAD-запроса и много-VCS проверки (`_check_vcs`: git → svn → hg → fossil). Используется сервисным слоем для проверки актуальности кешированных URL (настройка `validate_db_urls`).

**Check VCS / Multi-VCS Probe**:
Функция `_check_vcs(url, timeout, github_token=None) → bool | None` в `url_validator.py`. Последовательно проверяет, является ли URL git/svn/hg/fossil-репозиторием, с ранним выходом при первом успехе. Правило агрегации: `True` если хотя бы одна проба успешна; иначе `False` если хотя бы одна проба явно сказала "не репозиторий"; иначе `None` (все пробы неопределённые, например при таймаутах). Гарантирует, что валидные кешированные URL не удаляются из БД при временных сетевых ошибках.

**SbomRemover**:
Модуль `sbom/remover.py`, содержащий функцию `remove_unresolved_components()`. Удаляет из SBOM компоненты, для которых не удалось найти repository URL, за исключением компонентов, имеющих вложенные подкомпоненты (`has_subcomponents`). Вызывается из `SbomEnrichmentPipeline` в рамках опционального флага `remove_unresolved`.

**SbomEnrichmentPipeline**:
Класс-оркестратор в `sbom_enrichment.py`, управляющий полным циклом обогащения SBOM: парсинг → сбор компонентов → сохранение pre-existing references → batch-резолвинг → удаление неразрешённых (опционально) → enrichment → отчёт. Инкапсулирует взаимодействие между `sbom/*`, `service.py` и `storage`.

## Frontend (Vue 3 SPA)

**SPA Architecture**:
Фронтенд реализован как Single-Page Application на Vue 3 + Vite + TypeScript. Размещается в `frontend/`. FastAPI раздаёт статику через `SPAStaticFiles` (кастомный подкласс `StaticFiles` с fallback на `index.html` для клиентского роутинга), монтируется в `main.py` после всех API-роутов. Vue Router (`createWebHistory()`) обрабатывает клиентский роутинг для 5 страниц: PURL Resolver (`/`), SBOM Updater (`/sbom-updater`), Database Admin (`/db-admin`), Settings (`/settings`), Images List Converter (`/images-list-converter`). Catch-all маршрут (`/:pathMatch(.*)*`) отображает `NotFound.vue`. API-запросы направляются на существующие бэкендовые эндпоинты. Каждый `.vue`-компонент использует `<style scoped>` для изоляции стилей; глобальные CSS-переменные в `src/assets/main.css`.

**SbomUpdater**:
Страница обогащения CycloneDX SBOM. Использует `FileUploadZone` для загрузки файла, чекбоксы для опций, редактор паттернов игнорирования, `POST /api/v1/resolve/sbom` для обработки. Отображает сводку (total/found/not_found/skipped/removed/ignored) и таблицу результатов.

**DatabaseAdmin**:
Страница управления таблицей `resolved_purls`. Поддерживает фильтрацию (поиск, резолвер, confidence, даты), сортировку по колонкам, инлайн-редактирование, одиночное/массовое удаление, CSV-импорт (с выбором стратегии upsert/skip_existing) и CSV-экспорт. Пагинация реализована через композабл `usePagination`. Все колонки отображаются по умолчанию без чекбоксов видимости.

**API Client**:
Типизированный HTTP-клиент в `frontend/src/api/`. Модули: `client.ts` (базовая fetch-обёртка с `ApiError`), `purl.ts`, `sbom.ts`, `db.ts`, `settings.ts`, `images.ts`. Все ответы типизированы через интерфейсы в `types/api.ts`, зеркалирующие `schemas.py`.

**Pinia**:
Не используется. Состояние на уровне компонентов (`ref`, `reactive`) достаточно для текущего набора страниц.