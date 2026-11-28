# LLM-резолвер: веб-поиск через SearXNG — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Дать llm-resolver реальный веб-поиск: модель вызывает инструменты `web_search`/`web_fetch`, sbom-helper исполняет их (поиск через локальный SearXNG, загрузка страниц) и возвращает результаты модели до финального JSON.

**Architecture:** SearXNG поднимается отдельным compose-сервисом. В `LlmResolver` добавляется цикл tool-calling поверх OpenAI Chat Completions (`tools` → `tool_calls` → результаты → повтор), два инструмента (поиск по SearXNG JSON API и безопасная загрузка страницы с блокировкой приватных IP), плюс настройки `SEARXNG_URL` (env) и `llm_resolver_max_tool_rounds` (AppSettings/UI).

**Tech Stack:** Python 3.12, FastAPI, `openai` AsyncOpenAI, `httpx`, stdlib `html.parser`/`ipaddress`/`socket`, Vue 3 + Pinia (frontend), Docker Compose, SearXNG (`searxng/searxng`).

**Spec:** `docs/superpowers/specs/2026-11-28-llm-resolver-web-search-design.md`

## Global Constraints

- Стиль: `from __future__ import annotations`, строки ≤ 100 символов (`ruff`), аннотации типов.
- Tool-calling **безусловный**: SearXNG — обязательная предпосылка компоуз-развёртывания.
- `web_fetch`: только `http/https`; блокировка приватных диапазонов по IP на **каждом** хопе; `follow_redirects=False`; лимит размера и таймаут.
- `web_fetch` использует отдельный клиент с `verify=True` (certifi), НЕ LLM-настройки TLS.
- Исчерпание `llm_resolver_max_tool_rounds` — терминально для PURL (без новых попыток).
- Значения по умолчанию: `SEARXNG_URL=http://searxng:8080`, `llm_resolver_max_tool_rounds=3`, топ-5 результатов, тело fetch ≤ 512 KB, таймаут fetch/search 15 c.
- Контракт `Resolution` (`purl`, `repository_url`, `warnings`) не меняется; порядок резолверов не меняется.
- `_check_url` (HEAD финального URL) и его TLS-настройки не трогаем.

## Review Focus

- `web_fetch` при редиректе на приватный/внутренний адрес: должно быть заблокировано на хопе, а не только на входном URL.
- `web_fetch` при цепочке/цикле редиректов и огромном/бинарном теле: должен завершаться ошибкой/обрезкой, не зависать и не падать.
- `_execute_tool` при битом JSON в аргументах инструмента: возвращает строку-ошибку, не исключение.
- SearXNG недоступен / отдал не-JSON / пусто: инструмент возвращает строку-ошибку, резолв деградирует, не падает.
- Исчерпание `max_tool_rounds`: терминально, без `attempts_count × (rounds+1)` вызовов.

---

### Task 1: Конфиг `SearxngSettings` + SearXNG в compose

**Files:**
- Create: `searxng/settings.yml`
- Modify: `docker-compose.yml`
- Modify: `.env.example`
- Modify: `src/purl_resolver/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces:
  - `class SearxngSettings(BaseSettings)` с полем `url: str = "http://searxng:8080"`, `model_config` с `env_prefix="SEARXNG_"`.
  - Модульный синглтон `searxng_settings = SearxngSettings()` в `config.py`.
  - Сервис `searxng` в compose, доступный как `http://searxng:8080`.

- [ ] **Step 1: Написать падающий тест**

```python
# tests/test_config.py
from purl_resolver.config import SearxngSettings


def test_searxng_default_url() -> None:
    assert SearxngSettings().url == "http://searxng:8080"


def test_searxng_env_override(monkeypatch) -> None:
    monkeypatch.setenv("SEARXNG_URL", "http://custom:9999")
    assert SearxngSettings().url == "http://custom:9999"
```

- [ ] **Step 2: Прогнать, убедиться что падает**

Run: `.venv/bin/python -m pytest tests/test_config.py -q`
Expected: FAIL — `ImportError: cannot import name 'SearxngSettings'`.

