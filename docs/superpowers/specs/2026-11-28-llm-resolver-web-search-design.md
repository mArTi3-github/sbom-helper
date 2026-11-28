# LLM-резолвер: реальный веб-поиск через SearXNG (tool-calling)

## Intent / Зачем

Сейчас LLM-резолвер не выполняет поиск в вебе: `SYSTEM_PROMPT` просит модель
«использовать web-search и web-fetch», но в запросе к LLM (`_request`,
`src/purl_resolver/resolver/llm.py:153-158`) не передаётся параметр `tools`,
никаких инструментов не определено. Модель отвечает только по своим тренировочным
данным, то есть фактически угадывает `repository_url`. Для long-tail пакетов, ради
которых LLM-резолвер и добавлен последним в цепочке, это критически ненадёжно.

Нужно, чтобы llm-resolver реально искал в вебе: модель решает, что искать, а
sbom-helper исполняет поисковые запросы и загрузку страниц со своего хоста и
возвращает результаты модели до получения финального JSON.

## Goals / Non-goals / Anti-goals

**Goals**
- Добавить в `LlmResolver` цикл tool-calling: передавать модели инструменты
  `web_search` и `web_fetch`, исполнять `tool_calls` на стороне sbom-helper и
  подставлять результаты обратно, пока модель не вернёт финальный JSON.
- Поиск выполняется локально развёрнутым **SearXNG**, который поставляется вместе с
  sbom-helper как отдельный compose-сервис (вариант A) и доступен только во
  внутренней compose-сети.
- `web_fetch` делает исходящий запрос на URL, который вернула модель, поэтому:
  только схемы `http/https`, блокировка приватных диапазонов по IP, лимит размера
  ответа и таймаут.
- Число раундов инструментов ограничено (`llm_resolver_max_tool_rounds`), чтобы
  исключить зацикливание.

**Non-goals**
- Утечка/неприменимость API-ключа ecosyste.ms в query-параметре и DEBUG-логах —
  это отдельный дефект, разбирается отдельной задачей (не входит в этот дизайн).
- Изменение порядка резолверов в цепочке и контракта `Resolution`/API-контрактов
  резолва.
- Доверие к корпоративному CA / TLS-настройки LLM-клиента — уже реализовано
  (см. `2026-11-28-llm-resolver-tls-trust-design.md`).
- Поддержка прокси для исходящего поиска (в целевых сетях внешний поиск доступен
  напрямую).
- Публикация SearXNG наружу / отдельная авторизация к нему.
- Защита от prompt-injection через содержимое загружаемых страниц (`web_fetch`):
  вне области этой задачи; опираемся на промпт и финальную валидацию (формат + HEAD).
  Кандидат в отдельную задачу.
- Изменение TLS-проверки существующей `_check_url` (она использует LLM-настройки
  `verify`): это предсуществующее поведение, не трогаем.

**Anti-goals**
- Не делать так, чтобы недоступность SearXNG ломала резолв: при ошибке инструмента
  модель получает текст ошибки, а при полном провале поиска должна вернуть `failure`,
  а не выдумывать URL. SearXNG считается runtime-предпосылкой компоуз-развёртывания
  (поднимается вместе с проектом); при запуске без компоуза (`.venv`) поиск
  недоступен, и резолвер деградирует до ответов модели по памяти.
- Не выставлять SearXNG-порт на хост.
- Не ломать существующие тесты и поведение, когда llm-resolver выключен.
- Не логировать содержимое поисковых запросов как секреты (это не секреты, но и не
  засорять логи по умолчанию — на уровне DEBUG/INFO, как сейчас).

## Constraints

- `openai>=1.0.0`, `httpx>=0.27.0`; стиль проекта: `from __future__ import
  annotations`, строки ≤ 100 символов (`ruff`), аннотации типов.
- LLM-деплой — OpenAI-совместимый (positive-llm / vLLM, модель «Deepseek V4 Flash»),
  tool-calling подтверждён рабочим. Точный формат `tools`/`tool_calls` — стандартный
  OpenAI Chat Completions.
- `Resolution` (`resolver/interface.py`) содержит только `purl`, `repository_url`,
  `warnings` — менять его не нужно.
