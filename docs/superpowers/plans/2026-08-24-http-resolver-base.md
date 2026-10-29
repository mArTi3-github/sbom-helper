# HTTP Resolver Base Module — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Устранить дублирование обвязки сетевых резолверов через двухуровневую иерархию `HttpResolver`/`HttpApiResolver`, общий SSRF-защищённый URL check и единую политику нормализации URL для всей цепочки.

**Architecture:** Новый module `src/purl_resolver/url_check.py` (SSRF-guard + HEAD) используется и `url_validator`, и резолверами. Новый `src/purl_resolver/resolver/base.py`: модульная функция `normalize_repository_url`, класс `HttpResolver` (stateless-хелперы: `_validate_purl`, `_check_url`) и `HttpApiResolver(HttpResolver)` (client, rate limiter, `RetryHelper`, error-ladder `_get_json`, `close()`). Три API-резолвера наследуют `HttpApiResolver`, `LlmResolver` — `HttpResolver`, `Purl2RepoResolver` получает только вызов `normalize_repository_url`. Закрытие клиентов — через duck-typing в `_rebuild_resolvers` и lifespan teardown.

**Tech Stack:** Python 3.12, httpx, openai, pytest (asyncio-режим), asyncio.

**Spec:** `docs/superpowers/specs/2026-08-24-http-resolver-base-design.md`

## Global Constraints

- Все pytest-запуски: `.venv/bin/pytest ...` из корня репозитория (не использовать системный python).
- Новых сторонних зависимостей нет (httpx, openai уже в проекте).
- Форматы сообщений warnings сохраняются байт-идентично там, где они существовали (см. Spec Decision 6). Единственное изменение текста — в llm (`"not a valid https URL"`).
- Приватные атрибуты резолверов `_client`, `_min_interval`, `_last_request_time` сохраняют имена (существующие тесты их подменяют напрямую).
- Порядок цепочки не меняется (ADR-0007/0008): purl2repo → depsdev → ecosyste.ms → libraries.io → apk → llm.
- `resolver/interface.py` (Resolver ABC, Resolution, исключения) и `resolver/retry.py` не трогаются.
- `apk.py` не меняется.
- Коммиты — по одному на задачу, сообщения в стиле репозитория (русский, `git log` как образец).
- Полный прогон в конце: `.venv/bin/pytest tests -q --ignore=tests/e2e` (e2e требует живых API).

## File Structure

**Create:**
- `src/purl_resolver/url_check.py` — SSRF-защищённый HEAD (перенос из url_validator)
- `src/purl_resolver/resolver/base.py` — `normalize_repository_url`, `HttpResolver`, `HttpApiResolver`
- `tests/test_url_check.py` — тесты url_check
- `tests/test_resolver_base.py` — тесты base
- `specs/decisions/0009-http-resolver-base.md` — ADR

**Modify:**
- `src/purl_resolver/url_validator.py` — делегирование в url_check
- `src/purl_resolver/resolver/depsdev.py`, `ecosystems.py`, `librariesio.py`, `llm.py`, `purl2repo.py` — адаптеры
- `src/purl_resolver/routes/settings.py` — async `_rebuild_resolvers` + close
- `src/purl_resolver/main.py` — teardown close
- `tests/test_vcs_check.py`, `tests/test_url_validator.py` — патчи `_is_private_url`
- `tests/test_llm_resolver.py`, `tests/test_ecosystems_resolver.py`, `tests/test_librariesio_resolver.py`, `tests/test_purl2repo_resolver.py`, `tests/test_api.py` — новые/обновлённые тесты
- `specs/architecture/layers.md`, `specs/INDEX.md` — документация

---

### Task 1: `url_check.py` — общий SSRF-защищённый HEAD

**Files:**
- Create: `src/purl_resolver/url_check.py`
- Create: `tests/test_url_check.py`
- Modify: `src/purl_resolver/url_validator.py`
- Modify: `tests/test_vcs_check.py`, `tests/test_url_validator.py`

**Interfaces:**
- Consumes: ничего (только stdlib + httpx)
- Produces: `async def is_private_url(url: str) -> bool`, `async def head_url(url: str, timeout: float) -> httpx.Response` (бросает `ConnectionError` на приватный адрес до/после редиректа)

- [ ] **Step 1: Write failing test file `tests/test_url_check.py`**

```python
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from purl_resolver.url_check import head_url, is_private_url


class TestIsPrivateUrl:
    @pytest.mark.asyncio
    async def test_public_host_is_not_private(self) -> None:
        assert await is_private_url("https://github.com") is False

    @pytest.mark.asyncio
    async def test_localhost_is_private(self) -> None:
        assert await is_private_url("http://127.0.0.1/admin") is True

    @pytest.mark.asyncio
    async def test_cloud_metadata_is_private(self) -> None:
        assert await is_private_url("http://169.254.169.254/latest/meta-data") is True

    @pytest.mark.asyncio
    async def test_dns_failure_returns_false(self) -> None:
        assert await is_private_url("https://unknown.invalid") is False


class TestHeadUrl:
    @pytest.mark.asyncio
    async def test_private_url_raises_connection_error(self) -> None:
        with patch("purl_resolver.url_check.is_private_url", return_value=True):
            with pytest.raises(ConnectionError):
                await head_url("http://127.0.0.1/", timeout=5.0)

    @pytest.mark.asyncio
    async def test_redirect_target_private_raises(self) -> None:
        response = MagicMock()
        response.url = "http://169.254.169.254/latest"
        client = AsyncMock()
        client.head.return_value = response
        with (
            patch("purl_resolver.url_check.is_private_url", side_effect=[False, True]),
            patch("httpx.AsyncClient", return_value=client),
        ):
            with pytest.raises(ConnectionError):
                await head_url("https://example.com", timeout=5.0)

    @pytest.mark.asyncio
    async def test_public_url_returns_response(self) -> None:
        response = MagicMock()
        response.url = "https://github.com/"
        client = AsyncMock()
        client.head.return_value = response
        with (
            patch("purl_resolver.url_check.is_private_url", return_value=False),
            patch("httpx.AsyncClient", return_value=client),
        ):
            result = await head_url("https://github.com", timeout=5.0)
        assert result is response
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_url_check.py -v`
Expected: FAIL — `ModuleNotFoundError: purl_resolver.url_check`

- [ ] **Step 3: Create `src/purl_resolver/url_check.py`**

Перенести `_PRIVATE_NETWORKS` и `_is_private_url` из `url_validator.py` (там они станут ненужными) и `_head_request`-семантику:

```python
from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
from urllib.parse import urlsplit

import httpx

logger = logging.getLogger(__name__)

_PRIVATE_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("192.88.99.0/24"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("240.0.0.0/4"),
    ipaddress.ip_network("255.255.255.255/32"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("ff00::/8"),
]


async def is_private_url(url: str) -> bool:
    """Resolve hostname and check if it points to a private/reserved IP range."""
    host = urlsplit(url).hostname
    if not host:
        return False
    try:
        ips = await asyncio.wait_for(
            asyncio.to_thread(socket.getaddrinfo, host, None),
            timeout=5.0,
        )
    except (socket.gaierror, asyncio.TimeoutError):
        return False
    for _, _, _, _, sockaddr in ips:
        ip = ipaddress.ip_address(sockaddr[0])
        if any(ip in net for net in _PRIVATE_NETWORKS):
            logger.warning("URL %s resolves to private IP %s", url, ip)
            return True
    return False


async def head_url(url: str, timeout: float) -> httpx.Response:
    if await is_private_url(url):
        raise ConnectionError(f"Refusing HEAD request to private URL: {url}")
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        resp = await client.head(url)
    if await is_private_url(str(resp.url)):
        raise ConnectionError(f"HEAD redirect target is private: {resp.url}")
    return resp
```

- [ ] **Step 4: Run new tests to verify they pass**

Run: `.venv/bin/pytest tests/test_url_check.py -v`
Expected: PASS (3 из 3 классов)

- [ ] **Step 5: Refactor `src/purl_resolver/url_validator.py`**

1. Добавить импорт после `import httpx`:
   ```python
   from . import url_check
   ```
2. Удалить `_PRIVATE_NETWORKS` (строки 21–42) и `async def _is_private_url` (строки 45–62).
3. Заменить тело `_head_request` (строки 100–107) на делегирование:
   ```python
   async def _head_request(url: str, timeout: int):
       return await url_check.head_url(url, timeout)
   ```
4. Заменить все вызовы `_is_private_url(` на `url_check.is_private_url(` — 6 мест:
   - `ensure_connectivity` (строка 86)
   - `_fossil_probe_xfer` (строки 208, 225)
   - `_fossil_probe_footer` (строки 242, 249)
   - `validate_url` (строка 320)

Публичный интерфейс (`validate_url`, `ensure_connectivity`, `UrlValidationResult`, `UrlValidationOutput`) не меняется.

- [ ] **Step 6: Update tests that reference `_is_private_url`**

`tests/test_vcs_check.py`:
1. `_patch_private()` (строки 44–47): target `"purl_resolver.url_validator._is_private_url"` → `"purl_resolver.url_check.is_private_url"`.
2. Класс `TestIsPrivateUrl` (строки 50–108): заменить `from purl_resolver.url_validator import _is_private_url` на `from purl_resolver.url_check import is_private_url` и вызовы `_is_private_url(` → `is_private_url(` (7 тестов).
3. Патчи в строках 411 и 478: target → `"purl_resolver.url_check.is_private_url"`.

`tests/test_url_validator.py`: патчи `"purl_resolver.url_validator._is_private_url"` в строках 171 и 268 → `"purl_resolver.url_check.is_private_url"`. Патчи `"purl_resolver.url_validator._head_request"` (строки 35–210, 540–576) НЕ трогать — обёртка сохранена.

- [ ] **Step 7: Run affected tests**

Run: `.venv/bin/pytest tests/test_url_check.py tests/test_url_validator.py tests/test_vcs_check.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add src/purl_resolver/url_check.py src/purl_resolver/url_validator.py tests/test_url_check.py tests/test_vcs_check.py tests/test_url_validator.py
git commit -m "Рефакторинг: вынести SSRF-защищённый HEAD-проверку в url_check.py"
```

---

### Task 2: `resolver/base.py` — `normalize_repository_url`, `HttpResolver`, `HttpApiResolver`

**Files:**
- Create: `src/purl_resolver/resolver/base.py`
- Create: `tests/test_resolver_base.py`

**Interfaces:**
- Consumes: `url_check.head_url` (Task 1), `purl_utils.validate`/`PurlValidationError`/`PurlComponents`, `retry.RetryHelper`/`RetryConfig`, `interface.Resolution`/`Resolver`
- Produces:
  - `def normalize_repository_url(url: str) -> str | None` (модульная функция)
  - `class HttpResolver(Resolver)`: `__init__(*, timeout: float = 15.0)`, `@staticmethod _validate_purl(purl) -> tuple[PurlComponents | None, str | None]`, `async _check_url(url) -> tuple[bool, str]`
  - `class HttpApiResolver(HttpResolver)`: `__init__(*, timeout=15.0, max_requests_per_second=0.0, retry_config=None)`, атрибуты `_client`/`_min_interval`/`_last_request_time`/`_retry`, `async _rate_limit_wait()`, `async _get_json(purl, url, *, label, params=None, subject=None) -> tuple[dict | None, str | None]`, `async close()`

- [ ] **Step 1: Write failing test file `tests/test_resolver_base.py`**