- [ ] **Step 3: Добавить класс в `config.py`**

После `StorageSettings` добавить:

```python
class SearxngSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SEARXNG_",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    url: str = "http://searxng:8080"


searxng_settings = SearxngSettings()
```

- [ ] **Step 4: Прогнать тест**

Run: `.venv/bin/python -m pytest tests/test_config.py -q`
Expected: PASS.

- [ ] **Step 5: Создать `searxng/settings.yml`**

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

- [ ] **Step 6: Добавить сервис в `docker-compose.yml`**

В `services` добавить сервис и связать с `app`:

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
```

В сервисе `app` добавить `searxng: { condition: service_started }` в `depends_on` и переменную `- SEARXNG_URL=${SEARXNG_URL:-http://searxng:8080}` в `environment`.

- [ ] **Step 7: Обновить `.env.example`**

Добавить строки с комментариями:

```bash
# SearXNG (внутренний веб-поиск для LLM-резолвера)
# Секрет генерируется один раз: openssl rand -hex 32
SEARXNG_SECRET=
SEARXNG_URL=http://searxng:8080
```

- [ ] **Step 8: Проверить конфиг compose**

Run: `docker compose config >/dev/null && echo OK`
Expected: `OK` (или, если docker недоступен, пропустить и отметить в отчёте).

- [ ] **Step 9: Commit**

```bash
git add searxng/settings.yml docker-compose.yml .env.example src/purl_resolver/config.py tests/test_config.py
git commit -m "feat: add SearXNG compose service and SearxngSettings"
```

---

### Task 2: Инструменты `web_search`/`web_fetch` в `LlmResolver`

**Files:**
- Modify: `src/purl_resolver/resolver/llm.py`
- Test: `tests/test_llm_resolver_tools.py` (create)

**Interfaces:**
- Consumes: `Resolution`, `httpx`.
- Produces (в `LlmResolver`):
  - `__init__(..., searxng_url: str = "http://searxng:8080", max_tool_rounds: int = 3)` — сохраняет `self._searxng_url`, `self._max_tool_rounds` и создаёт `self._fetch_client = httpx.AsyncClient(verify=True, timeout=_FETCH_TIMEOUT, follow_redirects=False)`.
  - `async def _web_search(self, query: str) -> str`
  - `async def _web_fetch(self, url: str) -> str`
  - `async def _resolves_to_forbidden(self, hostname: str) -> bool`
- Модульные хелперы: `_is_forbidden_ip(ip: str) -> bool`, `_html_to_text(html: str) -> str`.
- Константы модуля: `_SEARCH_TIMEOUT = 15.0`, `_FETCH_TIMEOUT = 15.0`, `_FETCH_MAX_BYTES = 512 * 1024`, `_FETCH_MAX_TEXT = 8000`, `_MAX_REDIRECTS = 3`, `_TOP_K_RESULTS = 5`.

- [ ] **Step 1: Написать падающие тесты**

```python
# tests/test_llm_resolver_tools.py
import httpx
import pytest
from purl_resolver.resolver.llm import LlmResolver, _html_to_text, _is_forbidden_ip


def make_resolver() -> LlmResolver:
    return LlmResolver(base_url="https://api.example.com", api_key="k", model="m")


def test_forbidden_ips() -> None:
    assert _is_forbidden_ip("127.0.0.1") is True
    assert _is_forbidden_ip("10.1.2.3") is True
    assert _is_forbidden_ip("169.254.1.1") is True
    assert _is_forbidden_ip("192.168.0.1") is True
    assert _is_forbidden_ip("93.184.216.34") is False


def test_html_to_text_strips_tags_and_scripts() -> None:
    html = "<html><head><style>x{}</style></head><body><script>bad()</script><p>Hello  world</p></body></html>"
    assert _html_to_text(html) == "Hello world"


@pytest.mark.asyncio
async def test_web_search_formats_results(monkeypatch) -> None:
    resolver = make_resolver()
    payload = {"results": [
        {"title": "T1", "url": "https://a/1", "content": "S1"},
        {"title": "T2", "url": "https://a/2", "content": "S2"},
    ]}
    response = httpx.Response(200, json=payload)
    resolver._fetch_client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: response))
    out = await resolver._web_search("requests")
    assert "T1" in out and "https://a/1" in out and "S1" in out


@pytest.mark.asyncio
async def test_web_search_error_returns_string() -> None:
    resolver = make_resolver()
    resolver._fetch_client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(500))
    )
    out = await resolver._web_search("x")
    assert out.startswith("error:")


@pytest.mark.asyncio
async def test_web_fetch_blocks_private_ip(monkeypatch) -> None:
    resolver = make_resolver()
    monkeypatch.setattr(
        "purl_resolver.resolver.llm.socket.getaddrinfo",
        lambda *a, **k: [(2, 1, 6, "", ("127.0.0.1", 0))],
    )
    out = await resolver._web_fetch("http://internal.example/")
    assert out.startswith("error:")


@pytest.mark.asyncio
async def test_web_fetch_rejects_non_http_scheme() -> None:
    resolver = make_resolver()
    out = await resolver._web_fetch("file:///etc/passwd")
    assert out.startswith("error:")


@pytest.mark.asyncio
async def test_web_search_empty_results() -> None:
    resolver = make_resolver()
    response = httpx.Response(200, json={"results": []})
    resolver._fetch_client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: response))
    assert await resolver._web_search("x") == "no results"


@pytest.mark.asyncio
async def test_web_search_non_json_returns_error() -> None:
    resolver = make_resolver()
    response = httpx.Response(200, text="not json")
    resolver._fetch_client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: response))
    assert (await resolver._web_search("x")).startswith("error:")


@pytest.mark.asyncio
async def test_web_fetch_too_many_redirects(monkeypatch) -> None:
    resolver = make_resolver()
    monkeypatch.setattr(
        "purl_resolver.resolver.llm.socket.getaddrinfo",
        lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 0))],
    )
    resolver._fetch_client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(302, headers={"location": "https://public.example/next"})
        )
    )
    out = await resolver._web_fetch("https://public.example/")
    assert out == "error: too many redirects"


@pytest.mark.asyncio
async def test_web_fetch_large_body_truncated(monkeypatch) -> None:
    resolver = make_resolver()
    monkeypatch.setattr(
        "purl_resolver.resolver.llm.socket.getaddrinfo",
        lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 0))],
    )
    big = "a" * (1024 * 1024)
    resolver._fetch_client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, text=big))
    )
    out = await resolver._web_fetch("https://public.example/")
    assert len(out) <= 8000


@pytest.mark.asyncio
async def test_web_fetch_blocks_redirect_to_private(monkeypatch) -> None:
    resolver = make_resolver()

    def fake_getaddrinfo(host, *a, **k):
        return [(2, 1, 6, "", ("127.0.0.1" if host == "evil.internal" else "93.184.216.34", 0))]

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://public.example/"
        return httpx.Response(302, headers={"location": "http://evil.internal/"})

    monkeypatch.setattr("purl_resolver.resolver.llm.socket.getaddrinfo", fake_getaddrinfo)
    resolver._fetch_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    out = await resolver._web_fetch("https://public.example/")
    assert out.startswith("error:")
```

- [ ] **Step 2: Прогнать, убедиться что падает**

Run: `.venv/bin/python -m pytest tests/test_llm_resolver_tools.py -q`
Expected: FAIL — `ImportError: cannot import name '_html_to_text'`.

- [ ] **Step 3: Реализовать хелперы и инструменты в `llm.py`**

Добавить импорты: `import html.parser`, `import ipaddress`, `import socket`, `from urllib.parse import urljoin, urlparse`.

Модульные хелперы:

```python
class _TextExtractor(html.parser.HTMLParser):
    _SKIP = {"script", "style", "head", "title"}

    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip_depth += 1
        elif tag in {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4"}:
            self._parts.append(" ")

    def handle_endtag(self, tag):
        if tag in self._SKIP and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data):
        if self._skip_depth == 0:
            self._parts.append(data)


def _html_to_text(raw: str) -> str:
    parser = _TextExtractor()
    parser.feed(raw)
    return " ".join("".join(parser._parts).split())


def _is_forbidden_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip.split("%")[0])
    except ValueError:
        return True
    return (
        addr.is_private or addr.is_loopback or addr.is_link_local
        or addr.is_reserved or addr.is_multicast or addr.is_unspecified
    )
```

В `LlmResolver.__init__` — новые параметры (в конце списка, с дефолтами), сохранить поля и создать клиент:

```python
self._searxng_url = searxng_url.rstrip("/")
self._max_tool_rounds = max_tool_rounds
self._fetch_client = httpx.AsyncClient(
    verify=True, timeout=_FETCH_TIMEOUT, follow_redirects=False
)
```

Методы:

```python
async def _web_search(self, query: str) -> str:
    if not query.strip():
        return "error: empty query"
    try:
        response = await self._fetch_client.get(
            f"{self._searxng_url}/search", params={"q": query, "format": "json"}
        )
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        return f"error: search failed ({type(exc).__name__}: {exc})"
    results = data.get("results") if isinstance(data, dict) else None
    if not results:
        return "no results"
    lines = []
    for item in results[:_TOP_K_RESULTS]:
        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or "").strip()
        snippet = str(item.get("content") or "").strip()
        lines.append(f"- {title}\n  {url}\n  {snippet}")
    return "\n".join(lines)

async def _resolves_to_forbidden(self, hostname: str) -> bool:
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return True
    return any(_is_forbidden_ip(info[4][0]) for info in infos)

async def _web_fetch(self, url: str) -> str:
    current = url
    for _ in range(_MAX_REDIRECTS + 1):
        parsed = urlparse(current)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return f"error: unsupported URL '{current}'"
        if await self._resolves_to_forbidden(parsed.hostname):
            return f"error: forbidden host '{current}'"
        try:
            async with self._fetch_client.stream("GET", current) as response:
                if response.is_redirect and response.headers.get("location"):
                    current = urljoin(current, response.headers["location"])
                    continue
                if response.status_code >= 400:
                    return f"error: HTTP {response.status_code} for '{current}'"
                charset = response.charset_encoding or "utf-8"
                body = b""
                async for chunk in response.aiter_bytes():
                    body += chunk
                    if len(body) >= _FETCH_MAX_BYTES:
                        break
        except httpx.HTTPError as exc:
            return f"error: fetch failed ({type(exc).__name__}: {exc})"
        text = _html_to_text(body[:_FETCH_MAX_BYTES].decode(charset, errors="replace"))
        return text[:_FETCH_MAX_TEXT]
    return "error: too many redirects"
```

- [ ] **Step 4: Прогнать тесты**

Run: `.venv/bin/python -m pytest tests/test_llm_resolver_tools.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/purl_resolver/resolver/llm.py tests/test_llm_resolver_tools.py
git commit -m "feat: add web_search and web_fetch tools to LlmResolver"
```

---

### Task 3: Цикл tool-calling, `TOOLS`, промпт

**Files:**
- Modify: `src/purl_resolver/resolver/llm.py`
- Test: `tests/test_llm_resolver.py`

**Interfaces:**
- Consumes: `self._web_search`, `self._web_fetch`, `self._max_tool_rounds`.
- Produces:
  - `TOOLS: list[dict]` (OpenAI-схема, имена `web_search`, `web_fetch`).
  - `async def _run_with_tools(self, messages: list[dict]) -> tuple[str | None, str | None]`.
  - `async def _execute_tool(self, call) -> str`.
  - `_format_request_error(exc: BaseException) -> str` (модульный хелпер; переносит логику из старого `_request`).
  - Константа `_TOOL_ROUNDS_EXHAUSTED = "exceeded max tool rounds"`.
  - `resolve` вызывает `_run_with_tools` вместо `_request` и при `error == _TOOL_ROUNDS_EXHAUSTED` завершает попытки.

- [ ] **Step 1: Обновить тестовый helper и добавить падающие тесты**

В `tests/test_llm_resolver.py`, в `make_completion`, явно задать отсутствие инструментов:

```python
def make_completion(content: str) -> MagicMock:
    message = MagicMock()
    message.content = content
    message.tool_calls = None
    ...
```

Добавить в конец файла:

```python
def make_tool_call_completion(tool_name: str, arguments: str, call_id: str = "call_1") -> MagicMock:
    call = MagicMock()
    call.id = call_id
    call.function.name = tool_name
    call.function.arguments = arguments
    message = MagicMock()
    message.content = None
    message.tool_calls = [call]
    choice = MagicMock()
    choice.message = message
    completion = MagicMock()
    completion.choices = [choice]
    return completion


class TestToolCallingLoop:
    @pytest.mark.asyncio
    async def test_tools_passed_to_create(self) -> None:
        resolver, create, _ = make_llm_resolver()
        set_response(create, [success_json(_PURL)])
        await resolver.resolve(_PURL)
        assert "tools" in create.await_args.kwargs

    @pytest.mark.asyncio
    async def test_tool_call_executed_then_final_answer(self) -> None:
        resolver, create, _ = make_llm_resolver()
        resolver._web_search = AsyncMock(return_value="result-text")  # type: ignore
        create.side_effect = [
            make_tool_call_completion("web_search", '{"query": "requests repo"}'),
            make_completion(success_json(_PURL)),
        ]
        result = await resolver.resolve(_PURL)
        assert result.repository_url == "https://github.com/psf/requests"
        resolver._web_search.assert_awaited_once_with("requests repo")
        second_messages = create.await_args_list[1].kwargs["messages"]
        assert any(m.get("role") == "tool" and m.get("content") == "result-text" for m in second_messages)

    @pytest.mark.asyncio
    async def test_tool_round_exhaustion_is_terminal(self) -> None:
        resolver, create, _ = make_llm_resolver(attempts_count=3)
        resolver._web_search = AsyncMock(return_value="x")  # type: ignore
        create.side_effect = [
            make_tool_call_completion("web_search", '{"query": "a"}')
            for _ in range(resolver._max_tool_rounds + 1)
        ]
        result = await resolver.resolve(_PURL)
        assert result.repository_url is None
        assert any("max tool rounds" in w for w in result.warnings)
        # одна попытка: rounds+1 вызовов, без умножения на attempts_count
        assert create.await_count == resolver._max_tool_rounds + 1

    @pytest.mark.asyncio
    async def test_invalid_tool_arguments_return_error_string(self) -> None:
        resolver, create, _ = make_llm_resolver()
        create.side_effect = [
            make_tool_call_completion("web_search", "not-json"),
            make_completion(success_json(_PURL)),
        ]
        result = await resolver.resolve(_PURL)
        assert result.repository_url == "https://github.com/psf/requests"
```

- [ ] **Step 2: Прогнать, убедиться что падает**

Run: `.venv/bin/python -m pytest tests/test_llm_resolver.py -q`
Expected: FAIL — `test_tools_passed_to_create` (нет `tools` в kwargs) / loop не исполняет инструменты.

- [ ] **Step 3: Реализовать `TOOLS`, промпт, `_run_with_tools`, `_execute_tool`**

Добавить константу `TOOLS` (имена именно `web_search`/`web_fetch`):

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

_TOOL_ROUNDS_EXHAUSTED = "exceeded max tool rounds"
```

`SYSTEM_PROMPT` — заменить фразу «Use your web-search and web-fetch tools…» на указание вызывать `web_search`, а при неоднозначности проверять кандидата через `web_fetch`; формат ответа (JSON) и правила оставить.

Модульный хелпер (вынести логику из `_request`):

```python
def _format_request_error(exc: BaseException) -> str:
    cause = exc.__cause__ or exc.__context__
    if cause is not None and cause is not exc:
        return (
            f"LLM request failed ({type(exc).__name__}: {exc}; "
            f"caused by {type(cause).__name__}: {cause})"
        )
    return f"LLM request failed ({type(exc).__name__}: {exc})"
```

Удалить `_request`; добавить методы:

```python
async def _execute_tool(self, call) -> str:
    name = getattr(call.function, "name", "")
    try:
        args = json.loads(call.function.arguments or "{}")
    except (TypeError, json.JSONDecodeError):
        return f"error: invalid arguments for {name}"
    if not isinstance(args, dict):
        return f"error: invalid arguments for {name}"
    if name == "web_search":
        return await self._web_search(str(args.get("query", "")))
    if name == "web_fetch":
        return await self._web_fetch(str(args.get("url", "")))
    return f"error: unknown tool {name}"

async def _run_with_tools(self, messages: list[dict]) -> tuple[str | None, str | None]:
    for _ in range(self._max_tool_rounds + 1):
        try:
            completion = await self._client.chat.completions.create(
                model=self._model, messages=messages, tools=TOOLS
            )
        except (APIError, httpx.HTTPError) as exc:
            reason = _format_request_error(exc)
            logger.warning("%s", reason)
            return None, reason
        message = completion.choices[0].message
        tool_calls = getattr(message, "tool_calls", None)
        if not tool_calls:
            return message.content, None
        messages.append(message)
        for call in tool_calls:
            result = await self._execute_tool(call)
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
    return None, _TOOL_ROUNDS_EXHAUSTED
```

В `resolve` заменить вызов `_request` на `_run_with_tools`; после `self._record_failure(...)` добавить терминальный выход:

```python
            content, error = await self._run_with_tools(messages)
            if content is None:
                self._record_failure(warnings, messages, attempt, purl, error or "LLM request failed")
                if error == _TOOL_ROUNDS_EXHAUSTED:
                    break
                continue
```

- [ ] **Step 4: Прогнать тесты**

Run: `.venv/bin/python -m pytest tests/test_llm_resolver.py tests/test_llm_resolver_tools.py -q`
Expected: PASS (включая ранее существовавшие тесты).

- [ ] **Step 5: Commit**

```bash
git add src/purl_resolver/resolver/llm.py tests/test_llm_resolver.py
git commit -m "feat: add tool-calling loop with web_search/web_fetch to LlmResolver"
```

---

### Task 4: Настройки, API и фабрика

**Files:**
- Modify: `src/purl_resolver/settings_store.py`
- Modify: `src/purl_resolver/routes/settings.py`
- Modify: `src/purl_resolver/resolver/factory.py`
- Modify: `src/purl_resolver/main.py:71`
- Test: `tests/test_settings_store.py`, `tests/test_api.py`, `tests/test_llm_resolver.py`

**Interfaces:**
- Consumes: `searxng_settings` (Task 1), `LlmResolver(..., searxng_url=, max_tool_rounds=)` (Task 2).
- Produces:
  - `AppSettings.llm_resolver_max_tool_rounds: int = Field(default=3, ge=1, le=10)`.
  - `SettingsUpdate.llm_resolver_max_tool_rounds: int | None = Field(None, ge=1, le=10)`.
  - `build_resolvers(settings, app_settings, searxng_url: str = "http://searxng:8080")`.
  - `GET`/`PATCH /api/v1/settings` содержат `llm_resolver_max_tool_rounds`.

- [ ] **Step 1: Написать падающие тесты**

В `tests/test_settings_store.py` добавить roundtrip:

```python
def test_max_tool_rounds_default_and_roundtrip(tmp_path):
    from purl_resolver.settings_store import AppSettings, SettingsStore
    store = SettingsStore(tmp_path / "settings.json")
    assert store.load().llm_resolver_max_tool_rounds == 3
    store.save(AppSettings(llm_resolver_max_tool_rounds=5))
    assert SettingsStore(tmp_path / "settings.json").load().llm_resolver_max_tool_rounds == 5
```

В `tests/test_api.py` (синхронный `client`-фикстур, класс по образцу `TestLlmResolverTlsSettings`) добавить проверку GET/PATCH поля:

```python
class TestLlmMaxToolRounds:
    def test_get_settings_includes_max_tool_rounds(self, client: TestClient) -> None:
        data = client.get("/api/v1/settings").json()
        assert data["llm_resolver_max_tool_rounds"] == 3

    def test_patch_settings_max_tool_rounds(self, client: TestClient, tmp_path: Path) -> None:
        client.app.state.settings_store = SettingsStore(path=tmp_path / "settings.json")
        response = client.patch("/api/v1/settings", json={"llm_resolver_max_tool_rounds": 4})
        assert response.status_code == 200
        assert response.json()["llm_resolver_max_tool_rounds"] == 4
```

(Тест синхронный — фикстура `client` в `tests/test_api.py` возвращает `TestClient`; PATCH-тест подменяет `settings_store` на файл в `tmp_path`, чтобы не трогать `data/settings.json`.)

В `tests/test_llm_resolver.py` добавить проверку фабрики:

```python
def test_factory_passes_searxng_and_rounds() -> None:
    from purl_resolver.config import Settings
    from purl_resolver.resolver.factory import build_resolvers
    from purl_resolver.settings_store import AppSettings

    app_settings = AppSettings(
        ecosystems_enabled=False, librariesio_enabled=False,
        llm_resolver_enabled=True, llm_resolver_base_url=_BASE_URL,
        llm_resolver_api_key=_API_KEY, llm_resolver_model=_MODEL,
        llm_resolver_max_tool_rounds=5,
    )
    with patch("purl_resolver.resolver.factory.LlmResolver") as llm_cls:
        llm_cls.return_value.name = "llm"
        build_resolvers(Settings(), app_settings, "http://searxng:8080")
    kwargs = llm_cls.call_args.kwargs
    assert kwargs["searxng_url"] == "http://searxng:8080"
    assert kwargs["max_tool_rounds"] == 5
```

- [ ] **Step 2: Прогнать, убедиться что падает**

Run: `.venv/bin/python -m pytest tests/test_settings_store.py tests/test_api.py tests/test_llm_resolver.py -q`
Expected: FAIL (нет поля/параметра).

- [ ] **Step 3: Реализовать**

`settings_store.py` — добавить поле в `AppSettings` после `llm_resolver_ca_bundle`.

`routes/settings.py`:
- импорт `from ..config import settings, searxng_settings`;
- в `SettingsUpdate` добавить `llm_resolver_max_tool_rounds: int | None = Field(None, ge=1, le=10)`;
- в оба ответа `GET`/`PATCH` добавить `"llm_resolver_max_tool_rounds": <obj>.llm_resolver_max_tool_rounds`;
- в `_rebuild_resolvers` вызывать `build_resolvers(settings, app_settings, searxng_settings.url)`.

`resolver/factory.py` — сигнатура и проброс:

```python
def build_resolvers(
    settings: Settings,
    app_settings: AppSettings,
    searxng_url: str = "http://searxng:8080",
) -> list[Resolver]:
```

В конструкторе `LlmResolver(...)` добавить `searxng_url=searxng_url` и
`max_tool_rounds=app_settings.llm_resolver_max_tool_rounds`.

`main.py:71` — `build_resolvers(settings, app_settings, searxng_settings.url)` и импорт `searxng_settings` из `.config`.

- [ ] **Step 4: Прогнать тесты**

Run: `.venv/bin/python -m pytest tests/test_settings_store.py tests/test_api.py tests/test_llm_resolver.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/purl_resolver/settings_store.py src/purl_resolver/routes/settings.py \
  src/purl_resolver/resolver/factory.py src/purl_resolver/main.py \
  tests/test_settings_store.py tests/test_api.py tests/test_llm_resolver.py
git commit -m "feat: wire searxng_url and max_tool_rounds through settings and factory"
```

---

### Task 5: Frontend — поле «Максимум раундов поиска»

**Files:**
- Modify: `frontend/src/types/api.ts:68-74,102-109`
- Modify: `frontend/src/stores/useSettingsStore.ts:26-34,67-73,94-103`
- Modify: `frontend/src/views/Settings.vue` (карточка LLM, рядом с `attemptsCount`)
- Modify: `frontend/src/i18n/locales/en.json`, `frontend/src/i18n/locales/ru.json`
- Test: `frontend/src/views/Settings.test.ts`

**Interfaces:**
- Consumes: `GET/PATCH /api/v1/settings` с `llm_resolver_max_tool_rounds`.
- Produces: поле ввода 1..10, автосохранение через `debouncedAutoSave({ llm_resolver_max_tool_rounds })`.

- [ ] **Step 1: Написать/обновить падающий тест**

В `frontend/src/views/Settings.test.ts`: добавить `llm_resolver_max_tool_rounds: 3` в `defaultSettings`-мок и тест, что поле отрисовано и изменение шлёт `llm_resolver_max_tool_rounds`.

- [ ] **Step 2: Прогнать, убедиться что падает**

Run: `npm --prefix frontend run test -- Settings`
Expected: FAIL (нет поля/ключа).

- [ ] **Step 3: Реализовать**

- `types/api.ts`: `llm_resolver_max_tool_rounds: number` в `SettingsResponse`; `llm_resolver_max_tool_rounds?: number` в `SettingsUpdate`.
- `useSettingsStore.ts`: `const llmMaxToolRounds = ref(3)`; в `load()` — `llmMaxToolRounds.value = data.llm_resolver_max_tool_rounds`; добавить в возвращаемый объект.
- `Settings.vue`: в карточке LLM после `attemptsCount` — строка с `<input type="number" v-model.number="llmMaxToolRounds" :disabled="!llmEnabled" min="1" max="10" @change="debouncedAutoSave({ llm_resolver_max_tool_rounds: llmMaxToolRounds })">`; добавить `llmMaxToolRounds` в деструктуризацию из store.
- i18n: `settings.llmResolver.maxToolRounds` и `maxToolRoundsDesc` в en/ru.

- [ ] **Step 4: Прогнать тесты и сборку**

Run: `npm --prefix frontend run test`
Run: `npm --prefix frontend run build`
Expected: PASS / успешная сборка.

- [ ] **Step 5: Commit**

```bash
git add frontend/src
git commit -m "feat(frontend): add llm_resolver_max_tool_rounds setting"
```

---

### Task 6: Спецификации и README (после кода)

**Files:**
- Modify: `README.md`
- Modify: `specs/domains/purl-resolution.md`
- Modify: `specs/architecture/layers.md`
- Modify: `specs/decisions/0008-llm-as-last-resort-resolver.md`

**Interfaces:** нет (документация).

- [ ] **Step 1: Обновить `README.md`**

Раздел Settings/Deployment: SearXNG-сервис в compose, генерация `SEARXNG_SECRET`, `SEARXNG_URL`, назначение `llm_resolver_max_tool_rounds`, что llm-resolver теперь делает реальный веб-поиск.

- [ ] **Step 2: Обновить specs**

- `specs/domains/purl-resolution.md`: описать tool-calling `web_search`/`web_fetch`, SearXNG, новые настройки.
- `specs/architecture/layers.md`: LLM-резолвер теперь с инструментами и SearXNG-зависимостью.
- `specs/decisions/0008-llm-as-last-resort-resolver.md`: Consequences — реальный веб-поиск через локальный SearXNG, ограничение раундов, блокировка приватных IP.

- [ ] **Step 3: Проверить согласованность спецификаций**

Использовать набор `vibespec` (`vibespec-check`) для проверки расхождений, если доступен; иначе — ручная сверка с кодом.

- [ ] **Step 4: Commit**

```bash
git add README.md specs/
git commit -m "docs: document LLM web search via SearXNG"
```

---

## Definition of Done (полный план)

- `SKIP_E2E=1 .venv/bin/python -m pytest -q` — зелёный.
- `ruff check` — без новых замечаний.
- `npm --prefix frontend run test` и `npm --prefix frontend run build` — проходят.
- `docker compose up` поднимает `app`, `db`, `searxng`; `app` ходит на `http://searxng:8080`.
- При включённом llm-resolver модель получает `tools`, вызывает `web_search`, получает результаты и возвращает финальный JSON.
- `web_fetch` отклоняет не-http(s), приватные IP и редиректы на приватные адреса.
- При выключенном llm-resolver поведение и тесты не меняются.
