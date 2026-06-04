from __future__ import annotations

import time
from unittest.mock import MagicMock

import httpx
import pytest

from purl_resolver.resolver.interface import Resolution
from purl_resolver.resolver.librariesio import LibrariesIoResolver


class TestEcosystemMapping:
    def test_pypi_maps_to_pyPI(self) -> None:
        assert LibrariesIoResolver.ECOSYSTEM_MAP["pypi"] == "PyPI"

    def test_npm_maps_to_NPM(self) -> None:
        assert LibrariesIoResolver.ECOSYSTEM_MAP["npm"] == "NPM"

    def test_nuget_maps_to_NuGet(self) -> None:
        assert LibrariesIoResolver.ECOSYSTEM_MAP["nuget"] == "NuGet"

    def test_gem_maps_to_RubyGems(self) -> None:
        assert LibrariesIoResolver.ECOSYSTEM_MAP["gem"] == "RubyGems"

    def test_golang_maps_to_Go(self) -> None:
        assert LibrariesIoResolver.ECOSYSTEM_MAP["golang"] == "Go"

    def test_maven_maps_to_Maven(self) -> None:
        assert LibrariesIoResolver.ECOSYSTEM_MAP["maven"] == "Maven"

    def test_cargo_maps_to_Cargo(self) -> None:
        assert LibrariesIoResolver.ECOSYSTEM_MAP["cargo"] == "Cargo"

    def test_unknown_type_returns_none(self) -> None:
        assert LibrariesIoResolver.ECOSYSTEM_MAP.get("unknown") is None


class TestResolverName:
    def test_name_is_libraries_io(self) -> None:
        r = LibrariesIoResolver(api_key="test_key")
        assert r.name == "libraries.io"


class TestResolveUnknownType:
    def test_unknown_purl_type_returns_warning(self) -> None:
        r = LibrariesIoResolver(api_key="test_key")
        result = r.resolve("pkg:deb/debian/libssl")
        assert result.repository_url is None
        assert len(result.warnings) > 0
        assert "Unsupported" in result.warnings[0] or "unsupported" in result.warnings[0].lower()


class TestResolveSuccess:
    def test_successful_resolution(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "name": "requests",
            "repository": {
                "url": "https://github.com/psf/requests",
                "homepage": "https://requests.readthedocs.io",
            },
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_response

        r = LibrariesIoResolver(api_key="test_key")
        r._client = mock_client

        result = r.resolve("pkg:pypi/requests@2.31.0")
        assert result.repository_url == "https://github.com/psf/requests"
        assert result.repository_kind == "source"
        assert result.confidence == "medium"
        assert "libraries.io:PyPI/requests" in result.evidence


class TestResolveNoRepository:
    def test_no_repository_in_response(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "name": "some-package",
            "repository": None,
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_response

        r = LibrariesIoResolver(api_key="test_key")
        r._client = mock_client

        result = r.resolve("pkg:pypi/some-package")
        assert result.repository_url is None
        assert any("no repository" in w.lower() for w in result.warnings)


class TestResolveErrors:
    def test_timeout_returns_warning(self) -> None:
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.side_effect = httpx.TimeoutException("timeout")

        r = LibrariesIoResolver(api_key="test_key")
        r._client = mock_client

        result = r.resolve("pkg:pypi/requests")
        assert result.repository_url is None
        assert any("timeout" in w.lower() for w in result.warnings)

    def test_429_returns_warning(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "rate limited", request=MagicMock(), response=mock_response
        )

        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_response

        r = LibrariesIoResolver(api_key="test_key")
        r._client = mock_client

        result = r.resolve("pkg:pypi/requests")
        assert result.repository_url is None
        assert any("rate" in w.lower() or "429" in w for w in result.warnings)

    def test_5xx_returns_warning(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "server error", request=MagicMock(), response=mock_response
        )

        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_response

        r = LibrariesIoResolver(api_key="test_key")
        r._client = mock_client

        result = r.resolve("pkg:pypi/requests")
        assert result.repository_url is None
        assert any("500" in w or "error" in w.lower() for w in result.warnings)

    def test_network_error_returns_warning(self) -> None:
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.side_effect = httpx.ConnectError("connection refused")

        r = LibrariesIoResolver(api_key="test_key")
        r._client = mock_client

        result = r.resolve("pkg:pypi/requests")
        assert result.repository_url is None
        assert len(result.warnings) > 0


class TestRateLimiting:
    def test_minimum_interval_between_requests(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"name": "pkg", "repository": {"url": "https://example.com"}}
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = mock_response

        r = LibrariesIoResolver(api_key="test_key")
        r._client = mock_client
        r._min_interval = 0.1  # short interval for testing

        start = time.monotonic()
        r.resolve("pkg:pypi/requests")
        r.resolve("pkg:npm/express")
        elapsed = time.monotonic() - start

        assert elapsed >= 0.1  # at least min_interval between calls