- `build_resolvers(settings, app_settings)` вызывается в `main.py:71` и
  `routes/settings.py:68` — оба места должны получать URL SearXNG.

## Approaches

Рассматривались варианты исполнения поиска (кто именно ходит в интернет):

1. **Локальный SearXNG + tool-calling, инструменты исполняет sbom-helper — выбрано.**
   Модель только решает, что искать; запросы уходят с хоста sbom-helper в локальный
   SearXNG, который сам агрегирует внешние поисковики. Полный контроль, без внешних
   ключей, изоляция во внутренней сети.
2. **Hosted web-search инструмент на стороне LLM-сервера.** Не подходит: поиск шёл
   бы с хоста LLM-деплоя, а не sbom-helper, что противоречит требованию.
3. **Прямой вызов внешнего поискового API (Tavily/Brave/…) из sbom-helper.**
   Отклонено: внешний ключ/деньги и риск блокировки в корпоративной сети; SearXNG
   даёт то же без ключа и с полным контролем движков.

Варианты размещения SearXNG рассмотрены отдельно; выбран **отдельный compose-сервис**
(официальный образ `searxng/searxng`) по образцу существующего сервиса `db`, а не
вшивание в образ sbom-helper (SearXNG — самостоятельный сервис со своим конфигом и
рантаймом).

## Как устроено (решённые решения)

### 1. SearXNG как compose-сервис

`docker-compose.yml` — новый сервис:

```yaml
  searxng:
    image: searxng/searxng:latest
    container_name: sbom-searxng
    volumes:
      - ./searxng:/etc/searxng:rw
    environment:
      - SEARXNG_BASE_URL=http://searxng:8080/
      - SEARXNG_SECRET=${SEARXNG_SECRET:?set SEARXNG_SECRET in .env}
    restart: unless-stopped
    # порт наружу НЕ публикуется
```

- `app` получает `depends_on: searxng` (condition `service_started`) и переменную
  окружения `SEARXNG_URL=http://searxng:8080`.
- Добавить `SEARXNG_SECRET` и `SEARXNG_URL` в `.env.example` с комментариями
  (как генерировать секрет: `openssl rand -hex 32`).

`searxng/settings.yml` (маунтится в `/etc/searxng/settings.yml`):

```yaml
use_default_settings: true
server:
  limiter: false
  image_proxy: true
  bind_address: "0.0.0.0"
search:
  formats:
    - html
    - json
```

- `search.formats` с `json` обязателен: по умолчанию SearXNG отдаёт только `html`.
- `server.limiter: false` — иначе JSON-API начнёт отдавать 429 при частых запросах
  от одного IP.
- Движки — дефолтный набор SearXNG (duckduckgo/bing/brave/wikipedia и т.д.),
  доступ к ним прямой, без прокси.

### 2. Tool-calling в `LlmResolver`

`src/purl_resolver/resolver/llm.py`.

Инструменты (стандартная OpenAI-схема; имена `web_search`/`web_fetch` — snake_case
для надёжности парсинга в vLLM):

```python
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web. Returns top results (title, url, snippet).",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": "Fetch a web page and return its visible text.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
        },
    },
]
```

`SYSTEM_PROMPT` приводится в соответствие: вместо абстрактных «web-search и
web-fetch» — прямое указание вызывать `web_search`, а при неоднозначности проверять
кандидата через `web_fetch`, затем вернуть финальный JSON в прежнем формате.

`resolve()` сохраняет прежнюю структуру (валидация PURL → попытки `attempts_count` →
валидация ответа → HEAD-проверка URL), но вместо одиночного `_request` вызывается
`_run_with_tools(messages)`:

```python
async def _run_with_tools(self, messages) -> tuple[str | None, str | None]:
    for _ in range(self._max_tool_rounds + 1):
        completion = await self._client.chat.completions.create(
            model=self._model, messages=messages, tools=TOOLS,
        )
        msg = completion.choices[0].message
        if not getattr(msg, "tool_calls", None):
            return msg.content, None
        messages.append(msg)
        for call in msg.tool_calls:
            result = await self._execute_tool(call)
            messages.append(
                {"role": "tool", "tool_call_id": call.id, "content": result}
            )
    return None, "exceeded max tool rounds"
```

