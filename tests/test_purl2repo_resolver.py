from __future__ import annotations

import pytest

from purl_resolver.resolver.interface import InvalidPurlError, Resolution
from purl_resolver.resolver.purl2repo import Purl2RepoResolver


@pytest.fixture
def resolver() -> Purl2RepoResolver:
    return Purl2RepoResolver(timeout=5.0, use_cache=False, no_network=True)


class TestPurl2RepoUnsupportedType:

    @pytest.mark.asyncio
    async def test_unsupported_type_returns_no_result(self, resolver: Purl2RepoResolver):
        result = await resolver.resolve("pkg:apk/alpine/nginx")
        assert result.repository_url is None
        assert any("unsupported" in w.lower() or "apk" in w.lower() for w in result.warnings)

    @pytest.mark.asyncio
    async def test_unsupported_type_does_not_raise(self, resolver: Purl2RepoResolver):
        result = await resolver.resolve("pkg:deb/debian/libc6")
        assert isinstance(result, Resolution)

    @pytest.mark.asyncio
    async def test_still_raises_for_truly_invalid_purl(self, resolver: Purl2RepoResolver):
        with pytest.raises(InvalidPurlError):
            await resolver.resolve("not-a-purl")
