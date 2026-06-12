from __future__ import annotations

import asyncio
import logging
import time
from enum import Enum

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


async def validate_url(url: str, timeout: int, github_token: str | None = None, skip_connectivity_check: bool = False) -> UrlValidationResult:
    if not url.startswith(("http://", "https://")):
        return UrlValidationResult.INVALID

    if _RateLimitTracker.is_in_cooldown():
        return UrlValidationResult.RATE_LIMITED

    if not skip_connectivity_check:
        try:
            github_ok = await _check_connectivity(github_token=github_token)
        except Exception:
            return UrlValidationResult.NETWORK_ERROR

        if not github_ok:
            return UrlValidationResult.NETWORK_ERROR

    try:
        resp = await _head_request(url, timeout, github_token=github_token)
        headers = dict(resp.headers)
        status = resp.status_code
    except Exception:
        _RateLimitTracker.reset()
        return UrlValidationResult.NETWORK_ERROR

    if _is_rate_limited(status, headers):
        _RateLimitTracker.record_rate_limit()
        return UrlValidationResult.RATE_LIMITED

    _RateLimitTracker.reset()

    if status in (401, 403) and github_token:
        return UrlValidationResult.TOKEN_INVALID

    if status in (404, 405):
        return UrlValidationResult.INVALID
    if status == 403:
        return UrlValidationResult.INVALID
    if status >= 400:
        return UrlValidationResult.INVALID

    try:
        git_result = await _git_ls_remote(url, timeout, github_token=github_token)
    except Exception:
        return UrlValidationResult.NETWORK_ERROR
    if git_result is None:
        return UrlValidationResult.NETWORK_ERROR
    if git_result is False:
        return UrlValidationResult.INVALID

    return UrlValidationResult.VALID
