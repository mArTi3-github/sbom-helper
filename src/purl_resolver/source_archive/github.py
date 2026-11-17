from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import quote, urlsplit

import httpx

_ALLOWED_HOSTS = frozenset({"github.com", "www.github.com"})
_SEGMENT = re.compile(r"^[A-Za-z0-9_.-]+$")
_SHA = re.compile(r"^[0-9a-fA-F]{40}$")


@dataclass(frozen=True)
class GitHubRepo:
    owner: str
    name: str


def parse_github_repository(url: str) -> GitHubRepo | None:
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    if parts.scheme.lower() not in ("http", "https"):
        return None
    if parts.hostname is None or parts.hostname.lower() not in _ALLOWED_HOSTS:
        return None
    path = parts.path
    if path.endswith("/"):
        path = path[:-1]
    if path.endswith(".git"):
        path = path[: -len(".git")]
    segments = path.split("/")
    if len(segments) != 3 or segments[0] != "":
        return None
    owner, name = segments[1], segments[2]
    if owner in (".", "..") or name in (".", ".."):
        return None
    if not _SEGMENT.match(owner) or not _SEGMENT.match(name):
        return None
    return GitHubRepo(owner, name)


def tag_archive_url(repo: GitHubRepo, tag: str) -> str:
    encoded = quote(tag, safe="/")
    return f"https://github.com/{repo.owner}/{repo.name}/archive/refs/tags/{encoded}.tar.gz"


def commit_archive_url(repo: GitHubRepo, sha: str) -> str:
    if not _SHA.match(sha):
        raise ValueError(f"Invalid commit SHA: {sha!r}")
    return f"https://github.com/{repo.owner}/{repo.name}/archive/{sha}.tar.gz"


async def check_archive_url(
    url: str,
    timeout: float,
    client: httpx.AsyncClient | None = None,
) -> bool:
    if client is not None:
        return await _head_ok(client, url, timeout)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as own_client:
        return await _head_ok(own_client, url, timeout)


async def _head_ok(client: httpx.AsyncClient, url: str, timeout: float) -> bool:
    try:
        response = await client.head(url, timeout=timeout, follow_redirects=True)
    except httpx.HTTPError:
        return False
    return response.status_code < 400
