from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from purl_resolver.url_validator import (
    UrlValidationOutput,
    UrlValidationResult,
    _check_vcs,
    ensure_connectivity,
    validate_github_token,
    validate_url,
    validate_url_with_retry,
)


@pytest.fixture(autouse=True)
def reset_rate_limit_tracker():
    from purl_resolver.url_validator import _rate_limit_tracker
    _rate_limit_tracker.reset()
    yield
    _rate_limit_tracker.reset()


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
        with patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head, \
             patch("purl_resolver.url_validator._check_vcs", new_callable=AsyncMock, return_value=True):
            mock_head.return_value = _mock_head(200)
            result = await validate_url("https://github.com/psf/requests", timeout=5)
            assert result.result == UrlValidationResult.VALID

    @pytest.mark.asyncio
    async def test_head_404_returns_invalid(self):
        with patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head:
            mock_head.return_value = _mock_head(404)
            result = await validate_url("https://github.com/deleted/repo", timeout=5)
            assert result.result == UrlValidationResult.INVALID

    @pytest.mark.asyncio
    async def test_head_403_without_rate_limit_headers_returns_invalid(self):
        with patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head:
            mock_head.return_value = _mock_head(403, {"x-github-media-type": "v3"})
            result = await validate_url("https://github.com/private/repo", timeout=5)
            assert result.result == UrlValidationResult.INVALID

    @pytest.mark.asyncio
    async def test_head_403_with_rate_limit_remaining_zero_returns_rate_limited(self):
        with patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head:
            mock_head.return_value = _mock_head(403, {"x-ratelimit-remaining": "0"})
            result = await validate_url("https://github.com/psf/requests", timeout=5)
            assert result.result == UrlValidationResult.RATE_LIMITED

    @pytest.mark.asyncio
    async def test_head_429_returns_rate_limited(self):
        with patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head:
            mock_head.return_value = _mock_head(429)
            result = await validate_url("https://github.com/psf/requests", timeout=5)
            assert result.result == UrlValidationResult.RATE_LIMITED

    @pytest.mark.asyncio
    async def test_head_connection_error_returns_network_error(self):
        with patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head:
            mock_head.side_effect = httpx.RequestError("Connection refused")
            result = await validate_url("https://example.com/repo", timeout=5)
            assert result.result == UrlValidationResult.NETWORK_ERROR

    @pytest.mark.asyncio
    async def test_file_url_returns_invalid(self):
        result = await validate_url("file:///usr/src/app/ptaf-task-mgr", timeout=5)
        assert result.result == UrlValidationResult.INVALID

    @pytest.mark.asyncio
    async def test_git_ls_remote_fails_returns_invalid(self):
        with patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head, \
             patch("purl_resolver.url_validator._check_vcs", new_callable=AsyncMock, return_value=False):
            mock_head.return_value = _mock_head(200)
            result = await validate_url("https://github.com/deleted/repo", timeout=5)
            assert result.result == UrlValidationResult.INVALID

    @pytest.mark.asyncio
    async def test_git_ls_remote_timeout_returns_network_error(self):
        with patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head, \
             patch("purl_resolver.url_validator._check_vcs", new_callable=AsyncMock, return_value=None):
            mock_head.return_value = _mock_head(200)
            result = await validate_url("https://example.com/repo", timeout=5)
            assert result.result == UrlValidationResult.NETWORK_ERROR

    @pytest.mark.asyncio
    async def test_rate_limit_cooldown_skips_validation(self):
        import time
        from purl_resolver.url_validator import _rate_limit_tracker
        _rate_limit_tracker._count = 5
        _rate_limit_tracker._cooldown_until = time.time() + 60
        result = await validate_url("https://github.com/psf/requests", timeout=5)
        assert result.result == UrlValidationResult.RATE_LIMITED


class TestUrlValidationOutputDataclass:
    def test_has_result_and_final_url_fields(self):
        assert "result" in UrlValidationOutput.__dataclass_fields__
        assert "final_url" in UrlValidationOutput.__dataclass_fields__


class TestValidateUrlRedirectCapture:
    @pytest.mark.asyncio
    async def test_captures_final_url(self):
        with patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head, \
             patch("purl_resolver.url_validator._check_vcs", new_callable=AsyncMock, return_value=True):
            mock_resp = _mock_head(200)
            mock_resp.url = "https://github.com/psf/requests"
            mock_head.return_value = mock_resp
            output = await validate_url("https://github.com/psf/requests", timeout=5)
            assert output.result == UrlValidationResult.VALID
            assert output.final_url == "https://github.com/psf/requests"

    @pytest.mark.asyncio
    async def test_captures_redirect_target(self):
        with patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head, \
             patch("purl_resolver.url_validator._check_vcs", new_callable=AsyncMock) as mock_vcs:
            mock_resp = _mock_head(200)
            mock_resp.url = "https://github.com/psf/requests"
            mock_head.return_value = mock_resp
            mock_vcs.return_value = True
            output = await validate_url("https://old-url.com/psf/requests", timeout=5)
            assert output.result == UrlValidationResult.VALID
            assert output.final_url == "https://github.com/psf/requests"
            mock_vcs.assert_called_once_with("https://github.com/psf/requests", 5, github_token=None)

    @pytest.mark.asyncio
    async def test_final_url_none_when_head_not_executed(self):
        result = await validate_url("file:///usr/src/app/ptaf-task-mgr", timeout=5)
        assert result.result == UrlValidationResult.INVALID
        assert result.final_url is None

