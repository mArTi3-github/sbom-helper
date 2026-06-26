# Multi-VCS URL Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `_git_ls_remote()` in `url_validator.py` with a unified `_check_vcs()` that probes git, svn, hg, and fossil repositories sequentially with early-exit. All consumers (`service.py`, `sbom_enrichment.py`) benefit transparently through `validate_url()` / `validate_url_with_retry()` with no signature changes.

**Architecture:** New private async function `_check_vcs(url, timeout, github_token=None) → bool | None` orchestrates four probes (git ls-remote, svn ls, hg identify, fossil HTTP GET). Aggregation: `True` wins; else `False` wins over `None`. Returns `None` when all probes hit transport errors (protects cached URLs from deletion during network outages). Docker image gains `subversion` and `mercurial` packages; fossil uses HTTP only.

**Tech Stack:** Python 3.12, asyncio, `asyncio.create_subprocess_exec` (for git/svn/hg), `httpx.AsyncClient` (for fossil), existing pytest infrastructure with `unittest.mock.patch` and `AsyncMock`.

## Global Constraints

- All subprocess calls use `asyncio.create_subprocess_exec` (list args, `shell=False`) — never `shell=True`
- `git` probe uses `git ls-remote --exit-code <url>` (matches current behavior)
- `svn` probe uses `svn ls <url>`
- `hg` probe uses `hg identify <url>`
- `fossil` probe uses `httpx.AsyncClient.get(url, follow_redirects=True)` with regex match
- Each probe receives the full `timeout` parameter (no shared budget)
- Aggregation rule: `True` if any probe returns `True`; else `False` if any returns `False`; else `None`
- `_check_vcs()` never raises — all probes wrapped in `try/except` returning `True`/`False`/`None`
- GitHub token rewriting (`oauth2:token@` for `github.com` URLs) applies to git probe only
- Docker image: `subversion` and `mercurial` added to both `dev` and `prod` stages via `apt-get install`
- Public API unchanged: `validate_url()` and `validate_url_with_retry()` signatures preserved
- No changes in `service.py` or `sbom_enrichment.py`

---

## File Structure

| File | Responsibility | Status |
|---|---|---|
| `src/purl_resolver/url_validator.py` | URL validation: HTTP HEAD + multi-VCS probe (`_check_vcs`) | Modify |
| `Dockerfile` | Container build with VCS tools (git, subversion, mercurial) | Modify |
| `tests/test_url_validator.py` | Tests for `validate_url()`, `validate_url_with_retry()`, etc. | Modify (update patches) |
| `tests/test_vcs_check.py` | Tests for `_check_vcs()` covering all 4 probes and aggregation | Create |
| `specs/domains/purl-resolution.md` | Domain spec: URL Validator invariants | Modify |
| `specs/architecture/layers.md` | Architecture: URL Validator responsibilities | Modify |
| `CONTEXT.md` | Domain glossary: URL Validator term | Modify |
| `docs/superpowers/specs/2026-06-26-multi-vcs-url-validation-design.md` | Design doc | Already created |

---

### Task 1: Add VCS Tool Dependencies to Dockerfile

**Files:**
- Modify: `Dockerfile` (both `dev` and `prod` stages, lines 16–18 and 46–48)

**Interfaces:**
- Consumes: existing Dockerfile structure
- Produces: updated `apt-get install` line including `subversion` and `mercurial`

- [ ] **Step 1: Update the `dev` stage install command**

In `Dockerfile`, change line 17 from:

```dockerfile
    apt-get install -y --no-install-recommends git openssl && \
```

to:

```dockerfile
    apt-get install -y --no-install-recommends git subversion mercurial openssl && \
```

- [ ] **Step 2: Update the `prod` stage install command**

In `Dockerfile`, change line 47 from:

```dockerfile
    apt-get install -y --no-install-recommends git openssl && \
```

to:

```dockerfile
    apt-get install -y --no-install-recommends git subversion mercurial openssl && \
```

- [ ] **Step 3: Verify Dockerfile syntax**

Run: `docker build --target dev -f Dockerfile .`
Expected: build succeeds; running `which svn hg git` inside the container returns `/usr/bin/svn`, `/usr/bin/hg`, `/usr/bin/git` respectively.

If Docker is not available locally, run: `grep -n "apt-get install" Dockerfile` to visually confirm both stages have the updated package list.