```python
from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from purl_resolver.resolver.base import (
    HttpApiResolver,
    HttpResolver,
    normalize_repository_url,
)
from purl_resolver.resolver.retry import RetryConfig


class TestNormalizeRepositoryUrl:
    def test_http_is_upgraded_to_https(self) -> None:
        assert normalize_repository_url("http://github.com/psf/requests") == "https://github.com/psf/requests"

    def test_scm_git_prefix_stripped(self) -> None:
        assert normalize_repository_url("scm:git:https://github.com/psf/requests.git") == "https://github.com/psf/requests"

    def test_git_ssh_style_converted(self) -> None:
        assert normalize_repository_url("git@github.com:psf/requests.git") == "https://github.com/psf/requests"

    def test_git_scheme_converted_to_https(self) -> None:
        assert normalize_repository_url("git://github.com/psf/requests") == "https://github.com/psf/requests"

    def test_branch_suffix_stripped(self) -> None:
        assert normalize_repository_url("https://github.com/keycloak/keycloak/tree/master") == "https://github.com/keycloak/keycloak"

    def test_trailing_git_stripped(self) -> None:
        assert normalize_repository_url("https://github.com/psf/requests.git") == "https://github.com/psf/requests"

    def test_non_https_scheme_rejected(self) -> None:
        assert normalize_repository_url("javascript:alert(1)") is None


class TestHttpResolver:
    @pytest.mark.asyncio
    async def test_check_url_ok(self) -> None:
        resolver = HttpResolver(timeout=5.0)
        response = MagicMock()
        response.status_code = 200
        with patch("purl_resolver.resolver.base.head_url", new=AsyncMock(return_value=response)):
            ok, err = await resolver._check_url("https://github.com/a/b")
        assert ok is True
        assert err == ""

    @pytest.mark.asyncio
    async def test_check_url_http_error_status(self) -> None:
        resolver = HttpResolver(timeout=5.0)
        response = MagicMock()
        response.status_code = 404
        with patch("purl_resolver.resolver.base.head_url", new=AsyncMock(return_value=response)):
            ok, err = await resolver._check_url("https://github.com/a/b")
        assert ok is False
        assert "404" in err

    @pytest.mark.asyncio
    async def test_check_url_private_rejected(self) -> None:
        resolver = HttpResolver(timeout=5.0)
        with patch(
            "purl_resolver.resolver.base.head_url",
            new=AsyncMock(side_effect=ConnectionError("private")),
        ):
            ok, err = await resolver._check_url("http://127.0.0.1/")
        assert ok is False
        assert "failed" in err

    @pytest.mark.asyncio
    async def test_check_url_network_error(self) -> None:
        resolver = HttpResolver(timeout=5.0)
        with patch(
            "purl_resolver.resolver.base.head_url",
            new=AsyncMock(side_effect=httpx.ConnectError("refused")),
        ):
            ok, err = await resolver._check_url("https://github.com/a/b")
        assert ok is False
        assert "failed" in err

    def test_validate_purl_returns_components(self) -> None:
        components, err = HttpResolver._validate_purl("pkg:pypi/requests@2.31.0")
        assert err is None
        assert components is not None
        assert components.type == "pypi"

    def test_validate_purl_invalid_returns_error(self) -> None:
        _, err = HttpResolver._validate_purl("not-a-purl")
        assert err is not None
        assert "Invalid PURL" in err


class TestHttpApiResolver:
    @pytest.mark.asyncio
    async def test_rate_limit_minimum_interval(self) -> None:
        resolver = HttpApiResolver(max_requests_per_second=10.0)
        assert resolver._min_interval == 0.1
        t0 = time.monotonic()
        await resolver._rate_limit_wait()
        await resolver._rate_limit_wait()
        assert time.monotonic() - t0 >= 0.09

    @pytest.mark.asyncio
    async def test_rate_limit_disabled_when_zero(self) -> None:
        resolver = HttpApiResolver(max_requests_per_second=0)
        assert resolver._min_interval == 0
        t0 = time.monotonic()
        await resolver._rate_limit_wait()
        await resolver._rate_limit_wait()
        assert time.monotonic() - t0 < 0.1

    @pytest.mark.asyncio
    async def test_get_json_error_ladder(self) -> None:
        resolver = HttpApiResolver(max_requests_per_second=0, retry_config=RetryConfig(max_attempts=1))
        client = AsyncMock()
        resolver._client = client

        client.get.side_effect = httpx.ConnectError("refused")
        data, err = await resolver._get_json("pkg:pypi/x", "https://api.example.com/x", label="svc")
        assert data is None
        assert err.startswith("svc network error for pkg:pypi/x")

        client.get.side_effect = httpx.HTTPStatusError(
            "404", request=MagicMock(), response=MagicMock(status_code=404)
        )
        _, err = await resolver._get_json("pkg:pypi/x", "https://api.example.com/x", label="svc")
        assert err == "svc error 404 for pkg:pypi/x"

        client.get.side_effect = httpx.TimeoutException("t")
        _, err = await resolver._get_json("pkg:pypi/x", "https://api.example.com/x", label="svc")
        assert err == "svc timeout for pkg:pypi/x"

    @pytest.mark.asyncio
    async def test_get_json_invalid_response_uses_subject(self) -> None:
        resolver = HttpApiResolver(max_requests_per_second=0, retry_config=RetryConfig(max_attempts=1))
        client = AsyncMock()
        resolver._client = client
        response = MagicMock()
        response.status_code = 200
        response.json.side_effect = ValueError("no json")
        client.get.return_value = response
        data, err = await resolver._get_json(
            "pkg:pypi/x", "https://api.example.com/x", label="svc", subject="platform/name"
        )
        assert data is None
        assert err == "svc invalid response for platform/name"

    @pytest.mark.asyncio
    async def test_close_closes_client(self) -> None:
        resolver = HttpApiResolver()
        client = AsyncMock()
        resolver._client = client
        await resolver.close()
        client.aclose.assert_awaited_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_resolver_base.py -v`
Expected: FAIL — `ModuleNotFoundError: purl_resolver.resolver.base`

- [ ] **Step 3: Create `src/purl_resolver/resolver/base.py`**

```python
from __future__ import annotations

import asyncio
import logging
import time
from urllib.parse import urlparse

import httpx

from ..purl_utils import PurlComponents, PurlValidationError, validate
from ..url_check import head_url
from .interface import Resolution, Resolver
from .retry import RetryConfig, RetryHelper

logger = logging.getLogger(__name__)


def normalize_repository_url(url: str) -> str | None:
    u = url.strip()
    lowered = u.lower()
    for prefix in ("scm:git:", "scm:svn:", "scm:hg:", "scm:"):
        if lowered.startswith(prefix):
            u = u[len(prefix):]
            break
    u = u.strip()
    if u.startswith("git://"):
        u = "https://" + u[len("git://"):]
    elif u.startswith("ssh://"):
        rest = u[len("ssh://"):]
        if rest.startswith("git@"):
            rest = rest[len("git@"):]
        if ":" in rest:
            host, _, path = rest.partition(":")
            if path and not path.split("/", 1)[0].isdigit():
                rest = f"{host}/{path}"
        u = "https://" + rest
    elif u.startswith("git@") and ":" in u:
        host, _, path = u.partition(":")
        u = f"https://{host[4:]}/{path}"
    if u.startswith("http://"):
        u = "https://" + u[len("http://"):]
    u = u.rstrip("/")
    lowered_u = u.lower()
    for host in ("github.com", "gitlab.com"):
        marker = f"/{host}/"
        pos = lowered_u.find(marker)
        if pos == -1:
            continue
        rest = u[pos + len(marker):]
        tree_pos = rest.lower().find("/tree/")
        if tree_pos != -1:
            u = u[: pos + len(marker) + tree_pos]
            if u.endswith("/-"):
                u = u[:-2]
        break
    if u.endswith(".git"):
        u = u[:-4]
    if urlparse(u).scheme != "https":
        return None
    return u


class HttpResolver(Resolver):

    def __init__(self, *, timeout: float = 15.0) -> None:
        self._timeout = timeout

    @property
    def name(self) -> str:
        raise NotImplementedError

    async def resolve(self, purl: str) -> Resolution:
        raise NotImplementedError

    @staticmethod
    def _validate_purl(purl: str) -> tuple[PurlComponents | None, str | None]:
        try:
            return validate(purl), None
        except PurlValidationError as e:
            return None, f"Invalid PURL: {e}"

    async def _check_url(self, url: str) -> tuple[bool, str]:
        try:
            response = await head_url(url, self._timeout)
        except ConnectionError as exc:
            return False, f"URL check for '{url}' failed: {exc}"
        except httpx.HTTPError as exc:
            return False, f"URL check for '{url}' failed: {exc}"
        if response.status_code >= 400:
            return False, f"URL '{url}' returned HTTP {response.status_code}"
        return True, ""


class HttpApiResolver(HttpResolver):

    def __init__(
        self,
        *,
        timeout: float = 15.0,
        max_requests_per_second: float = 0.0,
        retry_config: RetryConfig | None = None,
    ) -> None:
        super().__init__(timeout=timeout)
        self._client = httpx.AsyncClient(timeout=timeout)
        self._min_interval = (
            1.0 / max_requests_per_second if max_requests_per_second > 0 else 0
        )
        self._last_request_time = 0.0
        self._retry = RetryHelper(retry_config or RetryConfig())

    async def _rate_limit_wait(self) -> None:
        if self._min_interval <= 0:
            return
        now = time.monotonic()
        elapsed = now - self._last_request_time
        if elapsed < self._min_interval:
            await asyncio.sleep(self._min_interval - elapsed)
        self._last_request_time = time.monotonic()

    async def _get_json(
        self,
        purl: str,
        url: str,
        *,
        label: str,
        params: dict | None = None,
        subject: str | None = None,
    ) -> tuple[dict | None, str | None]:
        target = subject or purl
        await self._rate_limit_wait()
        try:
            response = await self._retry.execute(lambda: self._client.get(url, params=params))
            response.raise_for_status()
            return response.json(), None
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            logger.warning("%s returned %d for %s", label, status, target)
            return None, f"{label} error {status} for {target}"
        except httpx.TimeoutException:
            logger.warning("%s request timed out for %s", label, target)
            return None, f"{label} timeout for {target}"
        except httpx.HTTPError as exc:
            logger.warning("%s request failed for %s: %s", label, target, exc)
            return None, f"{label} network error for {target}: {exc}"
        except ValueError:
            logger.warning("%s returned non-JSON response for %s", label, target)
            return None, f"{label} invalid response for {target}"

    async def close(self) -> None:
        await self._client.aclose()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_resolver_base.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/purl_resolver/resolver/base.py tests/test_resolver_base.py
git commit -m "Рефакторинг: добавить базовые module HttpResolver и HttpApiResolver"
```