- `_execute_tool(call)` разбирает `call.function.name`/`arguments` (JSON) и
  диспетчеризует в `_web_search(query)` / `_web_fetch(url)`.
- Ошибки сети/парсинга инструмента не бросаются наружу, а возвращаются строкой-
  результатом для модели (graceful degradation).
- Ошибки самого LLM-запроса (`APIError`, `httpx.HTTPError`) обрабатываются как
  сейчас: причина попадает в `warnings` и приводит к следующей попытке.
- История `messages` (включая assistant/tool-сообщения) живёт в пределах вызова
  `resolve`; сбрасывать её между попытками или накапливать — на усмотрение
  строителя (попыток мало, по умолчанию 2).
- Исчерпание `max_tool_rounds` — **терминальный** исход для этого PURL: `resolve`
  больше не делает новых попыток (иначе худший случай `attempts_count ×
  (max_tool_rounds + 1)` LLM-вызовов, до 44 при максимальных настройках). Внешние
  попытки `attempts_count` остаются для провалов валидации ответа и HEAD-проверки.

`_web_search(query)`:
- `GET {searxng_url}/search` с `params={"q": query, "format": "json"}`, таймаут
  поиска (по умолчанию 15 с).
- Из `results` берётся до 5 записей, форматируются в текст: `title` / `url` /
  `content` (сниппет).
- Возвращается строка (в т.ч. «no results» при пустом списке).

`_web_fetch(url)`:
- Проверка схемы: только `http/https` (иначе — текстовая ошибка).
- Отдельный HTTP-клиент `self._fetch_client` (`httpx.AsyncClient` с **дефолтной**
  проверкой TLS `verify=True`, т.е. `certifi`), НЕ общий `self._http_client`:
  настройки `llm_resolver_verify_ssl`/`llm_resolver_ca_bundle` относятся к доверию
  LLM-эндпоинту и не должны распространяться на произвольные внешние страницы.
- Редиректы обрабатываются вручную (`follow_redirects=False`) с лимитом переходов
  (например, 3): на **каждом** хопе схема и IP проверяются заново. Иначе публичный
  URL мог бы редиректнуть на приватный адрес и обойти блокировку.
- Для каждой проверяемой цели: резолв хоста (`socket.getaddrinfo`) и проверка
  **всех** полученных IP через `ipaddress` — запрет, если IP
  `is_private/is_loopback/is_link_local/is_reserved/is_multicast/is_unspecified`.
- `GET` на каждый хоп с отдельным таймаутом и лимитом размера тела (~512 КБ);
  чтение с обрывом при превышении.
- HTML → видимый текст через stdlib `html.parser` (без новой зависимости),
  нормализация пробелов, обрезка результата перед возвратом модели.
- Любая ошибка (в т.ч. редирект на запрещённую цель, превышение хопов/размера) →
  текстовая строка-результат, не исключение.

Существующая `_check_url` (HEAD финального `repository_url`) сохраняется без
изменений как финальная проверка.

### 3. Конфигурация

`src/purl_resolver/config.py` — новый класс (по образцу `StorageSettings`):

```python
class SearxngSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SEARXNG_", env_file=".env",
                                     env_file_encoding="utf-8")
    url: str = "http://searxng:8080"

searxng_settings = SearxngSettings()
```

`build_resolvers(settings, app_settings, searxng_url)` — новый параметр;
`main.py:71` и `routes/settings.py:68` передают `searxng_settings.url`.
`LlmResolver.__init__` получает `searxng_url: str = "http://searxng:8080"` и
`max_tool_rounds: int = 3`.

`src/purl_resolver/settings_store.py` — `AppSettings`:
```python
llm_resolver_max_tool_rounds: int = Field(default=3, ge=1, le=10)
```

`src/purl_resolver/routes/settings.py` — `SettingsUpdate` + `GET`/`PATCH
/api/v1/settings`: добавить `llm_resolver_max_tool_rounds` (валидация 1..10).

