from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest

from purl_resolver.resolver.interface import Resolution
from purl_resolver.resolver.librariesio import LibrariesIoResolver
from purl_resolver.resolver.purl2repo import Purl2RepoResolver
from purl_resolver.service import resolve_purl
from purl_resolver.storage.inmemory import InMemoryCache


class TestResolverChain:
    @pytest.mark.asyncio
    async def test_purl2repo_fails_librariesio_succeeds(self) -> None:
        purl2repo = MagicMock(spec=Purl2RepoResolver)
        purl2repo.name = "purl2repo"
        purl2repo.resolve.return_value = Resolution(
            purl="pkg:pypi/requests",
            warnings=["Unsupported ecosystem"],
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "name": "requests",
            "repository": {"url": "https://github.com/psf/requests"},
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_response

        lio = LibrariesIoResolver(api_key="test_key")
        lio._client = mock_client

        storage = InMemoryCache()
        resolvers = [purl2repo, lio]

        result = await resolve_purl(
            "pkg:pypi/requests@2.31.0",
            storage,
            resolvers,
        )

        assert result.response is not None
        assert result.response.repository_url == "https://github.com/psf/requests"
        assert result.response.resolver == "libraries.io"

    @pytest.mark.asyncio
    async def test_both_fail_returns_warnings(self) -> None:
        purl2repo = MagicMock(spec=Purl2RepoResolver)
        purl2repo.name = "purl2repo"
        purl2repo.resolve.return_value = Resolution(
            purl="pkg:deb/debian/libssl",
            warnings=["Unsupported ecosystem"],
        )

        lio = MagicMock(spec=LibrariesIoResolver)
        lio.name = "libraries.io"
        lio.resolve.return_value = Resolution(
            purl="pkg:deb/debian/libssl",
            warnings=["Unsupported package type 'deb' for libraries.io"],
        )

        storage = InMemoryCache()
        resolvers = [purl2repo, lio]

        result = await resolve_purl(
            "pkg:deb/debian/libssl",
            storage,
            resolvers,
        )

        assert result.response is not None
        assert result.response.repository_url is None
        assert len(result.response.warnings) > 0

    @pytest.mark.asyncio
    async def test_librariesio_error_does_not_interrupt_chain(self) -> None:
        purl2repo = MagicMock(spec=Purl2RepoResolver)
        purl2repo.name = "purl2repo"
        purl2repo.resolve.return_value = Resolution(
            purl="pkg:pypi/requests",
            warnings=["Could not resolve"],
        )

        lio = MagicMock(spec=LibrariesIoResolver)
        lio.name = "libraries.io"
        lio.resolve.return_value = Resolution(
            purl="pkg:pypi/requests",
            warnings=["libraries.io timeout for PyPI/requests"],
        )

        storage = InMemoryCache()
        resolvers = [purl2repo, lio]

        result = await resolve_purl(
            "pkg:pypi/requests@2.31.0",
            storage,
            resolvers,
        )

        assert result.response is not None
        assert result.response.repository_url is None
        assert any("No resolver found" in w for w in result.response.warnings)
