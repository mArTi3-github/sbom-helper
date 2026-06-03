from __future__ import annotations

import asyncio
import logging
import subprocess
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


async def _check_connectivity() -> bool:
    try:
        import httpx
        async with httpx.AsyncClient(timeout=_CONNECTIVITY_TIMEOUT) as client:
            resp = await client.head(_CONNECTIVITY_URL)
            return resp.status_code < 500
    except Exception:
        logger.warning("Connectivity probe to %s failed", _CONNECTIVITY_URL)
        return False


async def _head_request(url: str, timeout: int):
    import httpx
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        return await client.head(url)


async def _git_ls_remote(url: str, timeout: int) -> bool:
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "ls-remote", "--exit-code", url,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            logger.warning("git ls-remote timed out for %s", url)
            return False
        return proc.returncode == 0
    except FileNotFoundError:
        logger.warning("git not found, skipping git ls-remote check")
        return True


async def validate_url(url: str, timeout: int) -> UrlValidationResult:
    if _RateLimitTracker.is_in_cooldown():
        return UrlValidationResult.VALID

    try:
        github_ok = await _check_connectivity()
    except Exception:
        return UrlValidationResult.NETWORK_ERROR

    if not github_ok:
        return UrlValidationResult.NETWORK_ERROR

    try:
        resp = await _head_request(url, timeout)
        headers = dict(resp.headers)
        status = resp.status
    except Exception:
        _RateLimitTracker.reset()
        return UrlValidationResult.INVALID

    if _is_rate_limited(status, headers):
        _RateLimitTracker.record_rate_limit()
        return UrlValidationResult.RATE_LIMITED

    _RateLimitTracker.reset()

    if status in (404, 405):
        return UrlValidationResult.INVALID
    if status == 403:
        return UrlValidationResult.INVALID
    if status >= 400:
        return UrlValidationResult.INVALID

    git_ok = await _git_ls_remote(url, timeout)
    if not git_ok:
        return UrlValidationResult.INVALID

    return UrlValidationResult.VALID
