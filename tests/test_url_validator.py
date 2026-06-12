from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from purl_resolver.url_validator import (
    UrlValidationResult,
    _git_ls_remote,
    _RateLimitTracker,
    ensure_connectivity,
    validate_github_token,
    validate_url,
    validate_url_with_retry,
)


@pytest.fixture(autouse=True)
def reset_rate_limit_tracker():
    _RateLimitTracker._count = 0
    _RateLimitTracker._cooldown_until = 0.0
    yield
    _RateLimitTracker._count = 0
    _RateLimitTracker._cooldown_until = 0.0


def _mock_response(status_code: int = 200, headers: dict | None = None) -> AsyncMock:
    resp = AsyncMock()
    resp.status_code = status_code
    resp.headers = headers or {}
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


def _mock_head(status_code: int = 200, headers: dict | None = None):
    return _mock_response(status_code, headers)


class TestValidateUrl:
    @pytest.mark.asyncio
    async def test_valid_url(self):
        with patch("purl_resolver.url_validator._check_connectivity", new_callable=AsyncMock, return_value=True), \
             patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head, \
             patch("purl_resolver.url_validator._git_ls_remote", new_callable=AsyncMock, return_value=True):
            mock_head.return_value = _mock_head(200)
            result = await validate_url("https://github.com/psf/requests", timeout=5)
            assert result == UrlValidationResult.VALID

    @pytest.mark.asyncio
    async def test_head_404_returns_invalid(self):
        with patch("purl_resolver.url_validator._check_connectivity", new_callable=AsyncMock, return_value=True), \
             patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head:
            mock_head.return_value = _mock_head(404)
            result = await validate_url("https://github.com/deleted/repo", timeout=5)
            assert result == UrlValidationResult.INVALID

    @pytest.mark.asyncio
    async def test_head_403_without_rate_limit_headers_returns_invalid(self):
        with patch("purl_resolver.url_validator._check_connectivity", new_callable=AsyncMock, return_value=True), \
             patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head:
            mock_head.return_value = _mock_head(403, {"x-github-media-type": "v3"})
            result = await validate_url("https://github.com/private/repo", timeout=5)
            assert result == UrlValidationResult.INVALID

    @pytest.mark.asyncio
    async def test_head_403_with_rate_limit_remaining_zero_returns_rate_limited(self):
        with patch("purl_resolver.url_validator._check_connectivity", new_callable=AsyncMock, return_value=True), \
             patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head:
            mock_head.return_value = _mock_head(403, {"x-ratelimit-remaining": "0"})
            result = await validate_url("https://github.com/psf/requests", timeout=5)
            assert result == UrlValidationResult.RATE_LIMITED

    @pytest.mark.asyncio
    async def test_head_429_returns_rate_limited(self):
        with patch("purl_resolver.url_validator._check_connectivity", new_callable=AsyncMock, return_value=True), \
             patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head:
            mock_head.return_value = _mock_head(429)
            result = await validate_url("https://github.com/psf/requests", timeout=5)
            assert result == UrlValidationResult.RATE_LIMITED

    @pytest.mark.asyncio
    async def test_head_connection_error_returns_network_error(self):
        with patch("purl_resolver.url_validator._check_connectivity", new_callable=AsyncMock, return_value=True), \
             patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head:
            mock_head.side_effect = Exception("Connection refused")
            result = await validate_url("https://example.com/repo", timeout=5)
            assert result == UrlValidationResult.NETWORK_ERROR

    @pytest.mark.asyncio
    async def test_file_url_returns_invalid(self):
        result = await validate_url("file:///usr/src/app/ptaf-task-mgr", timeout=5)
        assert result == UrlValidationResult.INVALID

    @pytest.mark.asyncio
    async def test_connectivity_probe_fails_returns_network_error(self):
        with patch("purl_resolver.url_validator._check_connectivity", new_callable=AsyncMock, return_value=False):
            result = await validate_url("https://github.com/psf/requests", timeout=5)
            assert result == UrlValidationResult.NETWORK_ERROR

    @pytest.mark.asyncio
    async def test_git_ls_remote_fails_returns_invalid(self):
        with patch("purl_resolver.url_validator._check_connectivity", new_callable=AsyncMock, return_value=True), \
             patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head, \
             patch("purl_resolver.url_validator._git_ls_remote", new_callable=AsyncMock, return_value=False):
            mock_head.return_value = _mock_head(200)
            result = await validate_url("https://github.com/deleted/repo", timeout=5)
            assert result == UrlValidationResult.INVALID

    @pytest.mark.asyncio
    async def test_git_ls_remote_timeout_returns_network_error(self):
        with patch("purl_resolver.url_validator._check_connectivity", new_callable=AsyncMock, return_value=True), \
             patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head, \
             patch("purl_resolver.url_validator._git_ls_remote", new_callable=AsyncMock, return_value=None):
            mock_head.return_value = _mock_head(200)
            result = await validate_url("https://example.com/repo", timeout=5)
            assert result == UrlValidationResult.NETWORK_ERROR

    @pytest.mark.asyncio
    async def test_rate_limit_cooldown_skips_validation(self):
        import time
        _RateLimitTracker._count = 5
        _RateLimitTracker._cooldown_until = time.time() + 60
        result = await validate_url("https://github.com/psf/requests", timeout=5)
        assert result == UrlValidationResult.RATE_LIMITED

