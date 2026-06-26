from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .settings_store import SettingsStore

logger = logging.getLogger(__name__)

_CONNECTIVITY_URL = "https://github.com"
_CONNECTIVITY_TIMEOUT = 2
_RATE_LIMIT_THRESHOLD = 5
_RATE_LIMIT_COOLDOWN = 60


class UrlValidationResult(Enum):
    VALID = "valid"
    INVALID = "invalid"
    NETWORK_ERROR = "network_error"
    RATE_LIMITED = "rate_limited"
    TOKEN_INVALID = "token_invalid"


@dataclass
class UrlValidationOutput:
    result: UrlValidationResult
    final_url: str | None = None


class _RateLimitTracker:
    _count: int = 0
    _cooldown_until: float = 0.0

    @classmethod
    def is_in_cooldown(cls) -> bool:
        if cls._cooldown_until > 0 and time.time() >= cls._cooldown_until:
            logger.info("Rate limit cooldown expired")
            cls._count = 0
            cls._cooldown_until = 0.0
        return cls._cooldown_until > 0 and time.time() < cls._cooldown_until

    @classmethod
    def record_rate_limit(cls) -> None:
        cls._count += 1
        if cls._count >= _RATE_LIMIT_THRESHOLD:
            cls._cooldown_until = time.time() + _RATE_LIMIT_COOLDOWN
            logger.warning(
                "Rate limit threshold reached (%d consecutive), "
                "entering %ds cooldown",
                cls._count, _RATE_LIMIT_COOLDOWN,
            )

    @classmethod
    def reset(cls) -> None:
        cls._count = 0
        cls._cooldown_until = 0.0


def _is_rate_limited(status: int, headers: dict) -> bool:
    if status == 429:
        return True
    if status == 403:
        remaining = headers.get("x-ratelimit-remaining") or headers.get("X-RateLimit-Remaining")
        if remaining is not None and int(remaining) <= 0:
            return True
    return False


async def _check_connectivity(github_token: str | None = None) -> bool:
    try:
        import httpx
        headers = {}
        if github_token:
            headers["Authorization"] = f"Bearer {github_token}"
        async with httpx.AsyncClient(timeout=_CONNECTIVITY_TIMEOUT) as client:
            resp = await client.head(_CONNECTIVITY_URL, headers=headers)
            return resp.status_code < 500
    except Exception:
        logger.warning("Connectivity probe to %s failed", _CONNECTIVITY_URL)
        return False


async def ensure_connectivity(github_token: str | None = None) -> bool:
    """Check connectivity once before batch processing. Raises on failure."""
    ok = await _check_connectivity(github_token=github_token)
    if not ok:
        raise ConnectionError(f"Cannot reach {_CONNECTIVITY_URL}")
    return True


async def _head_request(url: str, timeout: int, github_token: str | None = None):
    import httpx
    headers = {}
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        return await client.head(url, headers=headers)


async def _git_ls_remote(url: str, timeout: int, github_token: str | None = None) -> bool | None:
    """Return True if valid, False if not found, None if network error."""
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
        return None
    except FileNotFoundError:
        logger.warning("git not found, skipping git ls-remote check")
        return None
    except Exception:
        return None


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


async def validate_github_token(token: str) -> bool:
    """Validate a GitHub token by checking /rate_limit endpoint."""
    try:
        result = await _head_request(
            "https://api.github.com/rate_limit",
            timeout=5,
            github_token=token,
        )
        return result.status_code == 200
    except Exception:
        return False


async def validate_url(
    url: str,
    timeout: int,
    github_token: str | None = None,
    skip_connectivity_check: bool = False,
) -> UrlValidationOutput:
    if not url.startswith(("http://", "https://")):
        return UrlValidationOutput(UrlValidationResult.INVALID)

    if _RateLimitTracker.is_in_cooldown():
        return UrlValidationOutput(UrlValidationResult.RATE_LIMITED)

    if not skip_connectivity_check:
        try:
            github_ok = await _check_connectivity(github_token=github_token)
        except Exception:
            return UrlValidationOutput(UrlValidationResult.NETWORK_ERROR)

        if not github_ok:
            return UrlValidationOutput(UrlValidationResult.NETWORK_ERROR)

    try:
        resp = await _head_request(url, timeout, github_token=github_token)
        final_url = str(resp.url)
        if final_url != url:
            logger.info("URL redirected: %s -> %s", url, final_url)
        headers = dict(resp.headers)
        status = resp.status_code
    except Exception:
        _RateLimitTracker.reset()
        return UrlValidationOutput(UrlValidationResult.NETWORK_ERROR)

    if _is_rate_limited(status, headers):
        _RateLimitTracker.record_rate_limit()
        return UrlValidationOutput(UrlValidationResult.RATE_LIMITED, final_url=final_url)

    _RateLimitTracker.reset()

    if status in (401, 403) and github_token:
        return UrlValidationOutput(UrlValidationResult.TOKEN_INVALID, final_url=final_url)

    if status in (404, 405):
        return UrlValidationOutput(UrlValidationResult.INVALID, final_url=final_url)
    if status == 403:
        return UrlValidationOutput(UrlValidationResult.INVALID, final_url=final_url)
    if status >= 400:
        return UrlValidationOutput(UrlValidationResult.INVALID, final_url=final_url)

    try:
        git_result = await _check_vcs(final_url, timeout, github_token=github_token)
    except Exception:
        return UrlValidationOutput(UrlValidationResult.NETWORK_ERROR, final_url=final_url)
    if git_result is None:
        return UrlValidationOutput(UrlValidationResult.NETWORK_ERROR, final_url=final_url)
    if git_result is False:
        return UrlValidationOutput(UrlValidationResult.INVALID, final_url=final_url)

    return UrlValidationOutput(UrlValidationResult.VALID, final_url=final_url)


async def validate_url_with_retry(
    url: str,
    timeout: int,
    github_token: str | None = None,
    settings_store: SettingsStore | None = None,
    skip_connectivity_check: bool = False,
) -> UrlValidationOutput:
    voutput = await validate_url(
        url, timeout,
        github_token=github_token,
        skip_connectivity_check=skip_connectivity_check,
    )

    if voutput.result == UrlValidationResult.TOKEN_INVALID and settings_store is not None:
        logger.warning("GitHub token invalid, removing from settings")
        try:
            app_settings = settings_store.load()
            settings_store.save(app_settings.model_copy(update={"github_token": None}))
        except Exception:
            logger.warning("Failed to persist token removal to settings", exc_info=True)
        voutput = await validate_url(
            url, timeout,
            github_token=None,
            skip_connectivity_check=skip_connectivity_check,
        )

    return voutput