---

### Task 3: `DepsdevResolver` → `HttpApiResolver`

**Files:**
- Modify: `src/purl_resolver/resolver/depsdev.py`

**Interfaces:**
- Consumes: `HttpApiResolver`, `normalize_repository_url` из `resolver.base` (Task 2)
- Produces: без изменений внешнего контракта — `DepsdevResolver(timeout=15.0, max_requests_per_second=1.0, retry_config=None)`, `name == "depsdev"`; re-export `purl_resolver.resolver.depsdev.normalize_repository_url` сохранён

- [ ] **Step 1: Write the failing test (pinning re-export + inheritance)**

Добавить в конец `tests/test_depsdev_resolver.py`:

```python
class TestBaseIntegration:
    def test_depsdev_subclasses_http_api_resolver(self) -> None:
        from purl_resolver.resolver.base import HttpApiResolver
        assert issubclass(DepsdevResolver, HttpApiResolver)

    def test_normalize_repository_url_is_reexported(self) -> None:
        from purl_resolver.resolver.depsdev import normalize_repository_url
        assert normalize_repository_url("git://github.com/psf/requests.git") == "https://github.com/psf/requests"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_depsdev_resolver.py::TestBaseIntegration -v`
Expected: FAIL

- [ ] **Step 3: Refactor `src/purl_resolver/resolver/depsdev.py`**

Заменить содержимое файла (payload-логика версии и извлечения URL сохраняется):

```python
from __future__ import annotations

import logging
from urllib.parse import quote

from .base import HttpApiResolver, normalize_repository_url
from .interface import Resolution
from .retry import RetryConfig

logger = logging.getLogger(__name__)

_API_BASE = "https://api.deps.dev/v3"

_DEFAULT_MAX_REQUESTS_PER_SECOND = 1.0

_SYSTEMS: dict[str, str] = {
    "maven": "MAVEN",
    "npm": "NPM",
    "golang": "GO",
    "pypi": "PYPI",
    "nuget": "NUGET",
    "cargo": "CARGO",
    "gem": "RUBYGEMS",
}


def build_package_name(purl_type: str, namespace: str | None, name: str) -> str:
    if purl_type == "maven":
        return f"{namespace}:{name}" if namespace else name
    if namespace:
        return f"{namespace}/{name}"
    return name


def extract_source_repo_url(version_data: dict) -> str | None:
    for link in version_data.get("links", []):
        if link.get("label") == "SOURCE_REPO" and link.get("url"):
            return str(link["url"])
    for project in version_data.get("relatedProjects", []):
        if project.get("relationType") == "SOURCE_REPO":
            project_id = project.get("projectKey", {}).get("id")
            if project_id:
                return f"https://{project_id}"
    return None


class DepsdevResolver(HttpApiResolver):

    def __init__(
        self,
        timeout: float = 15.0,
        max_requests_per_second: float = _DEFAULT_MAX_REQUESTS_PER_SECOND,
        retry_config: RetryConfig | None = None,
    ) -> None:
        super().__init__(
            timeout=timeout,
            max_requests_per_second=max_requests_per_second,
            retry_config=retry_config,
        )

    @property
    def name(self) -> str:
        return "depsdev"

    async def resolve(self, purl: str) -> Resolution:
        components, error = self._validate_purl(purl)
        if error is not None:
            return Resolution(purl=purl, warnings=[error])
        assert components is not None

        system = _SYSTEMS.get(components.type)
        if system is None:
            return Resolution(
                purl=purl,
                warnings=[f"Unsupported package type '{components.type}' for deps.dev resolver"],
            )

        package_name = build_package_name(components.type, components.namespace, components.name)
        encoded_name = quote(package_name, safe="")

        version = components.version
        if version is None:
            data, error = await self._get_json(
                purl,
                f"{_API_BASE}/systems/{system}/packages/{encoded_name}",
                label="deps.dev",
            )
            if error is not None:
                return Resolution(purl=purl, warnings=[error])
            versions = (data or {}).get("versions") or []
            if not versions:
                return Resolution(purl=purl, warnings=[f"No versions found on deps.dev for {purl}"])
            chosen = next((v for v in versions if v.get("isDefault")), None)
            if chosen is None:
                dated = [v for v in versions if v.get("publishedAt")]
                chosen = max(dated, key=lambda v: v["publishedAt"]) if dated else versions[-1]
            version = chosen.get("versionKey", {}).get("version")
            if not version:
                warning = f"No version key found on deps.dev for {purl}"
                return Resolution(purl=purl, warnings=[warning])

        version_url = (
            f"{_API_BASE}/systems/{system}/packages/{encoded_name}"
            f"/versions/{quote(version, safe='')}"
        )
        version_data, error = await self._get_json(purl, version_url, label="deps.dev")
        if error is not None:
            return Resolution(purl=purl, warnings=[error])

        repo_url = extract_source_repo_url(version_data or {})
        if not repo_url:
            warning = f"No SOURCE_REPO link found on deps.dev for {purl}"
            return Resolution(purl=purl, warnings=[warning])

        normalized_url = normalize_repository_url(repo_url)
        if normalized_url is None:
            warning = f"Invalid repository URL from deps.dev for {purl}: {repo_url}"
            return Resolution(purl=purl, warnings=[warning])

        logger.info("deps.dev resolved %s to %s", purl, normalized_url)
        return Resolution(purl=purl, repository_url=normalized_url)
```

Примечание: `normalize_repository_url` импортируется из `.base` — это и есть re-export (символ доступен как `purl_resolver.resolver.depsdev.normalize_repository_url`).

- [ ] **Step 4: Run all depsdev tests**

Run: `.venv/bin/pytest tests/test_depsdev_resolver.py -v`
Expected: PASS (все классы включая TestUrlNormalization, TestNameMapping, TestFactory)

- [ ] **Step 5: Commit**

```bash
git add src/purl_resolver/resolver/depsdev.py tests/test_depsdev_resolver.py
git commit -m "Рефакторинг: DepsdevResolver наследует HttpApiResolver"
```

