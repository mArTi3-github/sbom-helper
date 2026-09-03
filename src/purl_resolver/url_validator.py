from __future__ import annotations

import asyncio
import ipaddress
import logging
import os
import signal
import socket
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlsplit

import httpx

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


@dataclass
class UrlValidationOutput:
    result: UrlValidationResult
    final_url: str | None = None


async def ensure_connectivity(
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
        async with httpx.AsyncClient(timeout=probe_timeout) as client:
            resp = await client.head(probe_url)
            ok = resp.status_code < 500
    except httpx.RequestError:
        logger.warning("Connectivity probe to %s failed", probe_url)
        ok = False
    if not ok:
        raise ConnectionError(f"Cannot reach {probe_url}")
    return True


async def _head_request(url: str, timeout: int):
    if await _is_private_url(url):
        raise ConnectionError(f"Refusing HEAD request to private URL: {url}")
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        resp = await client.head(url)
    if await _is_private_url(str(resp.url)):
        raise ConnectionError(f"HEAD redirect target is private: {resp.url}")
    return resp


def _process_descendants(root_pid: int) -> list[int]:
    """Return all descendant PIDs of *root_pid* (children, grandchildren, ...).

    Reads /proc/<pid>/task/<pid>/children; returns [] when unavailable.
    """
    found: list[int] = []
    stack = [root_pid]
    while stack:
        current = stack.pop()
        try:
            with open(f"/proc/{current}/task/{current}/children") as f:
                raw = f.read().split()
        except OSError:
            continue
        for token in raw:
            try:
                child = int(token)
            except ValueError:
                continue
            if child not in found and child != root_pid:
                found.append(child)
                stack.append(child)
    return found


_TRACKED_PIDS: set[int] = set()


def _track_process(pid: int | None) -> None:
    """Remember a direct child spawned via asyncio so the orphan reaper
    never reaps it behind the asyncio child watcher's back."""
    if isinstance(pid, int) and pid > 1:
        _TRACKED_PIDS.add(pid)


def _untrack_process(pid: int | None) -> None:
    """Forget a child once asyncio has reaped it (wait() completed)."""
    if isinstance(pid, int):
        _TRACKED_PIDS.discard(pid)


def enable_child_subreaper() -> None:
    """Make this process adopt orphaned descendants (Linux).

    VCS clients spawn their own children (git ls-remote starts
    git-remote-https helpers) and occasionally exit without reaping them.
    Those orphans are reparented to the nearest subreaper — or to PID 1 of
    the container, which never reaps them, leaving permanent zombies. As a
    subreaper this process receives them instead, and
    reap_orphaned_processes() can collect them. Harmless when this process
    already is PID 1.
    """
    if os.name != "posix" or not sys.platform.startswith("linux"):
        return
    try:
        import ctypes

        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        libc.prctl(36, 1, 0, 0, 0)  # PR_SET_CHILD_SUBREAPER
    except Exception:
        logger.warning("Failed to enable child subreaper", exc_info=True)


def reap_orphaned_processes() -> None:
    """Reap zombie children of this process that asyncio does not track.

    These are VCS helper processes (e.g. git-remote-https) that were
    orphaned by their parent and adopted by this process via the subreaper
    attribute (or PID 1). Zombies still tracked by asyncio are skipped so
    the child watcher reaps them normally.
    """
    me = os.getpid()
    try:
        entries = os.listdir("/proc")
    except OSError:
        return
    for entry in entries:
        if not entry.isdigit():
            continue
        pid = int(entry)
        if pid in _TRACKED_PIDS:
            continue
        try:
            with open(f"/proc/{entry}/stat", "rb") as f:
                data = f.read().decode(errors="replace")
            rest = data[data.rfind(")") + 1:].split()
            if rest[0] != "Z" or int(rest[1]) != me:
                continue
        except (OSError, ValueError, IndexError):
            continue
        try:
            os.waitpid(pid, os.WNOHANG)
        except (ChildProcessError, OSError):
            pass


async def _terminate_process(proc: asyncio.subprocess.Process) -> None:
    """SIGKILL the probe's process group and reap the whole process tree.

    VCS clients (git, svn, hg) spawn their own children — git starts
    git-remote-https helpers for HTTP URLs. Killing only the group leaves
    those grandchildren orphaned; inside the container they are reparented
    to this app (PID 1), where asyncio's child watcher never sees them, so
    they would remain zombies forever and eventually exhaust the PID/thread
    limit. Descendants are therefore collected up front and reaped here.
    """
    pid = proc.pid
    descendants: list[int] = []
    if isinstance(pid, int) and pid > 1 and proc.returncode is None:
        descendants = _process_descendants(pid)
        try:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        except ProcessLookupError:
            pass

    wait_task = asyncio.ensure_future(proc.wait())
    cancelled = False
    while not wait_task.done():
        try:
            await asyncio.shield(wait_task)
        except asyncio.CancelledError:
            cancelled = True

    for child_pid in descendants:
        for _ in range(5):
            try:
                reaped, _ = os.waitpid(child_pid, os.WNOHANG)
            except ChildProcessError:
                # Not our child yet: reparenting lags behind the deaths of
                # the intermediate ancestors. Retry briefly.
                try:
                    await asyncio.sleep(0.02)
                except asyncio.CancelledError:
                    cancelled = True
                    break
                continue
            if reaped == child_pid:
                break
            try:
                os.kill(child_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                await asyncio.sleep(0.02)
            except asyncio.CancelledError:
                cancelled = True
                break
    if cancelled:
        raise asyncio.CancelledError


async def _git_probe(url: str, timeout: int) -> bool | None:
    """Probe URL via git ls-remote. Returns True/False/None."""
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "ls-remote", "--exit-code", url, "HEAD",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
            env=env,
        )
    except (OSError, asyncio.TimeoutError) as e:
        logger.warning("git ls-remote failed to start for %s: %s", url, e)
        return None
    _track_process(proc.pid)
    try:
        try:
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            await _terminate_process(proc)
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
    except asyncio.CancelledError:
        await _terminate_process(proc)
        raise
    except OSError as e:
        await _terminate_process(proc)
        logger.warning("git ls-remote failed for %s: %s", url, e)
        return None
    finally:
        _untrack_process(proc.pid)


async def _svn_probe(url: str, timeout: int) -> bool | None:
    """Probe URL via svn ls. Returns True/False/None."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "svn", "ls", url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
    except (OSError, asyncio.TimeoutError) as e:
        logger.warning("svn ls failed to start for %s: %s", url, e)
        return None
    _track_process(proc.pid)
    try:
        try:
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            await _terminate_process(proc)
            logger.warning("svn ls timed out for %s", url)
            return None
        if proc.returncode == 0:
            logger.info("svn probe confirmed %s as svn repository", url)
            return True
        return False
    except asyncio.CancelledError:
        await _terminate_process(proc)
        raise
    except OSError as e:
        await _terminate_process(proc)
        logger.warning("svn ls failed for %s: %s", url, e)
        return None
    finally:
        _untrack_process(proc.pid)


async def _hg_probe(url: str, timeout: int) -> bool | None:
    """Probe URL via hg identify. Returns True/False/None."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "hg", "identify", url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
    except (OSError, asyncio.TimeoutError) as e:
        logger.warning("hg identify failed to start for %s: %s", url, e)
        return None
    _track_process(proc.pid)
    try:
        try:
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            await _terminate_process(proc)
            logger.warning("hg identify timed out for %s", url)
            return None
        if proc.returncode == 0:
            logger.info("hg probe confirmed %s as hg repository", url)
            return True
        return False
    except asyncio.CancelledError:
        await _terminate_process(proc)
        raise
    except OSError as e:
        await _terminate_process(proc)
        logger.warning("hg identify failed for %s: %s", url, e)
        return None
    finally:
        _untrack_process(proc.pid)


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
        ("git", lambda: _git_probe(url, timeout)),
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


async def validate_url(
    url: str,
    timeout: int,
) -> UrlValidationOutput:
    hostname = urlsplit(url).hostname
    if not hostname:
        return UrlValidationOutput(UrlValidationResult.INVALID)

    if await _is_private_url(url):
        return UrlValidationOutput(UrlValidationResult.INVALID)

    final_url = url
    if url.startswith(("http://", "https://")):
        try:
            resp = await _head_request(url, timeout)
            final_url = str(resp.url)
        except (httpx.RequestError, ConnectionError):
            pass  # graceful degradation — keep original url

    try:
        git_result = await _check_vcs(final_url, timeout)
    except Exception:
        logger.warning("VCS check failed unexpectedly for %s", final_url, exc_info=True)
        return UrlValidationOutput(UrlValidationResult.NETWORK_ERROR, final_url=final_url)
    if git_result is None:
        return UrlValidationOutput(UrlValidationResult.NETWORK_ERROR, final_url=final_url)
    if git_result is False:
        return UrlValidationOutput(UrlValidationResult.INVALID, final_url=final_url)

    return UrlValidationOutput(UrlValidationResult.VALID, final_url=final_url)

