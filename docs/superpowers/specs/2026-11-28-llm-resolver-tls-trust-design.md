# LLM-резолвер: настраиваемое доверие к TLS (корпоративный CA)

## Intent / Зачем

LLM-резолвер sbom-helper (OpenAI-совместимый клиент) не работает при подключении к
корпоративной LLM, чей сертификат выдан внутренним УЦ: `httpx`/`openai` используют бандл
`certifi`, в котором нет корневого сертификата внутреннего CA. В логах — `ConnectError:
CERTIFICATE_VERIFY_FAILED ... self-signed certificate in certificate chain`. Нужно дать
пользователю настраиваемое управление проверкой TLS для исходящих запросов LLM-резолвера:
либо указать PEM-файл корпоративного CA, либо (как временная мера) полностью отключить
проверку сертификата.

## Goals / Non-goals / Anti-goals

**Goals**
- Возможность указать путь к PEM-файлу CA (`llm_resolver_ca_bundle`), которому доверяет
  LLM-клиент при проверке TLS.
- Возможность полностью отключить проверку TLS (`llm_resolver_verify_ssl = false`) — режим,
  явно запрошенный пользователем, так как подстановка корпоративного сертификата может быть
  затруднительна.
- Настройки задаются в UI «Настройки», сохраняются в `data/settings.json` и применяются без
  перезапуска контейнера (через `PATCH /api/v1/settings` → `_rebuild_resolvers`).

**Non-goals**
- Утечка API-ключей в DEBUG-логах `httpx`/`httpcore`/`openai` — вынесено в отдельную задачу.
- Доверие к корпоративному CA для других резолверов (purl2repo, deps.dev, ecosyste.ms,
  libraries.io) — меняем только LLM-резолвер.
- HTTPS самого сервиса (uvicorn/самоподписанный сертификат) — это другой, уже решённый вопрос.

**Anti-goals**
- Не хранить PEM-файл внутри контейнера/репозитория: задаётся путь, файл монтируется
  (например, через `data/`).
- Не логировать API-ключи.
- Сломанная настройка (несуществующий файл CA) не должна ломать всю цепочку резолверов.

## Constraints

- `openai==3.3.1`, `httpx==0.28.1`. У `AsyncOpenAI` нет параметра `verify` — TLS настраивается
  только через `http_client=httpx.AsyncClient(...)`.
- Стиль проекта: `from __future__ import annotations`, строки ≤ 100 символов (ruff),
  аннотации типов.
- Нейминг следует существующему префиксу `llm_resolver_*` в `AppSettings`.

## Approaches

1. **`ca_bundle` (путь) + `verify_ssl` (bool) — выбрано.** Два независимых поля в
   `AppSettings`/`SettingsUpdate`/UI. `LlmResolver` строит `ssl.SSLContext` один раз и передаёт
   его в оба http-клиента (`openai` и HEAD-проверка URL). Минимум новых сущностей, консистентно
   с остальными настройками LLM-резолвера.
2. **Только `verify_ssl=false`, без CA-бандла.** Проще, но не решает задачу безопасно и не
   даёт пользователю возможность доверять конкретному CA. Отклонено.
3. **Глобальная настройка CA для всех исходящих запросов сервиса.** Шире, чем нужно, и
   затрагивает поведение всех резолверов. Отклонено (non-goal).

## Как устроено (решённые решения)

### Backend

`src/purl_resolver/settings_store.py` — `AppSettings`:
- `llm_resolver_verify_ssl: bool = True`
- `llm_resolver_ca_bundle: str | None = None`

`src/purl_resolver/routes/settings.py`:
- `SettingsUpdate` + `GET`/`PATCH /api/v1/settings`: новые поля
  `llm_resolver_verify_ssl` и `llm_resolver_ca_bundle`. В `GET` `llm_resolver_ca_bundle`
  отдаётся как есть (не секрет), `llm_resolver_api_key` по-прежнему только через `token_set`.

`src/purl_resolver/resolver/llm.py` — `LlmResolver.__init__` получает `verify_ssl: bool = True`,
`ca_bundle: str | None = None`. Строит `verify: bool | ssl.SSLContext` в хелпере
`_build_ssl_verify`:
- `ca_bundle` задан (непустой): `ssl.create_default_context(cafile=ca_bundle)`; при `OSError`
  (файл не существует/невалиден) — `logger.warning` и откат к дефолтной проверке (`True`).