class TestValidateUrlWithToken:
    @pytest.mark.asyncio
    async def test_token_passed_to_head_request(self):
        with patch("purl_resolver.url_validator._check_connectivity", new_callable=AsyncMock, return_value=True), \
             patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head, \
             patch("purl_resolver.url_validator._git_ls_remote", new_callable=AsyncMock, return_value=True):
            mock_head.return_value = _mock_head(200)
            await validate_url("https://github.com/psf/requests", timeout=5, github_token="ghp_test")
            mock_head.assert_called_once_with("https://github.com/psf/requests", 5, github_token="ghp_test")

    @pytest.mark.asyncio
    async def test_head_request_with_bearer_token(self):
        with patch("purl_resolver.url_validator._check_connectivity", new_callable=AsyncMock, return_value=True), \
             patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head, \
             patch("purl_resolver.url_validator._git_ls_remote", new_callable=AsyncMock, return_value=True):
            mock_head.return_value = _mock_head(200)
            await validate_url("https://github.com/psf/requests", timeout=5, github_token="ghp_test")
            call_kwargs = mock_head.call_args
            assert call_kwargs[1]["github_token"] == "ghp_test"

    @pytest.mark.asyncio
    async def test_git_ls_remote_with_token_in_url(self):
        with patch("purl_resolver.url_validator._check_connectivity", new_callable=AsyncMock, return_value=True), \
             patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head, \
             patch("purl_resolver.url_validator._git_ls_remote", new_callable=AsyncMock) as mock_git:
            mock_head.return_value = _mock_head(200)
            mock_git.return_value = True
            await validate_url("https://github.com/psf/requests", timeout=5, github_token="ghp_test")
            call_args = mock_git.call_args
            assert call_args[0][0] == "https://github.com/psf/requests"
            assert call_args[1]["github_token"] == "ghp_test"

    @pytest.mark.asyncio
    async def test_token_invalid_response(self):
        with patch("purl_resolver.url_validator._check_connectivity", new_callable=AsyncMock, return_value=True), \
             patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head:
            mock_head.return_value = _mock_response(401, {"x-github-media-type": "v3"})
            result = await validate_url("https://github.com/psf/requests", timeout=5, github_token="ghp_invalid")
            assert result == UrlValidationResult.TOKEN_INVALID


class TestGitLsRemoteTokenTransformation:
    @pytest.mark.asyncio
    async def test_github_url_rewrites_with_token(self):
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_proc.returncode = 0
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            result = await _git_ls_remote("https://github.com/psf/requests", 5, github_token="ghp_test123")
            assert result is True
            call_args = mock_exec.call_args
            assert "https://oauth2:ghp_test123@github.com/psf/requests" in call_args[0]

    @pytest.mark.asyncio
    async def test_non_github_url_no_token_injection(self):
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_proc.returncode = 0
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            result = await _git_ls_remote("https://gitlab.com/org/repo", 5, github_token="ghp_test123")
            assert result is True
            call_args = mock_exec.call_args
            assert "oauth2" not in str(call_args[0])


class TestTokenInvalidResult:
    def test_token_invalid_is_enum_value(self):
        assert UrlValidationResult.TOKEN_INVALID.value == "token_invalid"


