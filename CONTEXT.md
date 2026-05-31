# PURL Source Repository Resolver

Веб-приложение и API-сервис для сопоставления Package URL (PURL) с репозиторием исходного кода.

## Language

**PURL**:
Package URL — стандартизированная строка, идентифицирующая программный пакет (напр. `pkg:pypi/requests@2.31.0`).
_Avoid_: Package URL целиком, purl-строка

**Primary Resolver**:
Библиотека `purl2repo`, которая преобразует PURL в repository URL, confidence, evidence и repository_kind. Основной резолвер в MVP.

**Fallback Resolver**:
Библиотека `purl2src`, преобразующая PURL в download URL (тарбол/архив). Не входит в MVP; зарезервирована для будущего использования как резервный резолвер.

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
PURL, приведённый к минимальной форме `scheme:type/namespace/name` (namespace включается только если он присутствует в исходном PURL). Используется как ключ для кэширования и поиска в БД. Все опциональные компоненты (version, qualifiers, subpath) отбрасываются.

**PurlValidationLayer**:
Модуль `purl_utils/`, отвечающий за парсинг, валидацию и нормализацию PURL перед передачей резолверам. Использует библиотеку `packageurl-python`. Не зависит от какого-либо конкретного резолвера.

**PurlValidationError**:
Исключение, выбрасываемое `purl_utils` при невалидном PURL. Отличается от `InvalidPurlError` (который выбрасывается purl2repo) — это resolver-agnostic ошибка валидации на уровне приложения. Приводит к HTTP 400.

**PurlComponents**:
Структура данных, представляющая разобранный PURL на составные части: scheme, type, namespace, name, version, qualifiers, subpath.

**Safe Normalize**:
Функция `safe_normalize(purl) → str` в `purl_utils`. Оборачивает `validate()` + `normalize()` с обработкой исключений — при ошибке парсинга возвращает оригинальный PURL как есть. Устраняет дублирование логики нормализации в различных модулях.

**SBOM Module**:
Группа модулей `sbom/`, реализующих обработку CycloneDX SBOM: `parser.py` (валидация JSON-формата), `collector.py` (рекурсивный обход компонентов и выявление нуждающихся в обогащении), `enricher.py` (вставка VCS-ссылок в `externalReferences`), `reporter.py` (построение отчёта о результатах). Модуль импортирует `purl_utils` для нормализации PURL; не зависит от Storage или Resolver напрямую.

**SBOM Enrichment**:
Процесс обогащения CycloneDX SBOM-файла. Принимает на вход JSON-файл, находит компоненты без VCS/source-distribution ссылок в `externalReferences`, резолвит их PURL через существующий Service Layer, вставляет найденные ссылки и возвращает обогащённый SBOM вместе с отчётом (summary + results table).

**Batch Resolution**:
Функция `resolve_batch(purls, storage, resolvers) → dict` в Service Layer. Параллельно резолвит список PURL через `asyncio.gather()` с ограничением конкурентности (semaphore=10). Возвращает словарь `normalized_purl → repository_url` только для успешных резолвингов.