---

### Task 4: `EcosystemsResolver` → `HttpApiResolver`

**Files:**
- Modify: `src/purl_resolver/resolver/ecosystems.py`
- Modify: `tests/test_ecosystems_resolver.py`

**Interfaces:**
- Consumes: `HttpApiResolver`, `normalize_repository_url` из `resolver.base`
- Produces: `EcosystemsResolver(api_key=None, timeout=15.0, max_requests_per_second=2.0, retry_config=None)`, `name == "ecosyste.ms"`

- [ ] **Step 1: Write failing tests (normalization + non-JSON)**

Добавить в `tests/test_ecosystems_resolver.py` (при необходимости добавить `from purl_resolver.resolver.retry import RetryConfig` в импорты):

```python
class TestUrlNormalization:
    @pytest.mark.asyncio
    async def test_result_url_is_normalized(self) -> None:
        r = EcosystemsResolver(max_requests_per_second=0, retry_config=RetryConfig(max_attempts=1))
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"name": "pkg", "ecosystem": "pypi", "repository_url": "http://github.com/psf/requests.git"}
        ]
        mock_response.raise_for_status = MagicMock()
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_response
        r._client = mock_client
        r._min_interval = 0
        result = await r.resolve("pkg:pypi/requests")
        assert result.repository_url == "https://github.com/psf/requests"

    @pytest.mark.asyncio
    async def test_non_json_response_returns_warning(self) -> None:
        r = EcosystemsResolver(max_requests_per_second=0, retry_config=RetryConfig(max_attempts=1))
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("bad json")
        mock_response.raise_for_status = MagicMock()
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_response
        r._client = mock_client
        result = await r.resolve("pkg:pypi/requests")
        assert result.repository_url is None
        assert any("invalid response" in w for w in result.warnings)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_ecosystems_resolver.py::TestUrlNormalization -v`
Expected: FAIL (первый тест вернёт ненормализованный URL, второй — необработанный ValueError)

- [ ] **Step 3: Refactor `src/purl_resolver/resolver/ecosystems.py`**

```python
from __future__ import annotations

import logging

from .base import HttpApiResolver, normalize_repository_url
from .interface import Resolution
from .retry import RetryConfig

logger = logging.getLogger(__name__)

_API_URL = "https://packages.ecosyste.ms/api/v1/packages/lookup"


def select_repository_url(package_data: dict) -> str | None:
    candidates = [
        package_data.get("repository_url", ""),
        package_data.get("registry_url", ""),
        package_data.get("homepage", ""),
    ]

    for url in candidates:
        if not url or "repos.ecosyste.ms" in url:
            continue
        if "github.com" in url:
            return url

    for url in candidates:
        if url and "repos.ecosyste.ms" not in url:
            return url

    return None


class EcosystemsResolver(HttpApiResolver):

    def __init__(
        self,
        api_key: str | None = None,
        timeout: float = 15.0,
        max_requests_per_second: float = 2.0,
        retry_config: RetryConfig | None = None,
    ) -> None:
        super().__init__(
            timeout=timeout,
            max_requests_per_second=max_requests_per_second,
            retry_config=retry_config,
        )
        self._api_key = api_key

    @property
    def name(self) -> str:
        return "ecosyste.ms"

    async def resolve(self, purl: str) -> Resolution:
        _, error = self._validate_purl(purl)
        if error is not None:
            return Resolution(purl=purl, warnings=[error])

        params: dict[str, str] = {"purl": purl}
        if self._api_key:
            params["api_key"] = self._api_key

        data, error = await self._get_json(purl, _API_URL, label="ecosyste.ms", params=params)
        if error is not None:
            return Resolution(purl=purl, warnings=[error])
        logger.info("ecosyste.ms resolved %s successfully", purl)

        if not isinstance(data, list) or not data:
            return Resolution(purl=purl, warnings=[f"No package found on ecosyste.ms for {purl}"])

        package = data[0]
        repo_url = select_repository_url(package)
        if not repo_url:
            return Resolution(
                purl=purl,
                warnings=[f"No repository URL found on ecosyste.ms for {purl}"],
            )

        normalized_url = normalize_repository_url(repo_url)
        if normalized_url is None:
            return Resolution(
                purl=purl,
                warnings=[f"Invalid repository URL from ecosyste.ms for {purl}: {repo_url}"],
            )

        return Resolution(
            purl=purl,
            repository_url=normalized_url,
        )
```

- [ ] **Step 4: Run all ecosystems tests**

Run: `.venv/bin/pytest tests/test_ecosystems_resolver.py -v`
Expected: PASS (включая существующие TestRateLimiting — атрибуты `_client`/`_min_interval` сохранены)

- [ ] **Step 5: Commit**

```bash
git add src/purl_resolver/resolver/ecosystems.py tests/test_ecosystems_resolver.py
git commit -m "Рефакторинг: EcosystemsResolver наследует HttpApiResolver, нормализация URL"
```

---

### Task 5: `LibrariesIoResolver` → `HttpApiResolver`

**Files:**
- Modify: `src/purl_resolver/resolver/librariesio.py`
- Modify: `tests/test_librariesio_resolver.py`

**Interfaces:**
- Consumes: `HttpApiResolver`, `normalize_repository_url` из `resolver.base`
- Produces: `LibrariesIoResolver(api_key, timeout=15.0, retry_config=None)` (rate limit жёстко 1.0 внутри), `name == "libraries.io"`

- [ ] **Step 1: Write failing tests (normalization + non-JSON)**

Добавить в `tests/test_librariesio_resolver.py` (при необходимости добавить `from purl_resolver.resolver.retry import RetryConfig` в импорты):

```python
class TestUrlNormalization:
    @pytest.mark.asyncio
    async def test_result_url_is_normalized(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"name": "pkg", "repository_url": "git://github.com/psf/requests.git"}
        mock_response.raise_for_status = MagicMock()
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_response
        r = LibrariesIoResolver(api_key="test_key", retry_config=RetryConfig(max_attempts=1))
        r._client = mock_client
        r._min_interval = 0
        result = await r.resolve("pkg:pypi/requests")
        assert result.repository_url == "https://github.com/psf/requests"

    @pytest.mark.asyncio
    async def test_non_json_response_returns_warning(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("bad json")
        mock_response.raise_for_status = MagicMock()
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_response
        r = LibrariesIoResolver(api_key="test_key", retry_config=RetryConfig(max_attempts=1))
        r._client = mock_client
        r._min_interval = 0
        result = await r.resolve("pkg:pypi/requests")
        assert result.repository_url is None
        assert any("invalid response" in w for w in result.warnings)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_librariesio_resolver.py::TestUrlNormalization -v`
Expected: FAIL

- [ ] **Step 3: Refactor `src/purl_resolver/resolver/librariesio.py`**