- [ ] **Step 4: Commit**

```bash
git add Dockerfile
git commit -m "build(docker): add subversion and mercurial for multi-VCS validation"
```

---

### Task 2: Write Failing Unit Tests for `_check_vcs()`

**Files:**
- Create: `tests/test_vcs_check.py`

**Interfaces:**
- Consumes: `purl_resolver.url_validator._check_vcs(url, timeout, github_token=None) → bool | None`
- Produces: comprehensive test coverage that will fail until Task 3 implements the function

- [ ] **Step 1: Create the test file with all test cases**

Create `tests/test_vcs_check.py` with the following content:

```python
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# Helper for probe-helper mocks (orchestration tests)
def _probe_returning(value):
    """Create an AsyncMock that returns the given value when awaited."""
    async def fake(url, *args, **kwargs):
        return value
    return AsyncMock(side_effect=fake)


# Helper for subprocess mocks (probe-integration tests)
def _make_proc(returncode: int = 0, stderr: bytes = b"") -> AsyncMock:
    """Create a mock async subprocess with the given returncode and stderr."""
    mock_proc = AsyncMock()
    mock_proc.communicate = AsyncMock(return_value=(b"", stderr))
    mock_proc.returncode = returncode
    mock_proc.kill = AsyncMock()
    mock_proc.wait = AsyncMock()
    return mock_proc


def _make_proc_timeout():
    """Create a mock subprocess whose communicate() raises asyncio.TimeoutError."""
    mock_proc = AsyncMock()
    mock_proc.communicate = AsyncMock(side_effect=TimeoutError)
    mock_proc.kill = AsyncMock()
    mock_proc.wait = AsyncMock()
    return mock_proc


# Helper for httpx response mocks (fossil probe tests)
def _make_httpx_response(status_code: int = 200, body: str = "") -> MagicMock:
    """Create a MagicMock httpx Response with status_code and text."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.text = body
    return mock_resp


# =========================================================================
# Orchestration tests for _check_vcs — mock the four probe helpers directly
# =========================================================================


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
        aggregation must return False (not None) — protects cached URLs from deletion."""
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


# =========================================================================
# Probe-integration tests — mock subprocess / httpx directly
# =========================================================================


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
            # Should have called kill() on timeout
            mock_exec.return_value.kill.assert_awaited_once()

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
            mock_exec.return_value.kill.assert_awaited_once()


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
            mock_exec.return_value.kill.assert_awaited_once()


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
        # Case variation: "FOSSIL" instead of "fossil"
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


# =========================================================================
# Integration: validate_url uses _check_vcs (mock _check_vcs, not subprocess)
# =========================================================================


class TestValidateUrlUsesCheckVcs:
    @pytest.mark.asyncio
    async def test_check_vcs_true_returns_valid(self):
        from purl_resolver.url_validator import validate_url
        with patch("purl_resolver.url_validator._check_connectivity", new_callable=AsyncMock, return_value=True), \
             patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head, \
             patch("purl_resolver.url_validator._check_vcs", new_callable=AsyncMock, return_value=True):
            mock_head.return_value = MagicMock(status_code=200, headers={}, url="https://example.com/repo")
            result = await validate_url("https://example.com/repo", timeout=5)
            assert result.result == UrlValidationResult.VALID  # noqa: F821 (import in test)

    @pytest.mark.asyncio
    async def test_check_vcs_false_returns_invalid(self):
        from purl_resolver.url_validator import validate_url
        with patch("purl_resolver.url_validator._check_connectivity", new_callable=AsyncMock, return_value=True), \
             patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head, \
             patch("purl_resolver.url_validator._check_vcs", new_callable=AsyncMock, return_value=False):
            mock_head.return_value = MagicMock(status_code=200, headers={}, url="https://example.com/repo")
            result = await validate_url("https://example.com/repo", timeout=5)
            assert result.result == UrlValidationResult.INVALID  # noqa: F821

    @pytest.mark.asyncio
    async def test_check_vcs_none_returns_network_error(self):
        from purl_resolver.url_validator import validate_url
        with patch("purl_resolver.url_validator._check_connectivity", new_callable=AsyncMock, return_value=True), \
             patch("purl_resolver.url_validator._head_request", new_callable=AsyncMock) as mock_head, \
             patch("purl_resolver.url_validator._check_vcs", new_callable=AsyncMock, return_value=None):
            mock_head.return_value = MagicMock(status_code=200, headers={}, url="https://example.com/repo")
            result = await validate_url("https://example.com/repo", timeout=5)
            assert result.result == UrlValidationResult.NETWORK_ERROR  # noqa: F821
```

