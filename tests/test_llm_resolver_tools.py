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
    html = (
        "<html><head><style>x{}</style></head><body>"
        "<script>bad()</script><p>Hello  world</p></body></html>"
    )
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


@pytest.mark.asyncio
async def test_web_fetch_unknown_charset_returns_error(monkeypatch) -> None:
    resolver = make_resolver()
    monkeypatch.setattr(
        "purl_resolver.resolver.llm.socket.getaddrinfo",
        lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 0))],
    )
    response = httpx.Response(
        200,
        text="<p>hi</p>",
        headers={"Content-Type": "text/html; charset=bogus"},
    )
    resolver._fetch_client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: response)
    )
    out = await resolver._web_fetch("https://public.example/")
    assert out.startswith("error:")


@pytest.mark.asyncio
async def test_web_fetch_malformed_url_returns_error() -> None:
    resolver = make_resolver()
    out = await resolver._web_fetch("http://[::1")
    assert out.startswith("error:")
