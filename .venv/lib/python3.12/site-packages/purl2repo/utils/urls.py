"""URL normalization helpers."""

from __future__ import annotations

import re
from urllib.parse import quote, unquote, urlsplit, urlunsplit

KNOWN_HOSTS = {"github.com", "gitlab.com", "bitbucket.org"}
REPO_SUFFIXES = {"issues", "issue", "pulls", "pull", "releases", "release", "tags", "tag", "wiki"}
GITHUB_STOP_SEGMENTS = REPO_SUFFIXES | {"tree", "blob", "archive", "commits", "commit"}
BITBUCKET_STOP_SEGMENTS = REPO_SUFFIXES | {"src", "branch", "commits", "downloads"}

_SCP_RE = re.compile(r"^(?:git@|ssh://git@)(?P<host>[^:/]+)[:/](?P<path>.+)$")


def strip_vcs_prefix(url: str) -> str:
    value = url.strip()
    for prefix in ("scm:git:", "scm:hg:", "scm:svn:", "git+"):
        if value.startswith(prefix):
            value = value[len(prefix) :]
    return value.strip()


def coerce_git_url(url: str) -> str:
    value = strip_vcs_prefix(url)
    match = _SCP_RE.match(value)
    if match:
        return f"https://{match.group('host')}/{match.group('path')}"
    if value.startswith("git://"):
        return f"https://{value[len('git://') :]}"
    return value


def _clean_segments(path: str) -> list[str]:
    return [unquote(segment) for segment in path.split("/") if segment]


def _encode_segments(segments: list[str]) -> str:
    return "/" + "/".join(quote(segment, safe=":@._~+-") for segment in segments)


def _strip_git_suffix(segment: str) -> str:
    return segment[:-4] if segment.endswith(".git") else segment


def classify_host(host: str) -> str:
    normalized = host.lower()
    if normalized == "github.com":
        return "github"
    if normalized == "gitlab.com":
        return "gitlab"
    if normalized == "bitbucket.org":
        return "bitbucket"
    return "generic_git"


def normalize_repo_url(url: str) -> str | None:
    """Normalize repository-like URLs to a stable web URL when safe."""

    value = coerce_git_url(url)
    parsed = urlsplit(value)
    if not parsed.scheme and parsed.path and "." in parsed.path.split("/", 1)[0]:
        parsed = urlsplit(f"https://{value}")
    if parsed.scheme not in {"http", "https", "ssh"}:
        return None
    if not parsed.netloc:
        return None

    host = parsed.hostname.lower() if parsed.hostname else ""
    if not host:
        return None

    segments = _clean_segments(parsed.path)
    if segments:
        segments[-1] = _strip_git_suffix(segments[-1])
    if not segments:
        return f"https://{host}"

    if host == "github.com":
        segments = segments[:2] if len(segments) >= 2 else segments[:1]
    elif host == "gitlab.com":
        if "-" in segments:
            segments = segments[: segments.index("-")]
        if segments and segments[-1] in GITHUB_STOP_SEGMENTS:
            segments = segments[:-1]
    elif host == "bitbucket.org":
        if len(segments) >= 2:
            segments = segments[:2]
        if segments and segments[-1] in BITBUCKET_STOP_SEGMENTS:
            segments = segments[:-1]
    else:
        while segments and segments[-1] in REPO_SUFFIXES:
            segments = segments[:-1]

    normalized_path = _encode_segments(segments).rstrip("/")
    return urlunsplit(("https", host, normalized_path, "", "")).rstrip("/")


def url_host(url: str) -> str:
    parsed = urlsplit(coerce_git_url(url))
    return parsed.hostname.lower() if parsed.hostname else ""


def is_repo_like_url(url: str) -> bool:
    normalized = normalize_repo_url(url)
    if not normalized:
        return False
    split = urlsplit(normalized)
    segments = _clean_segments(split.path)
    if split.hostname in {"github.com", "bitbucket.org"}:
        return len(segments) >= 2
    if split.hostname == "gitlab.com":
        return len(segments) >= 2
    return len(segments) >= 1 and (url.endswith(".git") or split.hostname not in {"", None})