class TestValidateUrlWithToken:
    @pytest.mark.asyncio
    async def test_token_passed_to_head_request(self):
        with patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head, \
             patch("purl_resolver.url_validator._check_vcs", new_callable=AsyncMock, return_value=True):
            mock_head.return_value = _mock_head(200)
            await validate_url("https://github.com/psf/requests", timeout=5, github_token="ghp_test")
            mock_head.assert_called_once_with("https://github.com/psf/requests", 5, github_token="ghp_test")

    @pytest.mark.asyncio
    async def test_head_request_with_bearer_token(self):
        with patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head, \
             patch("purl_resolver.url_validator._check_vcs", new_callable=AsyncMock, return_value=True):
            mock_head.return_value = _mock_head(200)
            await validate_url("https://github.com/psf/requests", timeout=5, github_token="ghp_test")
            call_kwargs = mock_head.call_args
            assert call_kwargs[1]["github_token"] == "ghp_test"

    @pytest.mark.asyncio
    async def test_git_ls_remote_with_token_in_url(self):
        with patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head, \
             patch("purl_resolver.url_validator._check_vcs", new_callable=AsyncMock) as mock_vcs:
            mock_head.return_value = _mock_head(200)
            mock_vcs.return_value = True
            await validate_url("https://github.com/psf/requests", timeout=5, github_token="ghp_test")
            call_args = mock_vcs.call_args
            assert call_args[0][0] == "https://github.com/psf/requests"
            assert call_args[1]["github_token"] == "ghp_test"

    @pytest.mark.asyncio
    async def test_token_invalid_response(self):
        with patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head:
            mock_head.return_value = _mock_response(401, {"x-github-media-type": "v3"})
            result = await validate_url("https://github.com/psf/requests", timeout=5, github_token="ghp_invalid")
            assert result.result == UrlValidationResult.TOKEN_INVALID


class TestTokenInvalidResult:
    def test_token_invalid_is_enum_value(self):
        assert UrlValidationResult.TOKEN_INVALID.value == "token_invalid"


class TestValidateGithubToken:
    @pytest.mark.asyncio
    async def test_valid_token_returns_true(self):
        with patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head:
            mock_head.return_value = _mock_response(200)
            result = await validate_github_token("ghp_valid")
            assert result is True

    @pytest.mark.asyncio
    async def test_invalid_token_returns_false(self):
        with patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head:
            mock_head.return_value = _mock_response(401)
            result = await validate_github_token("ghp_invalid")
            assert result is False

    @pytest.mark.asyncio
    async def test_network_error_returns_false(self):
        with patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head:
            mock_head.side_effect = httpx.RequestError("Connection refused")
            result = await validate_github_token("ghp_test")
            assert result is False


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
            mock_client.return_value.__aenter__.return_value.head.side_effect = httpx.RequestError("fail")
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
        with patch("purl_resolver.url_validator._is_private_url", new_callable=AsyncMock, return_value=True):
            with pytest.raises(ConnectionError, match="private address"):
                await ensure_connectivity()


class TestValidateUrlWithRetry:
    @pytest.mark.asyncio
    async def test_valid_passes_through(self):
        with patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head, \
             patch("purl_resolver.url_validator._check_vcs", new_callable=AsyncMock, return_value=True):
            mock_head.return_value = _mock_head(200)
            output = await validate_url_with_retry("https://github.com/psf/requests", timeout=5)
            assert output.result == UrlValidationResult.VALID

    @pytest.mark.asyncio
    async def test_token_invalid_retries_without_token(self):

        class FakeSettingsStore:
            def load(self):
                from purl_resolver.settings_store import AppSettings
                return AppSettings()

        with patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head, \
             patch("purl_resolver.url_validator._check_vcs", new_callable=AsyncMock, return_value=True):
            first_call = True

            async def side_effect(url, timeout, **kwargs):
                nonlocal first_call
                if first_call:
                    first_call = False
                    return _mock_response(401, {"x-github-media-type": "v3"})
                return _mock_response(200)

            mock_head.side_effect = side_effect
            output = await validate_url_with_retry(
                "https://github.com/psf/requests", timeout=5,
                github_token="ghp_invalid",
                settings_store=FakeSettingsStore(),
            )
            assert output.result == UrlValidationResult.VALID

    @pytest.mark.asyncio
    async def test_token_invalid_without_settings_store_does_not_retry(self):
        with patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head:
            mock_head.return_value = _mock_response(401, {"x-github-media-type": "v3"})
            output = await validate_url_with_retry(
                "https://github.com/psf/requests", timeout=5,
                github_token="ghp_invalid",
            )
            assert output.result == UrlValidationResult.TOKEN_INVALID
