from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from purl_resolver.resolver.ecosystems import EcosystemsResolver, select_repository_url
from purl_resolver.resolver.retry import RetryConfig


class TestSelectRepositoryUrl:
    def test_repository_url_with_github(self) -> None:
        data = {"repository_url": "https://github.com/psf/requests", "registry_url": "https://pypi.org/project/requests/"}
        assert select_repository_url(data) == "https://github.com/psf/requests"

    def test_registry_url_when_no_repository(self) -> None:
        data = {"repository_url": "", "registry_url": "https://pypi.org/project/requests/"}
        assert select_repository_url(data) == "https://pypi.org/project/requests/"

    def test_homepage_fallback(self) -> None:
        data = {"repository_url": "", "registry_url": "", "homepage": "https://requests.readthedocs.io"}
        assert select_repository_url(data) == "https://requests.readthedocs.io"

    def test_skip_repos_ecosyste_ms(self) -> None:
        data = {"repository_url": "https://repos.ecosyste.ms/psf/requests", "homepage": "https://example.com"}
        assert select_repository_url(data) == "https://example.com"

    def test_github_preferred_over_other(self) -> None:
        data = {"repository_url": "https://gitlab.com/foo/bar", "homepage": "https://github.com/foo/bar"}
        assert select_repository_url(data) == "https://github.com/foo/bar"

    def test_empty_data_returns_none(self) -> None:
        assert select_repository_url({}) is None

    def test_all_ecosyste_ms_urls_returns_none(self) -> None:
        data = {"repository_url": "https://repos.ecosyste.ms/foo", "homepage": "https://repos.ecosyste.ms/bar"}
        assert select_repository_url(data) is None


class TestResolverName:
    def test_name(self) -> None:
        r = EcosystemsResolver()
        assert r.name == "ecosyste.ms"


class TestResolveSuccess:
    @pytest.mark.asyncio
    async def test_successful_resolution(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "name": "requests",
                "ecosystem": "pypi",
                "repository_url": "https://github.com/psf/requests",
                "registry_url": "https://pypi.org/project/requests/",
                "homepage": None,
            }
        ]
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_response

        r = EcosystemsResolver()
        r._client = mock_client

        result = await r.resolve("pkg:pypi/requests@2.31.0")
        assert result.repository_url == "https://github.com/psf/requests"


class TestResolveNoPackage:
    @pytest.mark.asyncio
    async def test_empty_array_returns_warning(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_response

        r = EcosystemsResolver()
        r._client = mock_client

        result = await r.resolve("pkg:pypi/nonexistent")
        assert result.repository_url is None
        assert any("no package" in w.lower() for w in result.warnings)


class TestResolveNoRepositoryUrl:
    @pytest.mark.asyncio
    async def test_no_repository_url_in_response(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "name": "some-pkg",
                "ecosystem": "pypi",
                "repository_url": "",
                "registry_url": "",
                "homepage": "",
            }
        ]
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_response

        r = EcosystemsResolver()
        r._client = mock_client

        result = await r.resolve("pkg:pypi/some-pkg")
        assert result.repository_url is None
        assert any("no repository" in w.lower() for w in result.warnings)


class TestResolveErrors:
    @pytest.mark.asyncio
    async def test_timeout_returns_warning(self) -> None:
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.side_effect = httpx.TimeoutException("timeout")

        r = EcosystemsResolver(retry_config=RetryConfig(max_attempts=1))
        r._client = mock_client

        result = await r.resolve("pkg:pypi/requests")
        assert result.repository_url is None
        assert any("timeout" in w.lower() for w in result.warnings)

    @pytest.mark.asyncio
    async def test_5xx_returns_warning(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "server error", request=MagicMock(), response=mock_response
        )

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_response

        r = EcosystemsResolver(retry_config=RetryConfig(max_attempts=1))
        r._client = mock_client

        result = await r.resolve("pkg:pypi/requests")
        assert result.repository_url is None
        assert any("500" in w or "error" in w.lower() for w in result.warnings)

    @pytest.mark.asyncio
    async def test_4xx_returns_warning(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "not found", request=MagicMock(), response=mock_response
        )

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_response

        r = EcosystemsResolver(retry_config=RetryConfig(max_attempts=1))
        r._client = mock_client

        result = await r.resolve("pkg:pypi/requests")
        assert result.repository_url is None
        assert any("404" in w or "error" in w.lower() for w in result.warnings)

    @pytest.mark.asyncio
    async def test_network_error_returns_warning(self) -> None:
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.side_effect = httpx.ConnectError("connection refused")

        r = EcosystemsResolver(retry_config=RetryConfig(max_attempts=1))
        r._client = mock_client

        result = await r.resolve("pkg:pypi/requests")
        assert result.repository_url is None
        assert len(result.warnings) > 0


class TestApiKey:
    @pytest.mark.asyncio
    async def test_api_key_passed_in_params(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"name": "pkg", "ecosystem": "pypi", "repository_url": "https://github.com/a/b"}]
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_response

        r = EcosystemsResolver(api_key="test_key_123")
        r._client = mock_client

        await r.resolve("pkg:pypi/pkg")
        call_kwargs = mock_client.get.call_args
        assert call_kwargs[1]["params"]["api_key"] == "test_key_123"

    @pytest.mark.asyncio
    async def test_no_key_no_api_key_param(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"name": "pkg", "ecosystem": "pypi", "repository_url": "https://github.com/a/b"}]
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_response

        r = EcosystemsResolver()
        r._client = mock_client

        await r.resolve("pkg:pypi/pkg")
        call_kwargs = mock_client.get.call_args
        assert "api_key" not in call_kwargs[1]["params"]


class TestInvalidPurl:
    @pytest.mark.asyncio
    async def test_invalid_purl_returns_warning(self) -> None:
        r = EcosystemsResolver()
        result = await r.resolve("not-a-valid-purl")
        assert result.repository_url is None
        assert any("invalid" in w.lower() for w in result.warnings)


class TestRateLimiting:
    @pytest.mark.asyncio
    async def test_minimum_interval_between_requests(self) -> None:
        r = EcosystemsResolver(max_requests_per_second=10.0)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"name": "pkg", "ecosystem": "pypi", "repository_url": "https://github.com/a/b"}]
        mock_response.raise_for_status = MagicMock()
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_response
        r._client = mock_client

        t0 = time.monotonic()
        await r.resolve("pkg:pypi/a")
        await r.resolve("pkg:pypi/b")
        elapsed = time.monotonic() - t0
        assert elapsed >= 0.09  # 1/10 * 2 requests = 0.2s min, but allow some margin

    @pytest.mark.asyncio
    async def test_no_rate_limit_when_max_requests_per_second_zero(self) -> None:
        r = EcosystemsResolver(max_requests_per_second=0)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"name": "pkg", "ecosystem": "pypi", "repository_url": "https://github.com/a/b"}]
        mock_response.raise_for_status = MagicMock()
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_response
        r._client = mock_client

        t0 = time.monotonic()
        await r.resolve("pkg:pypi/a")
        await r.resolve("pkg:pypi/b")
        elapsed = time.monotonic() - t0
        assert elapsed < 0.1  # no sleep between requests

    @pytest.mark.asyncio
    async def test_constructor_accepts_max_requests_per_second(self) -> None:
        r = EcosystemsResolver(max_requests_per_second=5.0)
        assert r._min_interval == 0.2