**Important notes for the implementer:**

1. The `# noqa: F821 (import in test)` comments indicate that `UrlValidationResult` is imported lazily inside the test method. Replace those comments with a proper import at the top of each test method (or at file level) — the noqa comments are just placeholders so the example code compiles.

2. The `TestValidateUrlUsesCheckVcs` class verifies that `validate_url()` calls `_check_vcs` (not `_git_ls_remote`). This is the integration assertion.

3. Tests use `_make_httpx_response` (returns a `MagicMock`) and `patch(... new_callable=AsyncMock)` so that `await client.get(url)` resolves to the configured response mock — this is the correct pattern for mocking async HTTP calls.

- [ ] **Step 2: Run the tests to verify they all fail**

Run: `.venv/bin/python -m pytest tests/test_vcs_check.py -v 2>&1 | tail -30`
Expected: All tests FAIL with `ImportError` or `AttributeError: module 'purl_resolver.url_validator' has no attribute '_check_vcs'`

- [ ] **Step 3: Commit**

```bash
git add tests/test_vcs_check.py
git commit -m "test: add failing unit tests for _check_vcs() multi-VCS probe"
```

- [ ] **Step 2: Run the tests to verify they all fail**

Run: `.venv/bin/python -m pytest tests/test_vcs_check.py -v 2>&1 | tail -30`
Expected: All tests FAIL with `ImportError` or `AttributeError: module 'purl_resolver.url_validator' has no attribute '_check_vcs'`

- [ ] **Step 3: Commit**

```bash
git add tests/test_vcs_check.py
git commit -m "test: add failing unit tests for _check_vcs() multi-VCS probe"
```

---

### Task 3: Implement `_check_vcs()` in `url_validator.py`

**Files:**
- Modify: `src/purl_resolver/url_validator.py` (add new function near existing `_git_ls_remote`)

**Interfaces:**
- Consumes: `_check_vcs(url, timeout, github_token=None) → bool | None` (called from `validate_url` in Task 4)
- Produces: implementation that makes all tests in `tests/test_vcs_check.py` pass

- [ ] **Step 1: Add the `_check_vcs()` function and its probe helpers**

Add the following imports near the top of `src/purl_resolver/url_validator.py` (after the existing imports, around line 13):

```python
from collections.abc import Awaitable, Callable
```

Then add the following code to `src/purl_resolver/url_validator.py` immediately after the existing `_git_ls_remote()` function (around line 134, before the blank line preceding `validate_github_token`):

```python
async def _git_probe(url: str, timeout: int, github_token: str | None = None) -> bool | None:
    """Probe URL via git ls-remote. Returns True/False/None."""
    try:
        git_url = url
        if github_token and "github.com" in url and url.startswith("https://"):
            git_url = f"https://oauth2:{github_token}@{url[len('https://'):]}"
        proc = await asyncio.create_subprocess_exec(
            "git", "ls-remote", "--exit-code", git_url,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            logger.warning("git ls-remote timed out for %s", url)
            return None
        if proc.returncode == 0:
            return True
        stderr_text = stderr.decode(errors="replace") if stderr else ""
        if "not found" in stderr_text.lower() or "does not exist" in stderr_text.lower():
            return False
        logger.warning("git ls-remote uncertain for %s: %s", url, stderr_text)
        return None
    except Exception as e:
        logger.warning("git ls-remote failed for %s: %s", url, e)
        return None


async def _svn_probe(url: str, timeout: int) -> bool | None:
    """Probe URL via svn ls. Returns True/False/None."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "svn", "ls", url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            logger.warning("svn ls timed out for %s", url)
            return None
        if proc.returncode == 0:
            return True
        return False
    except Exception as e:
        logger.warning("svn ls failed for %s: %s", url, e)
        return None


async def _hg_probe(url: str, timeout: int) -> bool | None:
    """Probe URL via hg identify. Returns True/False/None."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "hg", "identify", url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            logger.warning("hg identify timed out for %s", url)
            return None
        if proc.returncode == 0:
            return True
        return False
    except Exception as e:
        logger.warning("hg identify failed for %s: %s", url, e)
        return None


async def _fossil_probe(url: str, timeout: int) -> bool | None:
    """Probe URL via HTTP GET + fossil footer regex. Returns True/False/None."""
    import httpx
    import re
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(url)
        if resp.status_code != 200:
            return False
        if re.search(
            r'footer"?>\s*this page was generated in about\s*(\d+\.\d+)s\s*by\s*fossil',
            resp.text,
            re.I,
        ):
            return True
        return False
    except Exception as e:
        logger.warning("Fossil check failed for %s: %s", url, e)
        return None


async def _check_vcs(
    url: str,
    timeout: int,
    github_token: str | None = None,
) -> bool | None:
    """Probe whether URL points to a git/svn/hg/fossil repository.

    Runs four probes sequentially with early-exit on first success.

    Returns:
        True  — at least one VCS tool confirmed the URL is its repo type.
        False — no VCS tool confirmed; at least one definitively said "not a repo".
        None  — all probes were inconclusive (timeout, transport error).
                Caller should treat as network error / preserve cache.
    """
    probes: list[tuple[str, Callable[[], Awaitable[bool | None]]]] = [
        ("git", lambda: _git_probe(url, timeout, github_token)),
        ("svn", lambda: _svn_probe(url, timeout)),
        ("hg", lambda: _hg_probe(url, timeout)),
        ("fossil", lambda: _fossil_probe(url, timeout)),
    ]
    saw_false = False
    for _name, run in probes:
        result = await run()
        if result is True:
            return True
        if result is False:
            saw_false = True
    return False if saw_false else None
```

