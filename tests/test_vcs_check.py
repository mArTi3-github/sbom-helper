from __future__ import annotations

import socket
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from purl_resolver.url_validator import UrlValidationResult


def _probe_returning(value):
    """Create an AsyncMock that returns the given value when awaited."""
    async def fake(url, *args, **kwargs):
        return value
    return AsyncMock(side_effect=fake)


def _make_proc(returncode: int = 0, stderr: bytes = b"") -> AsyncMock:
    """Create a mock async subprocess with the given returncode and stderr."""
    mock_proc = AsyncMock()
    mock_proc.communicate = AsyncMock(return_value=(b"", stderr))
    mock_proc.returncode = returncode
    mock_proc.kill = MagicMock()
    mock_proc.wait = AsyncMock()
    return mock_proc


def _make_proc_timeout():
    """Create a mock subprocess whose communicate() raises asyncio.TimeoutError."""
    mock_proc = AsyncMock()
    mock_proc.communicate = AsyncMock(side_effect=TimeoutError)
    mock_proc.kill = MagicMock()
    mock_proc.wait = AsyncMock()
    return mock_proc


def _make_httpx_response(status_code: int = 200, body: str = "") -> MagicMock:
    """Create a MagicMock httpx Response with status_code and text."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.text = body
    return mock_resp


def _patch_private():
    """Context manager that patches _is_private_url to return False (public)."""
    return patch("purl_resolver.url_validator._is_private_url",
                 new_callable=AsyncMock, return_value=False)


class TestIsPrivateUrl:
    @pytest.mark.asyncio
    async def test_public_url_returns_false(self):
        from purl_resolver.url_validator import _is_private_url
        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_resolve:
            mock_resolve.return_value = [(2, 1, 6, "", ("140.82.121.3", 0))]
            result = await _is_private_url("https://github.com")
            assert result is False

    @pytest.mark.asyncio
    async def test_private_ipv4_returns_true(self):
        from purl_resolver.url_validator import _is_private_url
        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_resolve:
            mock_resolve.return_value = [(2, 1, 6, "", ("127.0.0.1", 0))]
            result = await _is_private_url("https://localhost")
            assert result is True

    @pytest.mark.asyncio
    async def test_private_ipv6_returns_true(self):
        from purl_resolver.url_validator import _is_private_url
        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_resolve:
            mock_resolve.return_value = [(10, 1, 6, "", ("::1", 0, 0, 0))]
            result = await _is_private_url("https://ip6-localhost")
            assert result is True

    @pytest.mark.asyncio
    async def test_cloud_metadata_returns_true(self):
        from purl_resolver.url_validator import _is_private_url
        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_resolve:
            mock_resolve.return_value = [(2, 1, 6, "", ("169.254.169.254", 0))]
            result = await _is_private_url("http://169.254.169.254/latest/meta-data")
            assert result is True

    @pytest.mark.asyncio
    async def test_rfc1918_returns_true(self):
        from purl_resolver.url_validator import _is_private_url
        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_resolve:
            mock_resolve.return_value = [(2, 1, 6, "", ("192.168.1.1", 0))]
            result = await _is_private_url("http://192.168.1.1/admin")
            assert result is True

    @pytest.mark.asyncio
    async def test_dns_failure_returns_false(self):
        from purl_resolver.url_validator import _is_private_url
        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_resolve:
            mock_resolve.side_effect = socket.gaierror
            result = await _is_private_url("https://unknown.example.com")
            assert result is False

    @pytest.mark.asyncio
    async def test_mixed_public_and_private_ips_returns_true(self):
        from purl_resolver.url_validator import _is_private_url
        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_resolve:
            mock_resolve.return_value = [
                (2, 1, 6, "", ("192.168.1.1", 0)),
                (2, 1, 6, "", ("1.2.3.4", 0)),
            ]
            result = await _is_private_url("https://dual-homed.example.com")
            assert result is True


class TestCheckVcsSequential:

    @pytest.mark.asyncio
    async def test_git_false_svn_success_returns_true(self):
        from purl_resolver.url_validator import _check_vcs
        git = _probe_returning(False)
        svn = _probe_returning(True)
        hg = _probe_returning(False)
        fossil = _probe_returning(False)
        with patch("purl_resolver.url_validator._git_probe", git), \
             patch("purl_resolver.url_validator._svn_probe", svn), \
             patch("purl_resolver.url_validator._hg_probe", hg), \
             patch("purl_resolver.url_validator._fossil_probe", fossil):
            result = await _check_vcs("https://example.com/svn-repo", 5)
            assert result is True
            git.assert_awaited_once()
            svn.assert_awaited_once()
            hg.assert_not_awaited()
            fossil.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_git_svn_false_hg_success_returns_true(self):
        from purl_resolver.url_validator import _check_vcs
        git = _probe_returning(False)
        svn = _probe_returning(False)
        hg = _probe_returning(True)
        fossil = _probe_returning(False)
        with patch("purl_resolver.url_validator._git_probe", git), \
             patch("purl_resolver.url_validator._svn_probe", svn), \
             patch("purl_resolver.url_validator._hg_probe", hg), \
             patch("purl_resolver.url_validator._fossil_probe", fossil):
            result = await _check_vcs("https://example.com/hg-repo", 5)
            assert result is True
            git.assert_awaited_once()
            svn.assert_awaited_once()
            hg.assert_awaited_once()
            fossil.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_git_svn_hg_false_fossil_success_returns_true(self):
        from purl_resolver.url_validator import _check_vcs
        git = _probe_returning(False)
        svn = _probe_returning(False)
        hg = _probe_returning(False)
        fossil = _probe_returning(True)
        with patch("purl_resolver.url_validator._git_probe", git), \
             patch("purl_resolver.url_validator._svn_probe", svn), \
             patch("purl_resolver.url_validator._hg_probe", hg), \
             patch("purl_resolver.url_validator._fossil_probe", fossil):
            result = await _check_vcs("https://example.com/fossil-repo", 5)
            assert result is True
            git.assert_awaited_once()
            svn.assert_awaited_once()
            hg.assert_awaited_once()
            fossil.assert_awaited_once()


class TestCheckVcsAggregation:
    @pytest.mark.asyncio
    async def test_all_probes_false_returns_false(self):
        from purl_resolver.url_validator import _check_vcs
        with patch("purl_resolver.url_validator._git_probe", _probe_returning(False)), \
             patch("purl_resolver.url_validator._svn_probe", _probe_returning(False)), \
             patch("purl_resolver.url_validator._hg_probe", _probe_returning(False)), \
             patch("purl_resolver.url_validator._fossil_probe", _probe_returning(False)):
            result = await _check_vcs("https://example.com/not-a-repo", 5)
            assert result is False

    @pytest.mark.asyncio
    async def test_all_probes_none_returns_none(self):
        from purl_resolver.url_validator import _check_vcs
        with patch("purl_resolver.url_validator._git_probe", _probe_returning(None)), \
             patch("purl_resolver.url_validator._svn_probe", _probe_returning(None)), \
             patch("purl_resolver.url_validator._hg_probe", _probe_returning(None)), \
             patch("purl_resolver.url_validator._fossil_probe", _probe_returning(None)):
            result = await _check_vcs("https://example.com/repo", 5)
            assert result is None

    @pytest.mark.asyncio
    async def test_false_wins_over_none(self):
        """When at least one probe is False (definitive) and rest are None (uncertain),
        aggregation must return False (not None) - protects cached URLs from deletion."""
        from purl_resolver.url_validator import _check_vcs
        with patch("purl_resolver.url_validator._git_probe", _probe_returning(None)), \
             patch("purl_resolver.url_validator._svn_probe", _probe_returning(False)), \
             patch("purl_resolver.url_validator._hg_probe", _probe_returning(None)), \
             patch("purl_resolver.url_validator._fossil_probe", _probe_returning(None)):
            result = await _check_vcs("https://example.com/repo", 5)
            assert result is False

    @pytest.mark.asyncio
    async def test_partial_timeout_with_success_returns_true(self):
        from purl_resolver.url_validator import _check_vcs
        with patch("purl_resolver.url_validator._git_probe", _probe_returning(None)), \
             patch("purl_resolver.url_validator._svn_probe", _probe_returning(True)), \
             patch("purl_resolver.url_validator._hg_probe", _probe_returning(False)), \
             patch("purl_resolver.url_validator._fossil_probe", _probe_returning(False)):
            result = await _check_vcs("https://example.com/svn-repo", 5)
            assert result is True


class TestGitProbe:
    @pytest.mark.asyncio
    async def test_exit_zero_returns_true(self):
        from purl_resolver.url_validator import _git_probe
        with patch("asyncio.create_subprocess_exec", return_value=_make_proc(0)) as mock_exec:
            result = await _git_probe("https://github.com/psf/requests", 5)
            assert result is True
            args = mock_exec.call_args[0]
            assert args[0] == "git"
            assert args[1] == "ls-remote"
            assert args[2] == "--exit-code"

    @pytest.mark.asyncio
    async def test_not_found_stderr_returns_false(self):
        from purl_resolver.url_validator import _git_probe
        with patch("asyncio.create_subprocess_exec", return_value=_make_proc(128, b"fatal: not found\n")):
            result = await _git_probe("https://github.com/missing/repo", 5)
            assert result is False

    @pytest.mark.asyncio
    async def test_does_not_exist_stderr_returns_false(self):
        from purl_resolver.url_validator import _git_probe
        with patch("asyncio.create_subprocess_exec", return_value=_make_proc(128, b"repository does not exist\n")):
            result = await _git_probe("https://github.com/missing/repo", 5)
            assert result is False

    @pytest.mark.asyncio
    async def test_other_stderr_returns_none(self):
        from purl_resolver.url_validator import _git_probe
        with patch("asyncio.create_subprocess_exec", return_value=_make_proc(128, b"some random error\n")):
            result = await _git_probe("https://github.com/example/repo", 5)
            assert result is None

    @pytest.mark.asyncio
    async def test_timeout_returns_none(self):
        from purl_resolver.url_validator import _git_probe
        with patch("asyncio.create_subprocess_exec", return_value=_make_proc_timeout()) as mock_exec:
            result = await _git_probe("https://github.com/psf/requests", 5)
            assert result is None
            mock_exec.return_value.kill.assert_called_once()

    @pytest.mark.asyncio
    async def test_github_token_rewrites_url(self):
        from purl_resolver.url_validator import _git_probe
        with patch("asyncio.create_subprocess_exec", return_value=_make_proc(0)) as mock_exec:
            await _git_probe("https://github.com/psf/requests", 5, github_token="ghp_test123")
            args = mock_exec.call_args[0]
            assert "https://oauth2:ghp_test123@github.com/psf/requests" in args

    @pytest.mark.asyncio
    async def test_non_github_url_no_token_injection(self):
        from purl_resolver.url_validator import _git_probe
        with patch("asyncio.create_subprocess_exec", return_value=_make_proc(0)) as mock_exec:
            await _git_probe("https://gitlab.com/org/repo", 5, github_token="ghp_test123")
            args = mock_exec.call_args[0]
            assert "oauth2" not in str(args)


class TestSvnProbe:
    @pytest.mark.asyncio
    async def test_exit_zero_returns_true(self):
        from purl_resolver.url_validator import _svn_probe
        with patch("asyncio.create_subprocess_exec", return_value=_make_proc(0)) as mock_exec:
            result = await _svn_probe("https://example.com/svn-repo", 5)
            assert result is True
            args = mock_exec.call_args[0]
            assert args[0] == "svn"
            assert args[1] == "ls"

    @pytest.mark.asyncio
    async def test_nonzero_exit_returns_false(self):
        from purl_resolver.url_validator import _svn_probe
        with patch("asyncio.create_subprocess_exec", return_value=_make_proc(1, b"svn: E200009\n")):
            result = await _svn_probe("https://example.com/svn-repo", 5)
            assert result is False

    @pytest.mark.asyncio
    async def test_timeout_returns_none(self):
        from purl_resolver.url_validator import _svn_probe
        with patch("asyncio.create_subprocess_exec", return_value=_make_proc_timeout()) as mock_exec:
            result = await _svn_probe("https://example.com/svn-repo", 5)
            assert result is None
            mock_exec.return_value.kill.assert_called_once()


class TestHgProbe:
    @pytest.mark.asyncio
    async def test_exit_zero_returns_true(self):
        from purl_resolver.url_validator import _hg_probe
        with patch("asyncio.create_subprocess_exec", return_value=_make_proc(0)) as mock_exec:
            result = await _hg_probe("https://example.com/hg-repo", 5)
            assert result is True
            args = mock_exec.call_args[0]
            assert args[0] == "hg"
            assert args[1] == "identify"

    @pytest.mark.asyncio
    async def test_nonzero_exit_returns_false(self):
        from purl_resolver.url_validator import _hg_probe
        with patch("asyncio.create_subprocess_exec", return_value=_make_proc(1, b"")):
            result = await _hg_probe("https://example.com/hg-repo", 5)
            assert result is False

    @pytest.mark.asyncio
    async def test_timeout_returns_none(self):
        from purl_resolver.url_validator import _hg_probe
        with patch("asyncio.create_subprocess_exec", return_value=_make_proc_timeout()) as mock_exec:
            result = await _hg_probe("https://example.com/hg-repo", 5)
            assert result is None
            mock_exec.return_value.kill.assert_called_once()


def _make_streaming_response(
    status_code: int = 200,
    content_type: str = "text/html",
    headers: dict | None = None,
) -> AsyncMock:
    """Create a mock async context manager for httpx.AsyncClient.stream().

    Returns a mock whose __aenter__ returns a response-like object
    with status_code and headers.
    """
    mock_cm = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.headers = {"content-type": content_type, **(headers or {})}
    mock_cm.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    return mock_cm


class TestFossilProbeXfer:
    @pytest.mark.asyncio
    async def test_xfer_content_type_returns_true(self):
        from purl_resolver.url_validator import _fossil_probe_xfer
        mock_cm = _make_streaming_response(200, "application/x-fossil-debug")
        with _patch_private(), patch("httpx.AsyncClient.stream", return_value=mock_cm):
            result = await _fossil_probe_xfer("https://example.com/fossil", 5)
            assert result is True

    @pytest.mark.asyncio
    async def test_non_fossil_content_type_returns_false(self):
        from purl_resolver.url_validator import _fossil_probe_xfer
        mock_cm = _make_streaming_response(200, "text/html")
        with _patch_private(), patch("httpx.AsyncClient.stream", return_value=mock_cm):
            result = await _fossil_probe_xfer("https://example.com/plain", 5)
            assert result is False

    @pytest.mark.asyncio
    async def test_401_returns_none(self):
        from purl_resolver.url_validator import _fossil_probe_xfer
        mock_cm = _make_streaming_response(401, "text/html")
        with _patch_private(), patch("httpx.AsyncClient.stream", return_value=mock_cm):
            result = await _fossil_probe_xfer("https://example.com/fossil", 5)
            assert result is None

    @pytest.mark.asyncio
    async def test_403_returns_none(self):
        from purl_resolver.url_validator import _fossil_probe_xfer
        mock_cm = _make_streaming_response(403, "text/html")
        with _patch_private(), patch("httpx.AsyncClient.stream", return_value=mock_cm):
            result = await _fossil_probe_xfer("https://example.com/fossil", 5)
            assert result is None

    @pytest.mark.asyncio
    async def test_request_error_returns_none(self):
        from purl_resolver.url_validator import _fossil_probe_xfer
        mock_cm = _make_streaming_response(200, "text/html")
        mock_cm.__aenter__.side_effect = TimeoutError
        with _patch_private(), patch("httpx.AsyncClient.stream", return_value=mock_cm):
            result = await _fossil_probe_xfer("https://example.com/fossil", 5)
            assert result is None

    @pytest.mark.asyncio
    async def test_xfer_url_appends_xfer_path(self):
        from purl_resolver.url_validator import _fossil_probe_xfer
        mock_cm = _make_streaming_response(200, "text/html")
        with _patch_private(), patch("httpx.AsyncClient.stream", return_value=mock_cm) as mock_stream:
            await _fossil_probe_xfer("https://example.com/fossil/repo", 5)
            call_url = mock_stream.call_args[0][1]
            assert call_url.endswith("/xfer")

    @pytest.mark.asyncio
    async def test_private_url_returns_none(self):
        from purl_resolver.url_validator import _fossil_probe_xfer
        with patch("purl_resolver.url_validator._is_private_url",
                   new_callable=AsyncMock, return_value=True):
            result = await _fossil_probe_xfer("http://192.168.1.1/admin", 5)
            assert result is None


class TestFossilProbeFooter:
    @pytest.mark.asyncio
    async def test_200_with_footer_returns_true(self):
        from purl_resolver.url_validator import _fossil_probe_footer
        body = '<html><body><div id="footer">this page was generated in about 0.05s by fossil</div></body></html>'
        with _patch_private(), patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _make_httpx_response(200, body)
            result = await _fossil_probe_footer("https://example.com/fossil", 5)
            assert result is True

    @pytest.mark.asyncio
    async def test_200_without_footer_returns_false(self):
        from purl_resolver.url_validator import _fossil_probe_footer
        with _patch_private(), patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _make_httpx_response(200, "<html><body>Hello world</body></html>")
            result = await _fossil_probe_footer("https://example.com/plain-html", 5)
            assert result is False

    @pytest.mark.asyncio
    async def test_404_returns_false(self):
        from purl_resolver.url_validator import _fossil_probe_footer
        with _patch_private(), patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _make_httpx_response(404, "")
            result = await _fossil_probe_footer("https://example.com/missing", 5)
            assert result is False

    @pytest.mark.asyncio
    async def test_regex_case_insensitive(self):
        from purl_resolver.url_validator import _fossil_probe_footer
        body = '<html><div id="footer">This page was generated in about 0.1s by FOSSIL</div></html>'
        with _patch_private(), patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _make_httpx_response(200, body)
            result = await _fossil_probe_footer("https://example.com/fossil", 5)
            assert result is True

    @pytest.mark.asyncio
    async def test_integer_seconds_matches(self):
        from purl_resolver.url_validator import _fossil_probe_footer
        body = '<html>This page was generated in about 1s by fossil</html>'
        with _patch_private(), patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _make_httpx_response(200, body)
            result = await _fossil_probe_footer("https://example.com/fossil", 5)
            assert result is True

    @pytest.mark.asyncio
    async def test_http_exception_returns_none(self):
        from purl_resolver.url_validator import _fossil_probe_footer
        with _patch_private(), patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = TimeoutError
            result = await _fossil_probe_footer("https://example.com/fossil", 5)
            assert result is None

    @pytest.mark.asyncio
    async def test_private_url_returns_none(self):
        from purl_resolver.url_validator import _fossil_probe_footer
        with patch("purl_resolver.url_validator._is_private_url",
                   new_callable=AsyncMock, return_value=True):
            result = await _fossil_probe_footer("http://10.0.0.1/admin", 5)
            assert result is None


class TestFossilProbeCombined:
    @pytest.mark.asyncio
    async def test_xfer_true_returns_true_no_footer(self):
        from purl_resolver.url_validator import _fossil_probe
        with patch("purl_resolver.url_validator._fossil_probe_xfer",
                   new_callable=AsyncMock, return_value=True) as mock_xfer, \
             patch("purl_resolver.url_validator._fossil_probe_footer",
                   new_callable=AsyncMock) as mock_footer:
            result = await _fossil_probe("https://example.com/fossil", 5)
            assert result is True
            mock_xfer.assert_awaited_once()
            mock_footer.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_xfer_false_returns_false_no_footer(self):
        from purl_resolver.url_validator import _fossil_probe
        with patch("purl_resolver.url_validator._fossil_probe_xfer",
                   new_callable=AsyncMock, return_value=False) as mock_xfer, \
             patch("purl_resolver.url_validator._fossil_probe_footer",
                   new_callable=AsyncMock) as mock_footer:
            result = await _fossil_probe("https://example.com/plain", 5)
            assert result is False
            mock_xfer.assert_awaited_once()
            mock_footer.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_xfer_none_falls_back_to_footer(self):
        from purl_resolver.url_validator import _fossil_probe
        with patch("purl_resolver.url_validator._fossil_probe_xfer",
                   new_callable=AsyncMock, return_value=None) as mock_xfer, \
             patch("purl_resolver.url_validator._fossil_probe_footer",
                   new_callable=AsyncMock, return_value=True) as mock_footer:
            result = await _fossil_probe("https://example.com/fossil", 5)
            assert result is True
            mock_xfer.assert_awaited_once()
            mock_footer.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_both_none_returns_none(self):
        from purl_resolver.url_validator import _fossil_probe
        with patch("purl_resolver.url_validator._fossil_probe_xfer",
                   new_callable=AsyncMock, return_value=None) as mock_xfer, \
             patch("purl_resolver.url_validator._fossil_probe_footer",
                   new_callable=AsyncMock, return_value=None) as mock_footer:
            result = await _fossil_probe("https://example.com/fossil", 5)
            assert result is None
            mock_xfer.assert_awaited_once()
            mock_footer.assert_awaited_once()


class TestValidateUrlUsesCheckVcs:
    @pytest.mark.asyncio
    async def test_check_vcs_true_returns_valid(self):
        from purl_resolver.url_validator import validate_url
        with patch("purl_resolver.url_validator._check_connectivity", new_callable=AsyncMock, return_value=True), \
             patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head, \
             patch("purl_resolver.url_validator._check_vcs", new_callable=AsyncMock, return_value=True):
            mock_head.return_value = MagicMock(status_code=200, headers={}, url="https://example.com/repo")
            result = await validate_url("https://example.com/repo", timeout=5)
            assert result.result == UrlValidationResult.VALID

    @pytest.mark.asyncio
    async def test_check_vcs_false_returns_invalid(self):
        from purl_resolver.url_validator import validate_url
        with patch("purl_resolver.url_validator._check_connectivity", new_callable=AsyncMock, return_value=True), \
             patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head, \
             patch("purl_resolver.url_validator._check_vcs", new_callable=AsyncMock, return_value=False):
            mock_head.return_value = MagicMock(status_code=200, headers={}, url="https://example.com/repo")
            result = await validate_url("https://example.com/repo", timeout=5)
            assert result.result == UrlValidationResult.INVALID

    @pytest.mark.asyncio
    async def test_check_vcs_none_returns_network_error(self):
        from purl_resolver.url_validator import validate_url
        with patch("purl_resolver.url_validator._check_connectivity", new_callable=AsyncMock, return_value=True), \
             patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head, \
             patch("purl_resolver.url_validator._check_vcs", new_callable=AsyncMock, return_value=None):
            mock_head.return_value = MagicMock(status_code=200, headers={}, url="https://example.com/repo")
            result = await validate_url("https://example.com/repo", timeout=5)
            assert result.result == UrlValidationResult.NETWORK_ERROR