```python
from __future__ import annotations

import logging
from urllib.parse import quote

from .base import HttpApiResolver, normalize_repository_url
from .interface import Resolution
from .retry import RetryConfig

logger = logging.getLogger(__name__)

_API_BASE = "https://libraries.io/api"


class LibrariesIoResolver(HttpApiResolver):

    ECOSYSTEM_MAP: dict[str, str] = {
        "cargo": "Cargo",
        "composer": "Packagist",
        "conda": "Conda",
        "cpan": "CPAN",
        "cran": "CRAN",
        "gem": "RubyGems",
        "generic": "GitHub",
        "golang": "Go",
        "hackage": "Hackage",
        "hex": "Hex",
        "maven": "Maven",
        "npm": "NPM",
        "nuget": "NuGet",
        "pub": "Pub",
        "pypi": "PyPI",
        "swift": "SwiftPM",
    }

    def __init__(
        self, api_key: str, timeout: float = 15.0, retry_config: RetryConfig | None = None
    ) -> None:
        super().__init__(
            timeout=timeout,
            max_requests_per_second=1.0,
            retry_config=retry_config,
        )
        self._api_key = api_key

    @property
    def name(self) -> str:
        return "libraries.io"

    async def resolve(self, purl: str) -> Resolution:
        components, error = self._validate_purl(purl)
        if error is not None:
            return Resolution(purl=purl, warnings=[error])
        assert components is not None

        platform = self.ECOSYSTEM_MAP.get(components.type)
        if platform is None:
            return Resolution(
                purl=purl,
                warnings=[f"Unsupported package type '{components.type}' for libraries.io"],
            )

        name = components.name
        encoded_name = quote(name, safe="")
        url = f"{_API_BASE}/{platform}/{encoded_name}"
        subject = f"{platform}/{name}"

        data, error = await self._get_json(
            purl,
            url,
            label="libraries.io",
            params={"api_key": self._api_key},
            subject=subject,
        )
        if error is not None:
            return Resolution(purl=purl, warnings=[error])
        logger.info("libraries.io resolved %s/%s successfully", platform, name)

        if not isinstance(data, dict):
            return Resolution(
                purl=purl,
                warnings=[f"Invalid response from libraries.io for {subject}"],
            )
        repo_url = data.get("repository_url", "")
        if not repo_url:
            return Resolution(
                purl=purl,
                warnings=[f"No repository found on libraries.io for {platform}/{name}"],
            )

        normalized_url = normalize_repository_url(repo_url)
        if normalized_url is None:
            return Resolution(
                purl=purl,
                warnings=[f"Invalid repository URL from libraries.io for {subject}: {repo_url}"],
            )

        return Resolution(
            purl=purl,
            repository_url=normalized_url,
        )
```

- [ ] **Step 4: Run all libraries.io tests**

Run: `.venv/bin/pytest tests/test_librariesio_resolver.py -v`
Expected: PASS (включая TestRateLimiting — `_min_interval` подменяется в тесте напрямую)

- [ ] **Step 5: Commit**

```bash
git add src/purl_resolver/resolver/librariesio.py tests/test_librariesio_resolver.py
git commit -m "Рефакторинг: LibrariesIoResolver наследует HttpApiResolver, нормализация URL"
```

---

### Task 6: `LlmResolver` → `HttpResolver` (SSRF, нормализация до HEAD)

**Files:**
- Modify: `src/purl_resolver/resolver/llm.py`
- Modify: `tests/test_llm_resolver.py`

**Interfaces:**
- Consumes: `HttpResolver`, `normalize_repository_url` из `resolver.base`
- Produces: `LlmResolver(base_url, api_key, model, attempts_count=2, timeout=60.0)`, `name == "llm"`, `async close()`; метод `_check_url` доступен (тесты мокают его на инстансе)

- [ ] **Step 1: Update `make_llm_resolver` and write failing tests**

В `tests/test_llm_resolver.py` заменить хелпер `make_llm_resolver` (строки 28–54):

```python
def make_llm_resolver(
    *,
    attempts_count: int = 2,
    status_codes: list[int] | None = None,
) -> tuple[LlmResolver, AsyncMock, AsyncMock]:
    create = AsyncMock()
    chat = MagicMock()
    chat.completions.create = create
    client = MagicMock()
    client.chat = chat

    check_url = AsyncMock()
    if status_codes is None:
        status_codes = [200]
    check_url.side_effect = [
        (code < 400, "" if code < 400 else f"URL returned HTTP {code}")
        for code in status_codes
    ]

    resolver = LlmResolver(
        base_url=_BASE_URL,
        api_key=_API_KEY,
        model=_MODEL,
        attempts_count=attempts_count,
    )
    resolver._client = client
    resolver._check_url = check_url
    return resolver, create, check_url
```

Добавить новые тесты:

```python
class TestUrlNormalization:
    @pytest.mark.asyncio
    async def test_url_normalized_before_head_check(self) -> None:
        resolver, create, check_url = make_llm_resolver(attempts_count=1)
        set_response(create, [success_json(_PURL, repo_url="http://github.com/psf/requests.git")])
        result = await resolver.resolve("pkg:pypi/requests@2.31.0")
        assert result.repository_url == "https://github.com/psf/requests"
        assert check_url.await_args.args[0] == "https://github.com/psf/requests"

    @pytest.mark.asyncio
    async def test_unnormalizable_url_retries(self) -> None:
        resolver, create, check_url = make_llm_resolver(attempts_count=2)
        set_response(create, [
            success_json(_PURL, repo_url="ftp://example.com/x"),
            success_json(_PURL),
        ])
        result = await resolver.resolve("pkg:pypi/requests@2.31.0")
        assert result.repository_url == "https://github.com/psf/requests"
        assert create.await_count == 2
        assert check_url.await_count == 1

    @pytest.mark.asyncio
    async def test_private_url_rejection_is_fed_back(self) -> None:
        resolver, create, check_url = make_llm_resolver(attempts_count=2)
        set_response(create, [success_json(_PURL), success_json(_PURL)])
        check_url.side_effect = [
            (False, "URL check for 'https://169.254.169.254/x' failed: Refusing HEAD request to private URL: https://169.254.169.254/x"),
            (True, ""),
        ]
        result = await resolver.resolve("pkg:pypi/requests@2.31.0")
        assert result.repository_url == "https://github.com/psf/requests"
        assert create.await_count == 2
        kwargs = create.await_args.kwargs
        assert any("Refusing HEAD request to private URL" in str(m["content"]) for m in kwargs["messages"])

    @pytest.mark.asyncio
    async def test_close_closes_openai_client(self) -> None:
        resolver, _, _ = make_llm_resolver()
        resolver._client = AsyncMock()
        await resolver.close()
        resolver._client.aclose.assert_awaited_once()
```

Обновить `TestHeadCheck.test_head_network_error_counts_as_failed_attempt` (строки 192–199) — сетевая ошибка теперь живёт внутри `_check_url` (покрыта в test_resolver_base), поэтому мок возвращает `(False, ...)`:

```python
    @pytest.mark.asyncio
    async def test_head_network_error_counts_as_failed_attempt(self) -> None:
        resolver, create, check_url = make_llm_resolver(attempts_count=2)
        check_url.side_effect = [(False, "URL check failed"), (False, "URL check failed")]
        set_response(create, [success_json(_PURL), success_json(_PURL)])
        result = await resolver.resolve("pkg:pypi/requests@2.31.0")
        assert result.repository_url is None
        assert create.await_count == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_llm_resolver.py -v`
