from purl_resolver.config import SearxngSettings


def test_searxng_default_url() -> None:
    assert SearxngSettings().url == "http://searxng:8080"


def test_searxng_env_override(monkeypatch) -> None:
    monkeypatch.setenv("SEARXNG_URL", "http://custom:9999")
    assert SearxngSettings().url == "http://custom:9999"