class TestValidateGithubToken:
    @pytest.mark.asyncio
    async def test_valid_token_returns_true(self):
        with patch("purl_resolver.url_validator._check_connectivity", new_callable=AsyncMock, return_value=True), \
             patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head:
            mock_head.return_value = _mock_response(200)
            result = await validate_github_token("ghp_valid")
            assert result is True

    @pytest.mark.asyncio
    async def test_invalid_token_returns_false(self):
        with patch("purl_resolver.url_validator._check_connectivity", new_callable=AsyncMock, return_value=True), \
             patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head:
            mock_head.return_value = _mock_response(401)
            result = await validate_github_token("ghp_invalid")
            assert result is False

    @pytest.mark.asyncio
    async def test_network_error_returns_false(self):
        with patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head:
            mock_head.side_effect = Exception("Connection refused")
            result = await validate_github_token("ghp_test")
            assert result is False


class TestEnsureConnectivity:
    @pytest.mark.asyncio
    async def test_success_returns_true(self):
        with patch("purl_resolver.url_validator._check_connectivity", new_callable=AsyncMock, return_value=True):
            result = await ensure_connectivity()
            assert result is True

    @pytest.mark.asyncio
    async def test_failure_raises_connection_error(self):
        with patch("purl_resolver.url_validator._check_connectivity", new_callable=AsyncMock, return_value=False):
            with pytest.raises(ConnectionError, match="Cannot reach"):
                await ensure_connectivity()

    @pytest.mark.asyncio
    async def test_failure_raises_with_token(self):
        with patch("purl_resolver.url_validator._check_connectivity", new_callable=AsyncMock, return_value=False):
            with pytest.raises(ConnectionError):
                await ensure_connectivity(github_token="ghp_test")


class TestValidateUrlSkipConnectivity:
    @pytest.mark.asyncio
    async def test_skip_connectivity_check_skips_probe(self):
        with patch("purl_resolver.url_validator._check_connectivity", new_callable=AsyncMock, return_value=True) as mock_conn, \
             patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head, \
             patch("purl_resolver.url_validator._git_ls_remote", new_callable=AsyncMock, return_value=True):
            mock_head.return_value = _mock_head(200)
            result = await validate_url("https://github.com/psf/requests", timeout=5, skip_connectivity_check=True)
            assert result == UrlValidationResult.VALID
            mock_conn.assert_not_called()

    @pytest.mark.asyncio
    async def test_default_still_checks_connectivity(self):
        with patch("purl_resolver.url_validator._check_connectivity", new_callable=AsyncMock, return_value=True) as mock_conn, \
             patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head, \
             patch("purl_resolver.url_validator._git_ls_remote", new_callable=AsyncMock, return_value=True):
            mock_head.return_value = _mock_head(200)
            result = await validate_url("https://github.com/psf/requests", timeout=5)
            assert result == UrlValidationResult.VALID
            mock_conn.assert_called_once()


class TestValidateUrlWithRetry:
    @pytest.mark.asyncio
    async def test_valid_passes_through(self):
        with patch("purl_resolver.url_validator._check_connectivity", new_callable=AsyncMock, return_value=True), \
             patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head, \
             patch("purl_resolver.url_validator._git_ls_remote", new_callable=AsyncMock, return_value=True):
            mock_head.return_value = _mock_head(200)
            result = await validate_url_with_retry("https://github.com/psf/requests", timeout=5)
            assert result == UrlValidationResult.VALID

    @pytest.mark.asyncio
    async def test_token_invalid_retries_without_token(self):
        saved_token = None

        class FakeSettingsStore:
            def load(self):
                from purl_resolver.settings_store import AppSettings
                return AppSettings()

        with patch("purl_resolver.url_validator._check_connectivity", new_callable=AsyncMock, return_value=True), \
             patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head, \
             patch("purl_resolver.url_validator._git_ls_remote", new_callable=AsyncMock, return_value=True):
            first_call = True

            async def side_effect(url, timeout, **kwargs):
                nonlocal first_call
                if first_call:
                    first_call = False
                    return _mock_response(401, {"x-github-media-type": "v3"})
                return _mock_response(200)

            mock_head.side_effect = side_effect
            result = await validate_url_with_retry(
                "https://github.com/psf/requests", timeout=5,
                github_token="ghp_invalid",
                settings_store=FakeSettingsStore(),
            )
            assert result == UrlValidationResult.VALID

    @pytest.mark.asyncio
    async def test_token_invalid_without_settings_store_does_not_retry(self):
        with patch("purl_resolver.url_validator._check_connectivity", new_callable=AsyncMock, return_value=True), \
             patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head:
            mock_head.return_value = _mock_response(401, {"x-github-media-type": "v3"})
            result = await validate_url_with_retry(
                "https://github.com/psf/requests", timeout=5,
                github_token="ghp_invalid",
            )
            assert result == UrlValidationResult.TOKEN_INVALID
