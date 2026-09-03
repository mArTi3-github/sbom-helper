from __future__ import annotations

import asyncio
import ctypes
import os
import shutil
import socket
import sys
import threading
from typing import NamedTuple

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "linux" or shutil.which("git") is None,
    reason="requires Linux with the git binary",
)


class ChildInfo(NamedTuple):
    pid: int
    state: str
    comm: str


def _my_children() -> list[ChildInfo]:
    """List direct children of the current process (pid, state, comm)."""
    me = os.getpid()
    rows: list[ChildInfo] = []
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/stat", "rb") as f:
                data = f.read().decode(errors="replace")
            rest = data[data.rfind(")") + 1:].split()
            ppid = int(rest[1])
            if ppid != me:
                continue
            with open(f"/proc/{entry}/comm") as cf:
                comm = cf.read().strip()
            rows.append(ChildInfo(int(entry), rest[0], comm))
        except (OSError, ValueError, IndexError):
            continue
    return rows


def _is_vcs_child(child: ChildInfo) -> bool:
    return child.comm == "git" or child.comm.startswith(("git-", "ssh", "svn", "hg"))


def _make_subreaper() -> None:
    """Make this process a child subreaper so orphaned grandchildren are
    reparented here — exactly like PID 1 inside the app container."""
    libc = ctypes.CDLL("libc.so.6", use_errno=True)
    libc.prctl(36, 1, 0, 0, 0)  # PR_SET_CHILD_SUBREAPER


class SilentGitServer:
    """TCP server that accepts connections and never responds.

    git ls-remote against it hangs until the probe timeout fires.
    """

    def __init__(self) -> None:
        self._srv = socket.socket()
        self._srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._srv.bind(("127.0.0.1", 0))
        self._srv.listen(64)
        self.port = self._srv.getsockname()[1]
        self._held: list[socket.socket] = []
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        while True:
            try:
                conn, _ = self._srv.accept()
            except OSError:
                return
            self._held.append(conn)
            threading.Thread(target=self._hold, args=(conn,), daemon=True).start()

    @staticmethod
    def _hold(conn: socket.socket) -> None:
        try:
            while True:
                if not conn.recv(65536):
                    return
        except OSError:
            pass

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/repo.git"

    def close(self) -> None:
        self._srv.close()


@pytest.fixture(scope="module", autouse=True)
def _subreaper_fixture():
    _make_subreaper()
    yield
    libc = ctypes.CDLL("libc.so.6", use_errno=True)
    libc.prctl(36, 0, 0, 0, 0)


@pytest.fixture
def silent_server():
    server = SilentGitServer()
    yield server
    server.close()


def _git_probe_of():
    from purl_resolver.url_validator import _git_probe

    return _git_probe


class TestGitProbeProcessCleanup:
    @pytest.mark.asyncio
    async def test_timeout_reaps_all_orphaned_processes(self, silent_server):
        """A timed-out git probe must not leave zombie git/git-remote-http
        children behind (previously orphaned grandchildren were reparented
        to PID 1 and never reaped)."""
        git_probe = _git_probe_of()

        result = await git_probe(silent_server.url, timeout=1)

        assert result is None
        await asyncio.sleep(0.5)
        stray = [c for c in _my_children() if _is_vcs_child(c)]
        assert stray == [], f"leaked processes after timeout: {stray}"

    @pytest.mark.asyncio
    async def test_cancellation_kills_process_and_leaves_no_children(
        self, silent_server,
    ):
        """Cancelling a running probe must kill the spawned git process tree
        instead of leaving it running forever."""
        git_probe = _git_probe_of()

        task = asyncio.create_task(git_probe(silent_server.url, timeout=30))
        await asyncio.sleep(0.8)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        await asyncio.sleep(0.5)
        stray = [c for c in _my_children() if _is_vcs_child(c)]
        assert stray == [], f"leaked processes after cancel: {stray}"


class TestFastFailureZombies:
    """git ls-remote exits fast (rc=128) for non-repository URLs but does not
    always reap its own helper child (git -> git-remote-https). That orphan
    is reparented to this process (subreaper) and must be collected by
    reap_orphaned_processes()."""

    @pytest.mark.asyncio
    async def test_fast_failure_leaves_no_zombies_after_reap(self):
        from purl_resolver.url_validator import _git_probe, reap_orphaned_processes

        url = "http://127.0.0.1:9/repo.git"
        for _ in range(3):
            result = await _git_probe(url, timeout=5)
            assert result is None

        await asyncio.sleep(0.5)
        reap_orphaned_processes()
        await asyncio.sleep(0.5)
        stray = [c for c in _my_children() if _is_vcs_child(c)]
        assert stray == [], f"leaked zombie processes: {stray}"