Expected: FAIL — `AttributeError: 'LlmResolver' object has no attribute '_http_client'` (старый хелпер) и провалы новых тестов

- [ ] **Step 3: Refactor `src/purl_resolver/resolver/llm.py`**

`SYSTEM_PROMPT` и `_RETRY_FEEDBACK` сохраняются без изменений. Класс:

```python
class LlmResolver(HttpResolver):

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        attempts_count: int = 2,
        timeout: float = 60.0,
    ) -> None:
        super().__init__(timeout=timeout)
        self._base_url = base_url
        self._api_key = api_key
        self._model = model
        self._attempts_count = attempts_count
        self._client = AsyncOpenAI(base_url=base_url, api_key=api_key, timeout=timeout)

    @property
    def name(self) -> str:
        return "llm"

    async def resolve(self, purl: str) -> Resolution:
        _, error = self._validate_purl(purl)
        if error is not None:
            return Resolution(purl=purl, warnings=[error])

        warnings: list[str] = []
        messages: list[dict[str, str]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Find the source code repository for the package with PURL: {purl}\n"
                    'Respond with the JSON object in the required format.'
                ),
            },
        ]

        for attempt in range(1, self._attempts_count + 1):
            logger.info("llm resolving %s (attempt %d/%d)", purl, attempt, self._attempts_count)
            content = await self._request(messages)
            if content is None:
                self._record_failure(warnings, messages, attempt, purl, "LLM request failed")
                continue

            repo_url, err = self._validate_response(content, purl)
            if err is not None:
                self._record_failure(warnings, messages, attempt, purl, err)
                continue

            normalized_url = normalize_repository_url(repo_url)
            if normalized_url is None:
                self._record_failure(
                    warnings, messages, attempt, purl,
                    f"repository_url '{repo_url}' is not a valid https URL",
                )
                continue

            ok, head_error = await self._check_url(normalized_url)
            if not ok:
                self._record_failure(warnings, messages, attempt, purl, head_error)
                continue

            logger.info("llm resolved %s to %s", purl, normalized_url)
            return Resolution(purl=purl, repository_url=normalized_url)

        return Resolution(purl=purl, warnings=warnings)

    def _record_failure(self, warnings, messages, attempt, purl, reason) -> None:
        # без изменений относительно текущего кода (llm.py:100-114)

    async def _request(self, messages) -> str | None:
        # без изменений (llm.py:116-125)

    def _validate_response(self, content: str | None, purl: str) -> tuple[str | None, str | None]:
        if not content:
            return None, "empty LLM response"
        data = self._parse_json(content)
        if not isinstance(data, dict):
            return None, "response is not a JSON object"
        if data.get("purl") != purl:
            return None, f"returned purl '{data.get('purl')}' does not match '{purl}'"
        status = data.get("status")
        if status not in ("success", "failure"):
            return None, f"invalid status '{status}'"
        if status == "failure":
            return None, "LLM reported failure for the purl"
        repo_url = data.get("repository_url")
        if not isinstance(repo_url, str) or not repo_url:
            return None, "repository_url is missing or empty"
        return repo_url, None

    @staticmethod
    def _parse_json(content: str) -> object:
        # без изменений (llm.py:148-163)

    async def close(self) -> None:
        await self._client.aclose()
```

Изменения относительно текущего файла: наследование `HttpResolver` вместо `Resolver`, `super().__init__(timeout=timeout)`, удалён `_http_client` (и `httpx.AsyncClient` для него), удалён urlparse-чек схемы из `_validate_response`, добавлена нормализация перед `_check_url`, добавлен `close()`. Импорты: убрать `from urllib.parse import urlparse` и `from ..purl_utils import PurlValidationError, validate` (не используются — валидацию даёт `_validate_purl` из базы); **сохранить** `import httpx` (нужен в `_request` для `httpx.HTTPError`); добавить `from .base import HttpResolver, normalize_repository_url`.

- [ ] **Step 4: Run all llm tests**

Run: `.venv/bin/pytest tests/test_llm_resolver.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/purl_resolver/resolver/llm.py tests/test_llm_resolver.py
git commit -m "Рефакторинг: LlmResolver наследует HttpResolver, SSRF-защита HEAD-проверки"
```

---

### Task 7: `Purl2RepoResolver` — нормализация на seam

**Files:**
- Modify: `src/purl_resolver/resolver/purl2repo.py`
- Modify: `tests/test_purl2repo_resolver.py`

**Interfaces:**
- Consumes: `normalize_repository_url` из `resolver.base` (модульная функция)
- Produces: без изменений внешнего контракта; валидационные исключения (InvalidPurlError/UpstreamError) сохраняются

- [ ] **Step 1: Write failing tests**

Добавить в `tests/test_purl2repo_resolver.py` (импорт `MagicMock` в начало файла):

```python
class TestPurl2RepoNormalization:
    @pytest.mark.asyncio
    async def test_success_url_is_normalized(self, resolver: Purl2RepoResolver) -> None:
        with patch(
            "purl_resolver.resolver.purl2repo.purl2repo_resolve",
            return_value=MagicMock(
                repository_url="git://github.com/psf/requests.git",
                warnings=[],
            ),
        ):
            result = await resolver.resolve("pkg:pypi/requests@2.31.0")
        assert result.repository_url == "https://github.com/psf/requests"

    @pytest.mark.asyncio
    async def test_unnormalizable_url_falls_through(self, resolver: Purl2RepoResolver) -> None:
        with patch(
            "purl_resolver.resolver.purl2repo.purl2repo_resolve",
            return_value=MagicMock(
                repository_url="javascript:alert(1)",
                warnings=[],
            ),
        ):
            result = await resolver.resolve("pkg:pypi/requests@2.31.0")
        assert result.repository_url is None
        assert any("Invalid repository URL" in w for w in result.warnings)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_purl2repo_resolver.py::TestPurl2RepoNormalization -v`
Expected: FAIL (URL не нормализован)

- [ ] **Step 3: Modify `src/purl_resolver/resolver/purl2repo.py`**

1. Добавить импорт:
   ```python
   from .base import normalize_repository_url
   ```
2. Заменить финальный `return` (строки 71–75):
   ```python
   repo_url = result.repository_url
   if repo_url is not None:
       normalized_url = normalize_repository_url(repo_url)
       if normalized_url is None:
           return Resolution(
               purl=purl,
               warnings=[f"Invalid repository URL from purl2repo for {purl}: {repo_url}"],
           )
       repo_url = normalized_url
   return Resolution(
       purl=purl,
       repository_url=repo_url,
       warnings=list(result.warnings),
   )
   ```

Всё остальное (маппинг исключений, `asyncio.to_thread`, конструктор) — без изменений.

- [ ] **Step 4: Run all purl2repo tests**

Run: `.venv/bin/pytest tests/test_purl2repo_resolver.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/purl_resolver/resolver/purl2repo.py tests/test_purl2repo_resolver.py
git commit -m "Рефакторинг: нормализация repository URL в Purl2RepoResolver"
```

