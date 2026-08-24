from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from purl_resolver.url_validator import (
    UrlValidationOutput,
    UrlValidationResult,
    ensure_connectivity,
    validate_url,
)


def _mock_response(status_code: int = 200, headers: dict | None = None) -> AsyncMock:
    resp = AsyncMock()
    resp.status_code = status_code
    resp.headers = headers or {}
    resp.url = "https://github.com/psf/requests"
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


def _mock_head(status_code: int = 200, headers: dict | None = None):
    return _mock_response(status_code, headers)


class TestValidateUrl:
    @pytest.mark.asyncio
    async def test_valid_url(self):
        with (
            patch(
                "purl_resolver.url_validator._head_request",
                new_callable=AsyncMock,
            ) as mock_head,
            patch(
                "purl_resolver.url_validator._check_vcs",
                new_callable=AsyncMock,
                return_value=True,
            ),
        ):
            mock_head.return_value = _mock_head(200)
            result = await validate_url("https://github.com/psf/requests", timeout=5)
            assert result.result == UrlValidationResult.VALID

    @pytest.mark.asyncio
    async def test_head_404_ignored_validation_proceeds(self):
        with (
            patch(
                "purl_resolver.url_validator._head_request",
                new_callable=AsyncMock,
            ) as mock_head,
            patch(
                "purl_resolver.url_validator._check_vcs",
                new_callable=AsyncMock,
                return_value=True,
            ),
        ):
            mock_head.return_value = _mock_head(404)
            result = await validate_url("https://github.com/deleted/repo", timeout=5)
            assert result.result == UrlValidationResult.VALID

    @pytest.mark.asyncio
    async def test_head_403_without_token_ignored(self):
        with (
            patch(
                "purl_resolver.url_validator._head_request",
                new_callable=AsyncMock,
            ) as mock_head,
            patch(
                "purl_resolver.url_validator._check_vcs",
                new_callable=AsyncMock,
                return_value=True,
            ),
        ):
            mock_head.return_value = _mock_head(403, {"x-github-media-type": "v3"})
            result = await validate_url("https://github.com/private/repo", timeout=5)
            assert result.result == UrlValidationResult.VALID

    @pytest.mark.asyncio
    async def test_head_connection_error_falls_back_and_vcs_probes(self):
        with (
            patch(
                "purl_resolver.url_validator._head_request",
                new_callable=AsyncMock,
            ) as mock_head,
            patch(
                "purl_resolver.url_validator._check_vcs",
                new_callable=AsyncMock,
                return_value=True,
            ),
        ):
            mock_head.side_effect = httpx.RequestError("Connection refused")
            result = await validate_url("https://example.com/repo", timeout=5)
            assert result.result == UrlValidationResult.VALID

    @pytest.mark.asyncio
    async def test_file_url_returns_invalid(self):
        result = await validate_url("file:///usr/src/app/ptaf-task-mgr", timeout=5)
        assert result.result == UrlValidationResult.INVALID

    @pytest.mark.asyncio
    async def test_git_ls_remote_fails_returns_invalid(self):
        with (
            patch(
                "purl_resolver.url_validator._head_request",
                new_callable=AsyncMock,
            ) as mock_head,
            patch(
                "purl_resolver.url_validator._check_vcs",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            mock_head.return_value = _mock_head(200)
            result = await validate_url("https://github.com/deleted/repo", timeout=5)
            assert result.result == UrlValidationResult.INVALID

    @pytest.mark.asyncio
    async def test_git_ls_remote_timeout_returns_network_error(self):
        with (
            patch(
                "purl_resolver.url_validator._head_request",
                new_callable=AsyncMock,
            ) as mock_head,
            patch(
                "purl_resolver.url_validator._check_vcs",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            mock_head.return_value = _mock_head(200)
            result = await validate_url("https://example.com/repo", timeout=5)
            assert result.result == UrlValidationResult.NETWORK_ERROR

    @pytest.mark.asyncio
    async def test_git_url_valid(self):
        with patch(
            "purl_resolver.url_validator._check_vcs",
            new_callable=AsyncMock,
            return_value=True,
        ):
            result = await validate_url("git://github.com/user/repo.git", timeout=5)
            assert result.result == UrlValidationResult.VALID

    @pytest.mark.asyncio
    async def test_ssh_url_valid(self):
        with patch(
            "purl_resolver.url_validator._check_vcs",
            new_callable=AsyncMock,
            return_value=True,
        ):
            result = await validate_url("ssh://git@github.com/user/repo.git", timeout=5)
            assert result.result == UrlValidationResult.VALID

    @pytest.mark.asyncio
    async def test_svn_url_valid(self):
        with patch(
            "purl_resolver.url_validator._check_vcs",
            new_callable=AsyncMock,
            return_value=True,
        ):
            result = await validate_url("svn://svn.example.com/repo", timeout=5)
            assert result.result == UrlValidationResult.VALID

    @pytest.mark.asyncio
    async def test_ssh_url_private_network_returns_invalid(self):
        with patch(
            "purl_resolver.url_validator._is_private_url",
            new_callable=AsyncMock,
            return_value=True,
        ):
            result = await validate_url("ssh://10.0.0.1/repo", timeout=5)
            assert result.result == UrlValidationResult.INVALID


class TestUrlValidationOutputDataclass:
    def test_has_result_and_final_url_fields(self):
        assert "result" in UrlValidationOutput.__dataclass_fields__
        assert "final_url" in UrlValidationOutput.__dataclass_fields__


class TestValidateUrlRedirectCapture:
    @pytest.mark.asyncio
    async def test_captures_final_url(self):
        with (
            patch(
                "purl_resolver.url_validator._head_request",
                new_callable=AsyncMock,
            ) as mock_head,
            patch(
                "purl_resolver.url_validator._check_vcs",
                new_callable=AsyncMock,
                return_value=True,
            ),
        ):
            mock_resp = _mock_head(200)
            mock_resp.url = "https://github.com/psf/requests"
            mock_head.return_value = mock_resp
            output = await validate_url("https://github.com/psf/requests", timeout=5)
            assert output.result == UrlValidationResult.VALID
            assert output.final_url == "https://github.com/psf/requests"

    @pytest.mark.asyncio
    async def test_captures_redirect_target(self):
        with (
            patch(
                "purl_resolver.url_validator._head_request",
                new_callable=AsyncMock,
            ) as mock_head,
            patch(
                "purl_resolver.url_validator._check_vcs",
                new_callable=AsyncMock,
            ) as mock_vcs,
        ):
            mock_resp = _mock_head(200)
            mock_resp.url = "https://github.com/psf/requests"
            mock_head.return_value = mock_resp
            mock_vcs.return_value = True
            output = await validate_url("https://old-url.com/psf/requests", timeout=5)
            assert output.result == UrlValidationResult.VALID
            assert output.final_url == "https://github.com/psf/requests"
            mock_vcs.assert_called_once_with("https://github.com/psf/requests", 5)

    @pytest.mark.asyncio
    async def test_final_url_none_when_head_not_executed(self):
        result = await validate_url("file:///usr/src/app/ptaf-task-mgr", timeout=5)
        assert result.result == UrlValidationResult.INVALID
        assert result.final_url is None

class TestEnsureConnectivity:
    @pytest.mark.asyncio
    async def test_success_returns_true(self):
        with patch("purl_resolver.url_validator.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.head.return_value.status_code = 200
            result = await ensure_connectivity()
            assert result is True

    @pytest.mark.asyncio
    async def test_failure_raises_connection_error(self):
        with patch("purl_resolver.url_validator.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.head.side_effect = (
                httpx.RequestError("fail")
            )
            with pytest.raises(ConnectionError, match="Cannot reach https://github.com"):
                await ensure_connectivity()

    @pytest.mark.asyncio
    async def test_success_with_custom_url_and_timeout(self):
        with patch("purl_resolver.url_validator.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.head.return_value.status_code = 200
            result = await ensure_connectivity(url="https://gitlab.com", timeout=5)
            assert result is True
            mock_client.assert_called_once_with(timeout=5)
            call_url = mock_client.return_value.__aenter__.return_value.head.call_args[0][0]
            assert call_url == "https://gitlab.com"

    @pytest.mark.asyncio
    async def test_empty_url_returns_true(self):
        result = await ensure_connectivity(url="")
        assert result is True

    @pytest.mark.asyncio
    async def test_private_url_raises_error(self):
        with patch(
            "purl_resolver.url_validator._is_private_url",
            new_callable=AsyncMock,
            return_value=True,
        ):
            with pytest.raises(ConnectionError, match="private address"):
                await ensure_connectivity()