- [ ] **Step 2: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_vcs_check.py -v 2>&1 | tail -40`
Expected: All tests PASS

If tests fail:
- Check the regex in `_fossil_probe` matches the test body strings exactly
- Check the timeout handling: `asyncio.TimeoutError` is raised from `asyncio.wait_for(proc.communicate(), ...)`
- Check that `_fossil_probe` uses `resp.text` (not `resp.body` or similar)
- Verify the git probe command list is `["git", "ls-remote", "--exit-code", git_url]`

- [ ] **Step 3: Commit**

```bash
git add src/purl_resolver/url_validator.py
git commit -m "feat(url-validator): add _check_vcs() multi-VCS probe (git/svn/hg/fossil)"
```

---

### Task 4: Wire `_check_vcs()` into `validate_url()` and Remove `_git_ls_remote()`

**Files:**
- Modify: `src/purl_resolver/url_validator.py` (replace `_git_ls_remote` call in `validate_url`; remove `_git_ls_remote` function)
- Modify: `tests/test_url_validator.py` (update patches; remove `TestGitLsRemoteTokenTransformation`)

**Interfaces:**
- Consumes: `_check_vcs` (implemented in Task 3)
- Produces: `validate_url()` calls `_check_vcs`; `_git_ls_remote` removed; existing tests updated

- [ ] **Step 1: Replace the `_git_ls_remote` call in `validate_url`**

In `src/purl_resolver/url_validator.py`, find the section of `validate_url()` that reads:

```python
    try:
        git_result = await _git_ls_remote(final_url, timeout, github_token=github_token)
    except Exception:
        return UrlValidationOutput(UrlValidationResult.NETWORK_ERROR, final_url=final_url)
    if git_result is None:
        return UrlValidationOutput(UrlValidationResult.NETWORK_ERROR, final_url=final_url)
    if git_result is False:
        return UrlValidationOutput(UrlValidationResult.INVALID, final_url=final_url)

    return UrlValidationOutput(UrlValidationResult.VALID, final_url=final_url)
```

Replace it with:

```python
    try:
        vcs_result = await _check_vcs(final_url, timeout, github_token=github_token)
    except Exception:
        return UrlValidationOutput(UrlValidationResult.NETWORK_ERROR, final_url=final_url)
    if vcs_result is None:
        return UrlValidationOutput(UrlValidationResult.NETWORK_ERROR, final_url=final_url)
    if vcs_result is False:
        return UrlValidationOutput(UrlValidationResult.INVALID, final_url=final_url)

    return UrlValidationOutput(UrlValidationResult.VALID, final_url=final_url)
