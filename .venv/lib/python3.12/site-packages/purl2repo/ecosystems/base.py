"""Ecosystem adapter abstraction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from purl2repo.hosts.base import HostAdapter
from purl2repo.http.client import HttpClient
from purl2repo.models import ParsedPurl, ReleaseLink, RepositoryCandidate
from purl2repo.utils.urls import classify_host, normalize_repo_url, url_host

Metadata = dict[str, Any]


class EcosystemResolver(ABC):
    ecosystem: str
    metadata_source: str

    @abstractmethod
    def fetch_metadata(self, parsed: ParsedPurl, client: HttpClient) -> Metadata:
        """Fetch structured ecosystem metadata."""

    @abstractmethod
    def extract_candidates(
        self, parsed: ParsedPurl, metadata: Metadata
    ) -> list[RepositoryCandidate]:
        """Extract repository candidates from structured metadata."""

    def resolve_release_link(
        self,
        parsed: ParsedPurl,
        repository: RepositoryCandidate | None,
        metadata: Metadata,
        host_adapter: HostAdapter | None,
    ) -> ReleaseLink | None:
        _ = metadata
        if not parsed.version or repository is None or host_adapter is None:
            return None
        return host_adapter.infer_release_link(repository.normalized_url, parsed.version)

    def fallback_scrape_pages(self, parsed: ParsedPurl, metadata: Metadata) -> list[str]:
        _ = parsed, metadata
        return []

    def metadata_fetch_fallback(self, parsed: ParsedPurl) -> Metadata | None:
        """Return minimal metadata when structured fetch fails but inference is possible."""

        _ = parsed
        return None


def make_candidate(url: str | None, source: str, reason: str) -> RepositoryCandidate | None:
    if not url:
        return None
    normalized = normalize_repo_url(url)
    if not normalized:
        normalized = url.strip()
    host = url_host(normalized)
    return RepositoryCandidate(
        url=url.strip(),
        normalized_url=normalized,
        host=host,
        repository_type=classify_host(host),
        source=source,
        score=0.0,
        reasons=[reason],
    )


def dedupe_candidates(candidates: list[RepositoryCandidate | None]) -> list[RepositoryCandidate]:
    deduped: dict[tuple[str, str], RepositoryCandidate] = {}
    for candidate in candidates:
        if candidate is None:
            continue
        key = (candidate.normalized_url, candidate.source)
        if key not in deduped:
            deduped[key] = candidate
    return list(deduped.values())