- `verify_ssl is False`: контекст без проверки (`check_hostname=False`,
  `verify_mode=ssl.CERT_NONE`) + `logger.warning` о том, что проверка TLS отключена.
- иначе: `True` (дефолт `certifi`).

Оба клиента создаются с одним `verify`:
- `AsyncOpenAI(base_url=..., api_key=..., timeout=..., max_retries=0,
  http_client=httpx.AsyncClient(verify=verify, timeout=timeout, follow_redirects=True))`
  (`max_retries=0`, чтобы ретраи управлялись только `llm_resolver_attempts_count`).
- `self._http_client = httpx.AsyncClient(verify=verify, timeout=timeout, follow_redirects=True)`
  (HEAD-проверка URL).

`_request` возвращает причину ошибки: при `except (APIError, httpx.HTTPError)` логируется и
попадает в `warnings` текст `type(exc).__name__: exc` (чтобы в логах/результате была видна
SSL-причина, а не «Connection error»). В `resolve` при `content is None` причина подставляется
в `_record_failure`.

`src/purl_resolver/resolver/factory.py` — проброс `verify_ssl`/`ca_bundle` из `AppSettings`.

### Frontend

- `frontend/src/types/api.ts`: в `SettingsResponse` — `llm_resolver_verify_ssl: boolean`,
  `llm_resolver_ca_bundle: string | null`; в `SettingsUpdate` — опциональные те же поля.
- `frontend/src/stores/useSettingsStore.ts`: ref `llmVerifySsl` (default `true`) и
  `llmCaBundle` (default `''`); загрузка/сохранение по образцу существующих полей LLM.
- `frontend/src/views/Settings.vue`: в карточке LLM-резолвера — чекбокс
  «Проверять TLS-сертификат» и текстовое поле «Путь к CA-бандлу (PEM)» (disabled при
  `!llmEnabled || !llmVerifySsl`); автосохранение через `debouncedAutoSave`
  (`llm_resolver_ca_bundle: llmCaBundle || null`).
- i18n `frontend/src/i18n/locales/{en,ru}.json`: ключи `settings.llmResolver.verifySsl`,
  `verifySslDesc`, `caBundle`, `caBundleDesc`.

### Тесты

- `tests/test_llm_resolver.py`: при заданном `ca_bundle` — SSL-контекст загружает этот файл;
  при `verify_ssl=False` — `verify_mode == ssl.CERT_NONE`; дефолт без изменений (существующие
  тесты проходят). Проверка через `resolver._ssl_verify` / хелпер `_build_ssl_verify`; для
  `max_retries=0` — мок `AsyncOpenAI` с проверкой kwargs.
- `tests/test_settings_store.py`: дефолты и roundtrip новых полей.
- `tests/test_api.py`: `GET` отдаёт новые поля; `PATCH` обновляет их; в
  `TestResolverChainRebuild` — `LlmResolver` в фабрике получает `verify_ssl`/`ca_bundle`.
- `frontend/src/views/Settings.test.ts`: `defaultSettings` дополнены; тест отрисовки и
  автосохранения новых контролов.

### Документация и спецификации (отдельный шаг после кода)

- `README.md` (раздел Settings) — новые параметры + сценарий «внутренняя LLM за корпоративным
  CA» (рекомендуется `llm_resolver_ca_bundle`, `verify_ssl=false` — временная мера).
- `specs/decisions/0008-llm-as-last-resort-resolver.md` — обновить Decision/Consequences.

## Что остаётся строителю

- Точная форма SSL-хелпера и хранение результата (рекомендуется `self._ssl_verify`) — на
  усмотрение.
- Сообщения в лог и i18n-тексты — формулировки.

## Definition of Done

- `SKIP_E2E=1 .venv/bin/python -m pytest -q` зелёный.
- `ruff check` без новых замечаний.
- `npm --prefix frontend run test` и `npm --prefix frontend run build` проходят.
- В UI можно задать CA-бандл и отключить проверку TLS; значения сохраняются в
  `data/settings.json` и применяются через `PATCH` без перезапуска.
