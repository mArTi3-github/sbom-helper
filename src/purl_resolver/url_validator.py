from __future__ import annotations

import asyncio
import ipaddress
import logging
import os
import signal
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

import httpx

if TYPE_CHECKING:
    from .settings_store import SettingsStore

logger = logging.getLogger(__name__)

_CONNECTIVITY_URL = "https://github.com"
_CONNECTIVITY_TIMEOUT = 2

_PRIVATE_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("192.88.99.0/24"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("240.0.0.0/4"),
    ipaddress.ip_network("255.255.255.255/32"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("ff00::/8"),
]


async def _is_private_url(url: str) -> bool:
    """Resolve hostname and check if it points to a private/reserved IP range."""
    host = urlsplit(url).hostname
    if not host:
        return False
    try:
        ips = await asyncio.wait_for(
            asyncio.to_thread(socket.getaddrinfo, host, None),
            timeout=5.0,
        )
    except (socket.gaierror, asyncio.TimeoutError):
        return False
    for _, _, _, _, sockaddr in ips:
        ip = ipaddress.ip_address(sockaddr[0])
        if any(ip in net for net in _PRIVATE_NETWORKS):
            logger.warning("URL %s resolves to private IP %s", url, ip)
            return True
    return False


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


async def ensure_connectivity(
    github_token: str | None = None,
    url: str | None = None,
    timeout: int | None = None,
) -> bool:
    if url is not None and url == "":
        return True
    probe_url = url or _CONNECTIVITY_URL
    probe_timeout = timeout or _CONNECTIVITY_TIMEOUT
    if await _is_private_url(probe_url):
        raise ConnectionError(f"Probe URL resolves to a private address: {probe_url}")
    try:
        headers = {}
        hostname = urlsplit(probe_url).hostname
        if github_token and hostname and (hostname == "github.com" or hostname.endswith(".github.com")):
            headers["Authorization"] = f"Bearer {github_token}"
        async with httpx.AsyncClient(timeout=probe_timeout) as client:
            resp = await client.head(probe_url, headers=headers)
            ok = resp.status_code < 500
    except httpx.RequestError:
        logger.warning("Connectivity probe to %s failed", probe_url)
        ok = False
    if not ok:
        raise ConnectionError(f"Cannot reach {probe_url}")
    return True


async def _head_request(url: str, timeout: int, github_token: str | None = None):
    if await _is_private_url(url):
        raise ConnectionError(f"Refusing HEAD request to private URL: {url}")
    headers = {}
    hostname = urlsplit(url).hostname
    if github_token and hostname and (hostname == "github.com" or hostname.endswith(".github.com")):
        headers["Authorization"] = f"Bearer {github_token}"
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        resp = await client.head(url, headers=headers)
    if await _is_private_url(str(resp.url)):
        raise ConnectionError(f"HEAD redirect target is private: {resp.url}")
    return resp


async def _git_probe(url: str, timeout: int, github_token: str | None = None) -> bool | None:
    """Probe URL via git ls-remote. Returns True/False/None."""
    try:
        git_url = url
        hostname = urlsplit(url).hostname
        if github_token and hostname and (hostname == "github.com" or hostname.endswith(".github.com")) and url.startswith("https://"):
            git_url = f"https://oauth2:{github_token}@{url[len('https://'):]}"
        proc = await asyncio.create_subprocess_exec(
            "git", "ls-remote", "--exit-code", git_url, "HEAD",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        try:
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            if isinstance(proc.pid, int) and proc.pid > 1:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass
            await proc.wait()
            logger.warning("git ls-remote timed out for %s", url)
            return None
        if proc.returncode in (0, 2):
            logger.info("git probe confirmed %s as git repository", url)
            return True
        stderr_text = stderr.decode(errors="replace") if stderr else ""
        if "not found" in stderr_text.lower() or "does not exist" in stderr_text.lower():
            return False
        logger.warning("git ls-remote uncertain for %s: %s", url, stderr_text)
        return None
    except (OSError, asyncio.TimeoutError) as e:
        logger.warning("git ls-remote failed for %s: %s", url, e)
        return None


async def _svn_probe(url: str, timeout: int) -> bool | None:
    """Probe URL via svn ls. Returns True/False/None."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "svn", "ls", url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        try:
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            if isinstance(proc.pid, int) and proc.pid > 1:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass
            await proc.wait()
            logger.warning("svn ls timed out for %s", url)
            return None
        if proc.returncode == 0:
            logger.info("svn probe confirmed %s as svn repository", url)
            return True
        return False
    except (OSError, asyncio.TimeoutError) as e:
        logger.warning("svn ls failed for %s: %s", url, e)
        return None


async def _hg_probe(url: str, timeout: int) -> bool | None:
    """Probe URL via hg identify. Returns True/False/None."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "hg", "identify", url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        try:
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            if isinstance(proc.pid, int) and proc.pid > 1:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass
            await proc.wait()
            logger.warning("hg identify timed out for %s", url)
            return None
        if proc.returncode == 0:
            logger.info("hg probe confirmed %s as hg repository", url)
            return True
        return False
    except (OSError, asyncio.TimeoutError) as e:
        logger.warning("hg identify failed for %s: %s", url, e)
        return None


async def _fossil_probe_xfer(url: str, timeout: int) -> bool | None:
    """Probe URL via Fossil sync protocol (/xfer endpoint). Returns True/False/None.

    Sends a minimal POST to <url>/xfer with Content-Type set to
    application/x-fossil-debug. A live Fossil server will respond with
    a fossil-specific Content-Type, confirming this is a Fossil sync endpoint.
    """
    if await _is_private_url(url):
        logger.warning("Refusing xfer probe to private URL: %s", url)
        return None
    from urllib.parse import urlsplit, urlunsplit

    probe_url = urlunsplit((*urlsplit(url)[:2], urlsplit(url).path.rstrip("/") + "/xfer", "", ""))

    headers = {
        "Content-Type": "application/x-fossil-debug",
        "Accept": "application/x-fossil-debug",
        "User-Agent": "fossil-probe/1.0",
    }
    body = b"# fossil-probe\n"

    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            async with client.stream("POST", probe_url, headers=headers, content=body) as resp:
                if await _is_private_url(str(resp.url)):
                    logger.warning("xfer probe redirected to private URL: %s", resp.url)
                    return None
                ctype = (resp.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
                if ctype in {"application/x-fossil", "application/x-fossil-debug"}:
                    logger.info("xfer probe confirmed %s as fossil repository", url)
                    return True
                if resp.status_code in (401, 403):
                    return None
                return False
    except httpx.RequestError as e:
        logger.warning("Fossil xfer probe failed for %s: %s", url, e)
        return None


async def _fossil_probe_footer(url: str, timeout: int) -> bool | None:
    """Probe URL via HTTP GET + fossil footer regex (fallback). Returns True/False/None."""
    if await _is_private_url(url):
        logger.warning("Refusing footer probe to private URL: %s", url)
        return None
    import re
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(url)
        if await _is_private_url(str(resp.url)):
            logger.warning("footer probe redirected to private URL: %s", resp.url)
            return None
        if resp.status_code != 200:
            return False
        if re.search(
            r"this page was generated in about\s+\d+(?:\.\d+)?s\s+by\s+fossil\b",
            resp.text,
            re.I,
        ):
            logger.info("footer probe confirmed %s as fossil repository", url)
            return True
        return False
    except httpx.RequestError as e:
        logger.warning("Fossil footer check failed for %s: %s", url, e)
        return None


async def _fossil_probe(url: str, timeout: int) -> bool | None:
    """Probe URL via Fossil sync protocol, falling back to HTML footer regex.

    Tries the authoritative /xfer protocol probe first. If it returns None
    (uncertain — auth required, proxy issue), falls back to the weaker
    HTML footer regex heuristic.
    """
    xfer_result = await _fossil_probe_xfer(url, timeout)
    if xfer_result is not None:
        return xfer_result
    return await _fossil_probe_footer(url, timeout)


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
        logger.debug("Trying %s probe for %s", _name, url)
        result = await run()
        if result is True:
            logger.debug("%s probe for %s succeeded", _name, url)
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
    except (httpx.RequestError, ConnectionError):
        return False


async def validate_url(
    url: str,
    timeout: int,
    github_token: str | None = None,
) -> UrlValidationOutput:
    hostname = urlsplit(url).hostname
    if not hostname:
        return UrlValidationOutput(UrlValidationResult.INVALID)

    if await _is_private_url(url):
        return UrlValidationOutput(UrlValidationResult.INVALID)

    final_url = url
    if url.startswith(("http://", "https://")):
        try:
            resp = await _head_request(url, timeout, github_token=github_token)
            if resp.status_code == 401 and github_token:
                return UrlValidationOutput(
                    UrlValidationResult.TOKEN_INVALID,
                    final_url=str(resp.url),
                )
            final_url = str(resp.url)
        except (httpx.RequestError, ConnectionError):
            pass  # graceful degradation — keep original url

    try:
        git_result = await _check_vcs(final_url, timeout, github_token=github_token)
    except Exception:
        logger.warning("VCS check failed unexpectedly for %s", final_url, exc_info=True)
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
) -> UrlValidationOutput:
    voutput = await validate_url(
        url, timeout,
        github_token=github_token,
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
        )

    return voutput
