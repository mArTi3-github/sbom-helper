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
Модуль `service.py`, реализующий оркестрацию: lookup в БД → вызов резолверов → сохранение результата. Изолирует business logic от HTTP-слоя.

**DB Cache Hit**:
Сценарий, при котором результат резолвинга PURL найден в PostgreSQL. Резолвер не вызывается.

**DB Cache Miss**:
Сценарий, при котором результат не найден в PostgreSQL. Резолвер вызывается, и при успехе результат сохраняется в БД.