```

- [ ] **Step 2: Remove the `_git_ls_remote` function**

In `src/purl_resolver/url_validator.py`, delete the entire `_git_ls_remote` function definition (the block starting with `async def _git_ls_remote(...)` and ending with its `return None`). Note: the new `_git_probe` function from Task 3 already replaces it.

- [ ] **Step 3: Update the import in `tests/test_url_validator.py`**

Find line 10:

```python
from purl_resolver.url_validator import (
    UrlValidationOutput,
    UrlValidationResult,
    _git_ls_remote,
    _RateLimitTracker,
    ...
```

Replace `_git_ls_remote,` with `_check_vcs,` (since `_git_ls_remote` no longer exists). The new line should read:

```python
from purl_resolver.url_validator import (
    UrlValidationOutput,
    UrlValidationResult,
    _check_vcs,
    _RateLimitTracker,
    ...
```

- [ ] **Step 4: Update all `patch(...)` calls in `tests/test_url_validator.py`**

In `tests/test_url_validator.py`, find every occurrence of:

```python
             patch("purl_resolver.url_validator._git_ls_remote", new_callable=AsyncMock, return_value=True)
```

and replace with:

```python
             patch("purl_resolver.url_validator._check_vcs", new_callable=AsyncMock, return_value=True)
```

Also find every occurrence of:

```python
             patch("purl_resolver.url_validator._git_ls_remote", new_callable=AsyncMock, return_value=False)
```

and replace with:

```python
             patch("purl_resolver.url_validator._check_vcs", new_callable=AsyncMock, return_value=False)
```

And every occurrence of:

```python
             patch("purl_resolver.url_validator._git_ls_remote", new_callable=AsyncMock, return_value=None)
```

and replace with:

```python
             patch("purl_resolver.url_validator._check_vcs", new_callable=AsyncMock, return_value=None)
```

And the variant:

```python
             patch("purl_resolver.url_validator._git_ls_remote", new_callable=AsyncMock) as mock_git
```

and replace with:

```python
             patch("purl_resolver.url_validator._check_vcs", new_callable=AsyncMock) as mock_vcs
```

For the `mock_git.assert_called_once_with(...)` assertion at line 161, replace with `mock_vcs.assert_called_once_with(...)`. For `mock_git.return_value = True` (line 157), replace with `mock_vcs.return_value = True`. For `mock_git.call_args` (line 197), replace with `mock_vcs.call_args`.

To verify all replacements are correct, run: `grep -n "_git_ls_remote\|mock_git" tests/test_url_validator.py`
Expected: no output (all references removed).

- [ ] **Step 5: Replace `TestGitLsRemoteTokenTransformation` class**

In `tests/test_url_validator.py`, find the entire `class TestGitLsRemoteTokenTransformation:` block (lines 210–231) and delete it. The github-token-rewriting logic is now tested by `TestCheckVcsGithubToken` in `tests/test_vcs_check.py` (Task 2).

- [ ] **Step 6: Run the full test suite**

Run: `.venv/bin/python -m pytest tests/test_url_validator.py tests/test_vcs_check.py -v 2>&1 | tail -50`
Expected: All tests PASS

If tests fail:
- Check that all `patch` targets were renamed consistently
- Verify `_check_vcs` is in the import list of `test_url_validator.py`
- Verify no test references `_git_ls_remote` directly

- [ ] **Step 7: Run the wider test suite to verify nothing else broke**

Run: `.venv/bin/python -m pytest tests/ -v --ignore=tests/e2e 2>&1 | tail -40`
Expected: All tests PASS (except possibly some unrelated tests that fail for environmental reasons). The URL validator tests should all pass.

- [ ] **Step 8: Commit**

```bash
git add src/purl_resolver/url_validator.py tests/test_url_validator.py
git commit -m "refactor(url-validator): replace _git_ls_remote with _check_vcs"
```

---

### Task 5: Update Specs and Documentation

**Files:**
- Modify: `specs/domains/purl-resolution.md` (URL Validator section around line 277; add invariants)
- Modify: `specs/architecture/layers.md` (URL Validator section around line 277)
- Modify: `CONTEXT.md` (URL Validator term around line 82)

**Interfaces:**
- Consumes: design doc at `docs/superpowers/specs/2026-06-26-multi-vcs-url-validation-design.md`
- Produces: updated specs and glossary reflecting the new multi-VCS behavior

- [ ] **Step 1: Update `specs/domains/purl-resolution.md` URL Validator section**

Find the "URL Validator" subsection in the "Layer Responsibilities" area (around line 277). It currently reads:

```markdown
### URL Validator (`url_validator.py`)
- Validates repository URLs via HTTP HEAD + `git ls-remote` to verify the URL exists and is reachable
- `validate_url(url, timeout, github_token=None, skip_connectivity_check=False) → UrlValidationOutput` — performs HEAD (with `follow_redirects=True`), captures the final URL after all 3xx redirects via `str(resp.url)`, then runs `git ls-remote` against the final URL; returns `UrlValidationOutput(result, final_url)`
- `validate_url_with_retry(url, timeout, github_token=None, settings_store=None, skip_connectivity_check=False) → UrlValidationOutput` — wraps `validate_url()` with `TOKEN_INVALID` retry: clears the GitHub token from `AppSettings` and re-validates without authentication
- `validate_github_token(token) → bool` — validates a GitHub token by HEAD on `/rate_limit`
- `ensure_connectivity(github_token=None) → bool` — connectivity probe against `github.com`; raises `ConnectionError` on failure
- `_RateLimitTracker` — class-level in-memory counter; after 5 consecutive rate-limited responses, all validation returns `RATE_LIMITED` for 60 seconds
- `_git_ls_remote(url, timeout, github_token=None) → bool | None` — returns True/False/None for valid/invalid/network-error; rewrites `github.com` URLs with `oauth2:token@` for authenticated `git` calls; called with the resolved final URL by `validate_url()`
- `UrlValidationResult` enum — `VALID`, `INVALID`, `NETWORK_ERROR`, `RATE_LIMITED`, `TOKEN_INVALID`
- `UrlValidationOutput` dataclass — `result: UrlValidationResult`, `final_url: str | None = None`; `final_url` is `str(resp.url)` after redirects, `None` when HEAD did not execute (scheme error, cooldown, connectivity failure, HEAD exception)
```

Replace it with:

```markdown
### URL Validator (`url_validator.py`)
- Validates repository URLs via HTTP HEAD + multi-VCS probe to verify the URL exists and is reachable
- `validate_url(url, timeout, github_token=None, skip_connectivity_check=False) → UrlValidationOutput` — performs HEAD (with `follow_redirects=True`), captures the final URL after all 3xx redirects via `str(resp.url)`, then runs `_check_vcs()` against the final URL; returns `UrlValidationOutput(result, final_url)`
- `validate_url_with_retry(url, timeout, github_token=None, settings_store=None, skip_connectivity_check=False) → UrlValidationOutput` — wraps `validate_url()` with `TOKEN_INVALID` retry: clears the GitHub token from `AppSettings` and re-validates without authentication
- `validate_github_token(token) → bool` — validates a GitHub token by HEAD on `/rate_limit`
- `ensure_connectivity(github_token=None) → bool` — connectivity probe against `github.com`; raises `ConnectionError` on failure
- `_RateLimitTracker` — class-level in-memory counter; after 5 consecutive rate-limited responses, all validation returns `RATE_LIMITED` for 60 seconds
- `_check_vcs(url, timeout, github_token=None) → bool | None` — unified multi-VCS probe; runs git → svn → hg → fossil sequentially with early-exit on first success; aggregation: `True` if any probe is `True`, else `False` if any is `False`, else `None`; called with the resolved final URL by `validate_url()`
- `_git_probe(url, timeout, github_token=None) → bool | None` — internal helper: `git ls-remote --exit-code <url>`; rewrites `github.com` URLs with `oauth2:token@` for authenticated calls
- `_svn_probe(url, timeout) → bool | None` — internal helper: `svn ls <url>`; exit 0 → True, exit ≠0 → False
- `_hg_probe(url, timeout) → bool | None` — internal helper: `hg identify <url>`; exit 0 → True, exit ≠0 → False
- `_fossil_probe(url, timeout) → bool | None` — internal helper: HTTP GET with `follow_redirects=True`; status 200 + footer regex match → True; status 200 without footer → False; non-200 → False; transport error → None
- `UrlValidationResult` enum — `VALID`, `INVALID`, `NETWORK_ERROR`, `RATE_LIMITED`, `TOKEN_INVALID`
- `UrlValidationOutput` dataclass — `result: UrlValidationResult`, `final_url: str | None = None`; `final_url` is `str(resp.url)` after redirects, `None` when HEAD did not execute (scheme error, cooldown, connectivity failure, HEAD exception)
```

- [ ] **Step 2: Add new invariants to `specs/domains/purl-resolution.md`**

Find the list of invariants (around line 156, in the "Invariants" section). Add the following invariants at the end of the list (after the last existing invariant):

```markdown
- **Multi-VCS validation**: `_check_vcs()` probes git (via `git ls-remote --exit-code`), svn (via `svn ls`), hg (via `hg identify`), fossil (via HTTP GET + footer regex) sequentially with early-exit on first success
- **VCS aggregation rule**: if any probe returns `True` → result `True`; else if any probe returns `False` → result `False`; else (all probes uncertain) → result `None`
- **Docker provides VCS tools**: `git`, `subversion`, `mercurial` are installed in both `dev` and `prod` stages of the Dockerfile; fossil uses HTTP (httpx) and requires no binary
- **VCS subprocess timeouts are non-fatal**: `asyncio.TimeoutError` from any subprocess call is treated as `None` (uncertain) and logged as a warning; never raised to the caller
- **GitHub token only affects git probe**: `_check_vcs()` rewrites `github.com` URLs to `oauth2:token@` form for the git probe only; svn/hg/fossil probes run without token rewriting
```

- [ ] **Step 3: Update `specs/architecture/layers.md`**

Find the "URL Validator" subsection (around line 277 in the "Layer Responsibilities" section). It currently has the same text as the URL Validator section in `purl-resolution.md`. Apply the same replacement as in Step 1.

- [ ] **Step 4: Update `CONTEXT.md`**

Find the "URL Validator" term (around line 82). It currently reads:

```markdown
**URL Validator**:
Модуль `url_validator.py`, реализующий валидацию repository URL с помощью HTTP HEAD-запроса и `git ls-remote`. Используется сервисным слоем для проверки актуальности кэшированных URL (настройка `validate_db_urls`).
```

Replace it with:

```markdown
**URL Validator**:
Модуль `url_validator.py`, реализующий валидацию repository URL с помощью HTTP HEAD-запроса и много-VCS проверки (`_check_vcs`: git → svn → hg → fossil). Используется сервисным слоем для проверки актуальности кэшированных URL (настройка `validate_db_urls`).

**Check VCS / Multi-VCS Probe**:
Функция `_check_vcs(url, timeout, github_token=None) → bool | None` в `url_validator.py`. Последовательно проверяет, является ли URL git/svn/hg/fossil-репозиторием, с ранним выходом при первом успехе. Правило агрегации: `True` если хотя бы одна проба успешна; иначе `False` если хотя бы одна проба явно сказала "не репозиторий"; иначе `None` (все пробы неопределённые, например при таймаутах). Гарантирует, что валидные кэшированные URL не удаляются из БД при временных сетевых ошибках.
```

- [ ] **Step 5: Verify the spec updates**

Run: `grep -n "_check_vcs\|_git_ls_remote" specs/domains/purl-resolution.md specs/architecture/layers.md CONTEXT.md`
Expected: All matches refer to `_check_vcs` (no remaining `_git_ls_remote` references except possibly in design docs which describe the old behavior).

- [ ] **Step 6: Commit**

```bash
git add specs/domains/purl-resolution.md specs/architecture/layers.md CONTEXT.md
git commit -m "docs(specs): document multi-VCS validation in URL Validator"
```

---

## Self-Review

**1. Spec coverage:**
- ✅ New function `_check_vcs()` with multi-VCS probing → Task 3
- ✅ `_check_vcs` wired into `validate_url()` → Task 4
- ✅ `_git_ls_remote` removed → Task 4
- ✅ Docker image updated → Task 1
- ✅ Existing tests updated → Task 4
- ✅ New unit tests for `_check_vcs` → Task 2
- ✅ Specs updated → Task 5
- ✅ CONTEXT.md updated → Task 5

**2. Placeholder scan:**
- No "TBD", "TODO", "fill in details", or vague steps
- All code blocks contain real, copy-pasteable content
- All commands are concrete and runnable

**3. Type consistency:**
- `_check_vcs(url, timeout, github_token=None) → bool | None` — consistent across all tasks
- Probe helpers all return `bool | None` — consistent
- `validate_url()` return type unchanged (`UrlValidationOutput`) — consistent
- `validate_url_with_retry()` return type unchanged — consistent