from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal, cast
from urllib.parse import quote

from ..purl_utils import PurlValidationError, normalize_with_version, validate
from ..settings_store import SettingsStore
from ..storage.source_archive import SourceArchiveRow, SourceArchiveStorage
from .git_tags import fetch_tags
from .github import GitHubRepo, check_archive_url, parse_github_repository, tag_archive_url
from .matching import TagInfo, TagMatch, find_exact, find_near, parse_version

logger = logging.getLogger(__name__)

MatchType = Literal["exact", "near", "repository_only", "not_found", "no_version"]

TagFetcher = Callable[[str, float], Awaitable[list[TagInfo]]]
UrlChecker = Callable[[str, float], Awaitable[bool]]


@dataclass(frozen=True)
class SourceArchiveResult:
    purl: str
    match_type: MatchType
    reason: str | None = None
    archive_url: str | None = None
    archive_url_commit: str | None = None
    matched_ref: str | None = None
    matched_ref_type: str | None = None
    matched_version: str | None = None
    repository_url: str | None = None
    resolver: str = ""
    cached: bool = False
    resolved_at: str = ""
    warnings: list[str] = field(default_factory=list)


class SourceArchiveService:
    def __init__(
        self,
        storage: SourceArchiveStorage,
        settings_store: SettingsStore,
        tag_fetcher: TagFetcher = fetch_tags,
        url_checker: UrlChecker = check_archive_url,
    ) -> None:
        self._storage = storage
        self._settings_store = settings_store
        self._tag_fetcher = tag_fetcher
        self._url_checker = url_checker

    async def lookup(
        self,
        purl: str,
        repository_url: str | None,
        force_refresh: bool = False,
    ) -> SourceArchiveResult:
        components = validate(purl)
        key = normalize_with_version(components)
        repository_url = repository_url or None

        if not components.version:
            return SourceArchiveResult(
                purl=key,
                match_type="no_version",
                reason="no_version",
                repository_url=repository_url,
            )

        version = parse_version(components.version)
        if version is None:
            return SourceArchiveResult(
                purl=key,
                match_type="repository_only" if repository_url else "not_found",
                reason="non_numeric_version",
                repository_url=repository_url,
            )

        if not force_refresh:
            cached = await self._load_cached(key)
            if cached is not None and not _is_stale(cached, repository_url):
                return _result_from_row(cached, cached=True)

        timeout = self._settings_store.load().source_archive_timeout

        if repository_url is None:
            return await self._store_outcome(
                key, components.version, "not_found", "no_repository", repository_url
            )

        repo = parse_github_repository(repository_url)
        if repo is None:
            return await self._store_outcome(
                key, components.version, "repository_only", "unsupported_host", repository_url
            )

        try:
            tags = await self._tag_fetcher(repository_url, timeout)
        except Exception:
            logger.warning("Failed to fetch tags for %s", repository_url, exc_info=True)
            return await self._store_outcome(
                key, components.version, "repository_only", "git_error", repository_url
            )

        exact = find_exact(tags, version)
        if exact:
            warnings: list[str] = []
            if len(exact) > 1:
                warnings.append(
                    f"Multiple exact tags matched; chose '{exact[0].tag.name}'"
                )
            row = _match_row(key, components.version, exact[0], repo, repository_url)
            if await self._check(row.archive_url, timeout):
                return await self._store_row(row, warnings)
            return await self._store_outcome(
                key, components.version, "repository_only", "archive_check_failed", repository_url
            )

        near = find_near(tags, version)
        if near is not None:
            row = _match_row(key, components.version, near, repo, repository_url)
            if await self._check(row.archive_url, timeout):
                return await self._store_row(row)
            return await self._store_outcome(
                key, components.version, "repository_only", "archive_check_failed", repository_url
            )

        return await self._store_outcome(
            key, components.version, "repository_only", "no_matching_tag", repository_url
        )

    async def enrich_many(
        self,
        purls: list[str],
        repository_urls: list[str | None],
        force_refresh: bool = False,
    ) -> list[SourceArchiveResult]:
        if len(purls) != len(repository_urls):
            raise ValueError("purls and repository_urls must have the same length")

        index_by_key: dict[tuple[str, str | None], int] = {}
        representatives: list[tuple[str, str | None]] = []
        per_input: list[int] = []
        for purl, repository_url in zip(purls, repository_urls):
            normalized_repository = repository_url or None
            key = (_cache_key(purl), normalized_repository)
            if key not in index_by_key:
                index_by_key[key] = len(representatives)
                representatives.append((purl, normalized_repository))
            per_input.append(index_by_key[key])

        semaphore = asyncio.Semaphore(
            self._settings_store.load().source_archive_concurrency
        )

        async def _lookup_one(
            purl: str, repository_url: str | None
        ) -> SourceArchiveResult:
            async with semaphore:
                return await self.lookup(purl, repository_url, force_refresh=force_refresh)

        unique_results = await asyncio.gather(
            *[_lookup_one(purl, url) for purl, url in representatives]
        )
        return [unique_results[index] for index in per_input]

    async def _load_cached(self, key: str) -> SourceArchiveRow | None:
        try:
            return await self._storage.lookup_archive(key)
        except Exception:
            logger.warning(
                "Failed to look up cached source archive for %s", key, exc_info=True
            )
            return None

    async def _store_row(
        self,
        row: SourceArchiveRow,
        warnings: list[str] | None = None,
    ) -> SourceArchiveResult:
        try:
            await self._storage.store_archive(row)
        except Exception:
            logger.warning(
                "Failed to store source archive for %s", row.purl, exc_info=True
            )
        return _result_from_row(row, cached=False, warnings=warnings)

    async def _store_outcome(
        self,
        key: str,
        version: str,
        match_type: Literal["repository_only", "not_found"],
        reason: str,
        repository_url: str | None,
    ) -> SourceArchiveResult:
        row = SourceArchiveRow(
            purl=key,
            version=version,
            match_type=match_type,
            reason=reason,
            repository_url=repository_url,
            resolver="git-tags",
            resolved_at=_now(),
        )
        return await self._store_row(row)

    async def _check(self, url: str | None, timeout: float) -> bool:
        if url is None:
            return False
        try:
            return await self._url_checker(url, timeout)
        except Exception:
            logger.warning("Failed to check archive URL %s", url, exc_info=True)
            return False


