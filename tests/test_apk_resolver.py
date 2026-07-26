from __future__ import annotations

import pytest

from purl_resolver.resolver.apk import ApkResolver
from purl_resolver.resolver.interface import Resolution

@pytest.mark.asyncio
async def test_resolve_apk_purl():
    resolver = ApkResolver()
    result = await resolver.resolve("pkg:apk/alpine/curl@7.83.0-r0")
    assert result.repository_url == "https://github.com/alpinelinux/aports"
    assert result.purl == "pkg:apk/alpine/curl@7.83.0-r0"


@pytest.mark.asyncio
async def test_resolve_apk_with_qualifiers():
    resolver = ApkResolver()
    result = await resolver.resolve("pkg:apk/alpine/apk@2.12.9-r3?arch=x86")
    assert result.repository_url == "https://github.com/alpinelinux/aports"


@pytest.mark.asyncio
async def test_resolve_non_apk_type():
    resolver = ApkResolver()
    result = await resolver.resolve("pkg:pypi/requests@2.31.0")
    assert result.repository_url is None
    assert any("Unsupported package type" in w for w in result.warnings)


@pytest.mark.asyncio
async def test_resolve_invalid_purl():
    resolver = ApkResolver()
    result = await resolver.resolve("not-a-purl")
    assert result.repository_url is None
    assert any("Invalid PURL" in w for w in result.warnings)


def test_resolver_name():
    resolver = ApkResolver()
    assert resolver.name == "apk"


@pytest.mark.asyncio
async def test_apk_resolver_is_last_in_chain(monkeypatch):
    from purl_resolver.settings_store import AppSettings
    from purl_resolver.config import Settings
    from purl_resolver.resolver.factory import build_resolvers

    app_settings = AppSettings(
        ecosystems_enabled=False,
        librariesio_enabled=False,
        apk_resolver_enabled=True,
    )
    resolvers = build_resolvers(Settings(), app_settings)
    assert resolvers[-1].name == "apk"