---

### Task 8: Lifecycle — закрытие клиентов при rebuild и teardown

**Files:**
- Modify: `src/purl_resolver/routes/settings.py`
- Modify: `src/purl_resolver/main.py`
- Modify: `tests/test_api.py`

**Interfaces:**
- Consumes: `resolver.close()` у `HttpApiResolver` (Task 2) и `LlmResolver` (Task 6); duck-typing `getattr(resolver, "close", None)`
- Produces: async `_rebuild_resolvers(request)` в routes/settings.py; teardown-закрытие в main.py

- [ ] **Step 1: Write failing test (old resolvers closed on PATCH)**

Добавить в `tests/test_api.py`, в класс `TestResolverChainRebuild`:

```python
    def test_patch_settings_closes_old_resolvers(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        from purl_resolver.resolver.base import HttpApiResolver

        client.app.state.settings_store = SettingsStore(path=tmp_path / "settings.json")
        with (
            patch.object(HttpApiResolver, "close", new=AsyncMock()) as close_mock,
        ):
            response = client.patch("/api/v1/settings", json={
                "librariesio_enabled": False,
                "ecosystems_enabled": False,
            })
        assert response.status_code == 200
        assert close_mock.await_count >= 2  # depsdev + ecosystems (стартовая цепочка)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_api.py::TestResolverChainRebuild::test_patch_settings_closes_old_resolvers -v`
Expected: FAIL — `close_mock.await_count == 0`

- [ ] **Step 3: Modify `src/purl_resolver/routes/settings.py`**

Заменить `_rebuild_resolvers` (строки 61–68) на async-версию с закрытием:

```python
async def _rebuild_resolvers(request: Request) -> None:
    store: SettingsStore = request.app.state.settings_store
    app_settings = store.load()
    old_resolvers = request.app.state.resolvers
    resolvers = build_resolvers(settings, app_settings)
    for old in old_resolvers:
        close = getattr(old, "close", None)
        if close is not None:
            await close()
    request.app.state.resolvers = resolvers
    service = getattr(request.app.state, "resolution_service", None)
    if service is not None:
        service.set_resolvers(resolvers)
```

Обновить вызов в `update_settings` (строка 139):

```python
    await _rebuild_resolvers(request)
```

- [ ] **Step 4: Modify `src/purl_resolver/main.py` (teardown)**

В блоке `finally` (строки 105–110) добавить закрытие резолверов перед `pool.close()`:

```python
    finally:
        expire_task.cancel()
        if app.state.job_manager is not None:
            await app.state.job_manager.stop()
        for resolver in getattr(app.state, "resolvers", []):
            close = getattr(resolver, "close", None)
            if close is not None:
                await close()
        if pool is not None:
            await pool.close()
```

- [ ] **Step 5: Run affected tests**

Run: `.venv/bin/pytest tests/test_api.py -v`
Expected: PASS (включая существующий `TestResolverChainRebuild` — PATCH работает через HTTP, async-изменение внутреннее)

- [ ] **Step 6: Commit**

```bash
git add src/purl_resolver/routes/settings.py src/purl_resolver/main.py tests/test_api.py
git commit -m "Рефакторинг: закрывать клиенты резолверов при пересборке цепочки и завершении"
```

---

### Task 9: Документация и полный прогон

**Files:**
- Create: `specs/decisions/0009-http-resolver-base.md`
- Modify: `specs/architecture/layers.md`, `specs/INDEX.md`

**Interfaces:** без кода

- [ ] **Step 1: Create ADR `specs/decisions/0009-http-resolver-base.md`**

```markdown
# ADR-0009: Shared HTTP resolver base module

## Context

Four network resolvers (depsdev, ecosyste.ms, libraries.io, llm) duplicated httpx client creation (never closed), rate limiting, error-to-warning mapping, and PURL validation boilerplate. The LLM resolver's HEAD check lacked the SSRF guard that url_validator had. URL normalization existed only in depsdev.

## Decision

Introduce a two-level hierarchy in `resolver/base.py`: `HttpResolver` (stateless helpers: `_validate_purl`, `_check_url`) and `HttpApiResolver(HttpResolver)` (httpx client, rate limiter, `RetryHelper`, error ladder `_get_json`, `close()`). The three JSON-API resolvers inherit `HttpApiResolver`; `LlmResolver` inherits `HttpResolver` and keeps its own generation-retry attempts loop. SSRF-guarded HEAD lives in `url_check.py`, shared with `url_validator`. URL normalization (`normalize_repository_url`) is a module-level function applied chain-wide, including `Purl2RepoResolver`. Clients are closed via duck-typing on settings rebuild and lifespan teardown.

## Rationale

- Transport retry (`RetryHelper`) and generation retry (LLM attempts loop) are different regimes and stay structurally separate — deterministic resolvers never re-run analysis.
- Two consumers of the SSRF-guarded HEAD (validator and LLM) justify the shared seam.
- One normalization policy keeps stored repository URLs uniform across the whole chain.

## Consequences

- Resolver chain order and the `Resolver` ABC are unchanged.
- Fresh resolutions from ecosyste.ms/libraries.io/llm/purl2repo store normalized URLs (https, no `.git`, no `/tree/`); existing DB rows are untouched.
- LLM HEAD checks are SSRF-guarded; private-URL rejection is fed back into the prompt.
- Non-JSON API responses yield warnings instead of unhandled `ValueError`.
```

- [ ] **Step 2: Update `specs/architecture/layers.md`**

В секции Resolver Layer (строка 232):
1. Добавить после «`Resolver Layer` (`resolver/`)»: модули `base.py` (`HttpResolver` — stateless-хелперы `_validate_purl`/`_check_url`; `HttpApiResolver(HttpResolver)` — httpx client, rate limiter, `RetryHelper`, `_get_json` error-ladder, `close()`) и `url_check.py` (SSRF-защищённый HEAD, общий с URL Validator).
2. Обновить описания резолверов: `DepsdevResolver`/`EcosystemsResolver`/`LibrariesIoResolver` наследуют `HttpApiResolver`, `LlmResolver` наследует `HttpResolver`; нормализация URL применяется во всех резолверах цепочки включая purl2repo.
3. Импорт-правила: Resolver Layer импортирует `url_check`; URL Validator импортирует `url_check` (строка 233 — добавить).
4. URL Validator section (строки 353–365): отметить, что SSRF-guard и HEAD вынесены в `url_check.py`.

- [ ] **Step 3: Update `specs/INDEX.md`**

В Dependency Graph добавить строку после 0008:
```
decisions/0009-http-resolver-base.md
```
В Directory Listing decisions добавить:
```
    ├── 0009-http-resolver-base.md               — shared HTTP resolver base module
```

- [ ] **Step 4: Full test run**

Run: `.venv/bin/pytest tests -q --ignore=tests/e2e`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add specs/decisions/0009-http-resolver-base.md specs/architecture/layers.md specs/INDEX.md
git commit -m "Документация: ADR-0009, layers.md и INDEX.md для HTTP resolver base"
```
