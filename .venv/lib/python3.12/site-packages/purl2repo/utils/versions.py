"""Version string helpers for conservative release inference."""

import re

_COMMIT_LIKE_RE = re.compile(r"^[0-9a-fA-F]{7,64}$")


def version_variants(version: str) -> list[str]:
    """Return exact and v-prefixed tag candidates without assuming SemVer."""

    stripped = version.strip()
    if not stripped:
        return []
    if stripped.startswith("v"):
        return [stripped, stripped[1:]]
    return [stripped, f"v{stripped}"]


def preferred_v_tag(version: str) -> str:
    """Return the common v-prefixed tag form for release-page heuristics."""

    return version if version.startswith("v") else f"v{version}"


def is_commit_like(version: str) -> bool:
    """Return True when a version resembles a git commit hash."""

    return bool(_COMMIT_LIKE_RE.fullmatch(version.strip()))