`src/purl_resolver/resolver/factory.py` — проброс `searxng_url` и
`max_tool_rounds` в `LlmResolver`.

### 4. Frontend

- `frontend/src/types/api.ts`: в `SettingsResponse`/`SettingsUpdate` —
  `llm_resolver_max_tool_rounds: number`.
- `frontend/src/stores/useSettingsStore.ts`: ref `llmMaxToolRounds` (default `3`),
  загрузка/сохранение по образцу прочих полей LLM.
- `frontend/src/views/Settings.vue`: в карточке LLM-резолвера — числовое поле
  «Максимум раундов поиска (1–10)»; автосохранение.
- i18n `frontend/src/i18n/locales/{en,ru}.json`: ключи для нового поля.

### 5. Тесты

- `tests/test_llm_resolver.py`:
  - цикл tool-calling: мок `create` возвращает `tool_calls` (assistant), затем
    финальный JSON; проверить, что между ними вызывается `_execute_tool` и в
    `messages` добавляются `tool`-сообщения;
  - превышение `max_tool_rounds` → `Resolution` без URL и warning;
  - `web_search`: мок httpx → формирование текста из `results`, топ-5;
  - `web_fetch`: мок httpx → извлечение текста из HTML; запрет `file://`/`ftp://`;
    блокировка приватного IP (monkeypatch `socket.getaddrinfo`, e.g. `127.0.0.1`,
    `10.0.0.1`, `169.254.1.1`); редирект на приватный адрес блокируется на хопе;
    используется отдельный `self._fetch_client` с дефолтной проверкой TLS
    (не `self._http_client`);
  - `tools` реально передаётся в `create` (проверка kwargs) при включённом поиске.
- `tests/test_settings_store.py`: дефолт и roundtrip `llm_resolver_max_tool_rounds`.
- `tests/test_api.py`: `GET` отдаёт поле; `PATCH` обновляет; в фабрике `LlmResolver`
  получает `searxng_url` и `max_tool_rounds`.
- `frontend` тесты: обновить `defaultSettings`, добавить проверку отрисовки и
  автосохранения нового поля.
- Опционально e2e (под `SKIP_E2E`): при поднятом SearXNG — `web_search` по реальному
  запросу возвращает результаты.

### 6. Документация и спецификации (отдельный шаг после кода)

- `README.md` — раздел про разворачивание: SearXNG-сервис, `SEARXNG_SECRET`,
  `SEARXNG_URL`, назначение `llm_resolver_max_tool_rounds`.
- `specs/domains/purl-resolution.md`, `specs/architecture/layers.md` — описать
  tool-calling и SearXNG в слое резолверов.
- `specs/decisions/0008-llm-as-last-resort-resolver.md` — обновить Consequences
  (реальный веб-поиск через локальный SearXNG).

## Что остаётся строителю

- Точные имена инструментов (`web_search`/`web_fetch` рекомендованы) и формулировки
  `SYSTEM_PROMPT`.
- Формат текста, который `web_search`/`web_fetch` возвращают модели; конкретные
  лимиты (5 результатов, 512 КБ, таймауты) — можно скорректировать.
- Где хранить `messages` между попытками и как обрезать историю инструментов.
- Конкретный способ резолва/пиннинга IP при `web_fetch` (защита от DNS-rebinding —
  опциональное усиление сверх обязательной блокировки приватных диапазонов).
- Нужен ли `image_proxy`/какие движки оставить в `settings.yml`.

## Definition of Done

- `SKIP_E2E=1 .venv/bin/python -m pytest -q` зелёный; `ruff check` без новых
  замечаний.
- `npm --prefix frontend run test` и `npm --prefix frontend run build` проходят.
- `docker compose up` поднимает `app`, `db`, `searxng`; `app` ходит на
  `http://searxng:8080`.
- При включённом llm-resolver модель получает `tools`, вызывает `web_search`
  (видно в логах/запросах к SearXNG) и возвращает финальный JSON.
- `web_fetch` отклоняет не-http(s), приватные IP и редиректы на приватные адреса;
  использует отдельный клиент с дефолтной проверкой TLS.
- При выключенном llm-resolver поведение и тесты не меняются.
