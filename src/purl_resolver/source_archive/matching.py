from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, Sequence

PRERELEASE_MARKERS = ("rc", "alpha", "beta", "pre", "dev", "snapshot", "nightly")
SEPARATOR_CHARS = frozenset(".-_/+")
_DIGIT_RUN = re.compile(r"\d+")


@dataclass(frozen=True)
class TagInfo:
    name: str
    commit_sha: str | None = None


@dataclass(frozen=True)
class VersionParts:
    numbers: tuple[int, ...]
    suffix: str


@dataclass(frozen=True)
class TagMatch:
    tag: TagInfo
    match_type: Literal["exact", "near"]
    matched_version: str


def parse_version(text: str) -> VersionParts | None:
    return _extract_version(text.strip())


def find_exact(tags: Sequence[TagInfo], version: VersionParts) -> list[TagMatch]:
    candidates: list[tuple[TagInfo, VersionParts]] = []
    for tag in tags:
        parts = _extract_version(tag.name)
        if parts is None:
            continue
        if not _numbers_equal(parts.numbers, version.numbers):
            continue
        if version.suffix and parts.suffix != version.suffix:
            continue
        candidates.append((tag, parts))
    candidates.sort(key=lambda item: _exact_key(*item))
    return [
        TagMatch(tag=tag, match_type="exact", matched_version=_format_numbers(parts.numbers))
        for tag, parts in candidates
    ]


def find_near(tags: Sequence[TagInfo], version: VersionParts) -> TagMatch | None:
    target_major_minor = _pad(version.numbers, 2)[:2]
    target_is_prerelease = _is_prerelease(version.suffix)
    candidates: list[tuple[TagInfo, VersionParts]] = []
    for tag in tags:
        parts = _extract_version(tag.name)
        if parts is None:
            continue
        if _pad(parts.numbers, 2)[:2] != target_major_minor:
            continue
        if _is_prerelease(parts.suffix) and not target_is_prerelease:
            continue
        if _is_exact(parts, version):
            continue
        candidates.append((tag, parts))
    if not candidates:
        return None
    tag, parts = min(candidates, key=lambda item: _near_key(version, *item))
    return TagMatch(tag=tag, match_type="near", matched_version=_format_numbers(parts.numbers))


def pick_nearer(version: VersionParts, first: TagMatch, second: TagMatch) -> TagMatch:
    return min((first, second), key=lambda match: _match_key(version, match))


def _extract_version(text: str) -> VersionParts | None:
    runs = list(_DIGIT_RUN.finditer(text))
    if not runs:
        return None
    chains: list[list[re.Match[str]]] = [[runs[0]]]
    for previous, current in zip(runs, runs[1:]):
        separator = text[previous.end() : current.start()]
        if separator and all(char in SEPARATOR_CHARS for char in separator):
            chains[-1].append(current)
        else:
            chains.append([current])
    chain = max(chains, key=len)
    numbers = tuple(int(run.group()) for run in chain)
    suffix = _normalize_suffix(text[chain[-1].end() :])
    return VersionParts(numbers=numbers, suffix=suffix)


def _normalize_suffix(text: str) -> str:
    return "".join(char for char in text if char.isalnum()).lower()


def _is_prerelease(suffix: str) -> bool:
    return suffix.startswith(PRERELEASE_MARKERS)


def _pad(numbers: tuple[int, ...], length: int) -> tuple[int, ...]:
    return numbers + (0,) * max(length - len(numbers), 0)


def _numbers_equal(first: tuple[int, ...], second: tuple[int, ...]) -> bool:
    length = max(len(first), len(second))
    return _pad(first, length) == _pad(second, length)


def _is_exact(parts: VersionParts, version: VersionParts) -> bool:
    if not _numbers_equal(parts.numbers, version.numbers):
        return False
    return not version.suffix or parts.suffix == version.suffix


def _format_numbers(numbers: tuple[int, ...]) -> str:
    return ".".join(str(number) for number in numbers)


def _exact_key(tag: TagInfo, parts: VersionParts) -> tuple[bool, int, str]:
    return (_is_prerelease(parts.suffix), len(tag.name), tag.name)


def _near_key(
    version: VersionParts,
    tag: TagInfo,
    parts: VersionParts,
) -> tuple[int, tuple[int, ...], int, str]:
    length = max(len(version.numbers), len(parts.numbers))
    target = _pad(version.numbers, length)
    candidate = _pad(parts.numbers, length)
    if candidate == target:
        return (0, (), len(tag.name), tag.name)
    if candidate < target:
        return (1, tuple(-number for number in candidate), len(tag.name), tag.name)
    return (2, candidate, len(tag.name), tag.name)


def _match_key(version: VersionParts, match: TagMatch) -> tuple[int, tuple[int, ...], int, str]:
    parts = _extract_version(match.tag.name)
    if parts is None:
        return (3, (), len(match.tag.name), match.tag.name)
    return _near_key(version, match.tag, parts)