def _match_row(
    key: str,
    version: str,
    match: TagMatch,
    repo: GitHubRepo,
    repository_url: str,
) -> SourceArchiveRow:
    tag = match.tag
    return SourceArchiveRow(
        purl=key,
        version=version,
        match_type=match.match_type,
        archive_url=tag_archive_url(repo, tag.name),
        archive_url_commit=_commit_archive_url(repo, tag.commit_sha) if tag.commit_sha else None,
        matched_ref=tag.name,
        matched_ref_type="tag",
        matched_version=match.matched_version,
        repository_url=repository_url,
        resolver="git-tags",
        resolved_at=_now(),
    )


def _commit_archive_url(repo: GitHubRepo, sha: str) -> str:
    return f"https://github.com/{repo.owner}/{repo.name}/archive/{quote(sha, safe='')}.tar.gz"


def _cache_key(purl: str) -> str:
    try:
        return normalize_with_version(validate(purl))
    except (PurlValidationError, ValueError):
        return purl


def _is_stale(row: SourceArchiveRow, repository_url: str | None) -> bool:
    return repository_url is not None and row.repository_url != repository_url


def _result_from_row(
    row: SourceArchiveRow,
    cached: bool,
    warnings: list[str] | None = None,
) -> SourceArchiveResult:
    return SourceArchiveResult(
        purl=row.purl,
        match_type=cast(MatchType, row.match_type),
        reason=row.reason,
        archive_url=row.archive_url,
        archive_url_commit=row.archive_url_commit,
        matched_ref=row.matched_ref,
        matched_ref_type=row.matched_ref_type,
        matched_version=row.matched_version,
        repository_url=row.repository_url,
        resolver=row.resolver,
        cached=cached,
        resolved_at=row.resolved_at,
        warnings=list(warnings or []),
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
