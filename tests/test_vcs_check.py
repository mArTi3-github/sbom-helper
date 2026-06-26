from __future__ import annotations

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


class TestCheckVcsSequential:
    @pytest.mark.asyncio
    async def test_git_success_returns_true_no_other_probes_run(self):
        from purl_resolver.url_validator import _check_vcs
        git = _probe_returning(True)
        svn = _probe_returning(False)
        hg = _probe_returning(False)
        fossil = _probe_returning(False)
        with patch("purl_resolver.url_validator._git_probe", git), \
             patch("purl_resolver.url_validator._svn_probe", svn), \
             patch("purl_resolver.url_validator._hg_probe", hg), \
             patch("purl_resolver.url_validator._fossil_probe", fossil):
            result = await _check_vcs("https://github.com/psf/requests", 5)
            assert result is True
            git.assert_awaited_once()
            svn.assert_not_awaited()
            hg.assert_not_awaited()
            fossil.assert_not_awaited()

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


class TestFossilProbe:
    @pytest.mark.asyncio
    async def test_200_with_footer_returns_true(self):
        from purl_resolver.url_validator import _fossil_probe
        body = '<html><body><div id="footer">this page was generated in about 0.05s by fossil</div></body></html>'
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _make_httpx_response(200, body)
            result = await _fossil_probe("https://example.com/fossil", 5)
            assert result is True

    @pytest.mark.asyncio
    async def test_200_without_footer_returns_false(self):
        from purl_resolver.url_validator import _fossil_probe
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _make_httpx_response(200, "<html><body>Hello world</body></html>")
            result = await _fossil_probe("https://example.com/plain-html", 5)
            assert result is False

    @pytest.mark.asyncio
    async def test_404_returns_false(self):
        from purl_resolver.url_validator import _fossil_probe
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _make_httpx_response(404, "")
            result = await _fossil_probe("https://example.com/missing", 5)
            assert result is False

    @pytest.mark.asyncio
    async def test_regex_case_insensitive(self):
        from purl_resolver.url_validator import _fossil_probe
        body = '<html><div id="footer">This page was generated in about 0.1s by FOSSIL</div></html>'
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _make_httpx_response(200, body)
            result = await _fossil_probe("https://example.com/fossil", 5)
            assert result is True

    @pytest.mark.asyncio
    async def test_http_exception_returns_none(self):
        from purl_resolver.url_validator import _fossil_probe
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = TimeoutError
            result = await _fossil_probe("https://example.com/fossil", 5)
            assert result is None


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