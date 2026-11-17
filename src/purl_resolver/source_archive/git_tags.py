from __future__ import annotations

import asyncio
import os
from urllib.parse import urlsplit

from ..url_validator import _terminate_process, _track_process, _untrack_process
from .matching import TagInfo

MAX_OUTPUT_BYTES = 5 * 1024 * 1024
MAX_TAGS = 50_000

_READ_CHUNK = 65536
_TAG_PREFIX = "refs/tags/"
_PEELED_SUFFIX = "^{}"


class GitTagsError(Exception):
    pass


class _OutputTooLarge(Exception):
    pass


def parse_ls_remote(output: str) -> list[TagInfo]:
    tags: dict[str, TagInfo] = {}
    for line in output.splitlines():
        sha, separator, ref = line.partition("\t")
        sha = sha.strip()
        if not separator or not sha or any(char.isspace() for char in sha):
            continue
        if not ref.startswith(_TAG_PREFIX):
            continue
        name = ref[len(_TAG_PREFIX) :]
        peeled = name.endswith(_PEELED_SUFFIX)
        if peeled:
            name = name[: -len(_PEELED_SUFFIX)]
        if not name:
            continue
        if peeled:
            tags[name] = TagInfo(name=name, commit_sha=sha)
        elif name not in tags:
            tags[name] = TagInfo(name=name, commit_sha=sha)
    return list(tags.values())


async def fetch_tags(repository_url: str, timeout: float) -> list[TagInfo]:
    if not _is_supported_url(repository_url):
        raise GitTagsError(f"Unsupported repository URL: {repository_url}")
    env = {
        **os.environ,
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_ASKPASS": "/bin/true",
    }
    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            "ls-remote",
            "--tags",
            repository_url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
            env=env,
        )
    except OSError as exc:
        raise GitTagsError(f"Failed to start git: {exc}") from exc
    _track_process(proc.pid)
    try:
        try:
            stdout, stderr = await asyncio.wait_for(
                _communicate_bounded(proc),
                timeout=timeout,
            )
        except asyncio.TimeoutError as exc:
            raise GitTagsError(f"git ls-remote timed out after {timeout}s") from exc
        except _OutputTooLarge as exc:
            raise GitTagsError("git ls-remote output exceeded 5 MB") from exc
        except OSError as exc:
            raise GitTagsError(f"git ls-remote failed: {exc}") from exc
        if proc.returncode != 0:
            detail = stderr.decode(errors="replace").strip()[:500]
            raise GitTagsError(
                f"git ls-remote exited with {proc.returncode}"
                + (f": {detail}" if detail else "")
            )
        tags = parse_ls_remote(stdout.decode(errors="replace"))
        if len(tags) > MAX_TAGS:
            raise GitTagsError(f"git ls-remote returned more than {MAX_TAGS} tags")
        return tags
    finally:
        try:
            if proc.returncode is None:
                await _terminate_process(proc)
        finally:
            _untrack_process(proc.pid)


def _is_supported_url(repository_url: str) -> bool:
    parts = urlsplit(repository_url)
    return parts.scheme.lower() in ("http", "https") and bool(parts.hostname)


async def _communicate_bounded(
    proc: asyncio.subprocess.Process,
) -> tuple[bytes, bytes]:
    stdout_task = asyncio.ensure_future(_read_bounded(proc.stdout))
    stderr_task = asyncio.ensure_future(_read_bounded(proc.stderr))
    try:
        stdout, stderr = await asyncio.gather(stdout_task, stderr_task)
    finally:
        for task in (stdout_task, stderr_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
    await proc.wait()
    return stdout, stderr


async def _read_bounded(stream: asyncio.StreamReader | None) -> bytes:
    if stream is None:
        return b""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await stream.read(_READ_CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_OUTPUT_BYTES:
            raise _OutputTooLarge
        chunks.append(chunk)
    return b"".join(chunks)
