from __future__ import annotations

import pytest

from purl_resolver.resolver.apk import ApkResolver
from purl_resolver.resolver.interface import Resolution

pytestmark = pytest.mark.asyncio


async def test_resolve_apk_purl():
    resolver = ApkResolver()
    result = await resolver.resolve("pkg:apk/alpine/curl@7.83.0-r0")
    assert result.repository_url == "https://github.com/alpinelinux/aports/"
    assert result.purl == "pkg:apk/alpine/curl@7.83.0-r0"


async def test_resolve_apk_with_qualifiers():
    resolver = ApkResolver()
    result = await resolver.resolve("pkg:apk/alpine/apk@2.12.9-r3?arch=x86")
    assert result.repository_url == "https://github.com/alpinelinux/aports/"


async def test_resolve_non_apk_type():
    resolver = ApkResolver()
    result = await resolver.resolve("pkg:pypi/requests@2.31.0")
    assert result.repository_url is None
    assert any("Unsupported package type" in w for w in result.warnings)


async def test_resolve_invalid_purl():
    resolver = ApkResolver()
    result = await resolver.resolve("not-a-purl")
    assert result.repository_url is None
    assert any("Invalid PURL" in w for w in result.warnings)


def test_resolver_name():
    resolver = ApkResolver()
    assert resolver.name == "apk"
