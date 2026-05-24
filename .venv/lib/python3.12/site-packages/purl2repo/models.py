"""Typed public data contracts for purl2repo."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

JsonDict = dict[str, Any]


@dataclass(frozen=True)
class ParsedPurl:
    raw: str
    type: str
    namespace: str | None
    name: str
    version: str | None
    qualifiers: dict[str, str]
    subpath: str | None

    def to_dict(self) -> JsonDict:
        return asdict(self)


@dataclass(frozen=True)
class RepositoryCandidate:
    url: str
    normalized_url: str
    host: str
    repository_type: str
    source: str
    score: float
    reasons: list[str]

    def to_dict(self) -> JsonDict:
        return asdict(self)


@dataclass(frozen=True)
class ScrapedCandidate:
    url: str
    normalized_url: str | None
    source_page: str
    extraction_method: str
    label_context: str | None
    score_cap: float
    reasons: list[str]

    def to_dict(self) -> JsonDict:
        return asdict(self)


@dataclass(frozen=True)
class RepositoryRef:
    url: str
    kind: str
    platform: str | None
    host: str | None
    namespace: str | None
    name: str | None
    is_canonical: bool
    confidence: str
    reasons: list[str]

    def to_dict(self) -> JsonDict:
        return asdict(self)


@dataclass(frozen=True)
class ReleaseLink:
    url: str
    kind: str
    version: str | None
    source: str

    def to_dict(self) -> JsonDict:
        return asdict(self)


@dataclass(frozen=True)
class ResolutionResult:
    purl: ParsedPurl
    repository_url: str | None
    repository_type: str | None
    repository_kind: str | None
    repository_candidates: list[RepositoryCandidate]
    canonical_repository: RepositoryRef | None
    release_link: ReleaseLink | None
    version_reference: ReleaseLink | None
    confidence: str
    evidence: list[str]
    warnings: list[str]
    metadata_sources: list[str]
    repository_validated: bool = False
    repository_validation_status: str = "unknown"

    def to_dict(self) -> JsonDict:
        return {
            "purl": self.purl.to_dict(),
            "repository_url": self.repository_url,
            "repository_type": self.repository_type,
            "repository_kind": self.repository_kind,
            "repository_candidates": [
                candidate.to_dict() for candidate in self.repository_candidates
            ],
            "canonical_repository": (
                self.canonical_repository.to_dict() if self.canonical_repository else None
            ),
            "release_link": self.release_link.to_dict() if self.release_link else None,
            "version_reference": (
                self.version_reference.to_dict() if self.version_reference else None
            ),
            "repository_validated": self.repository_validated,
            "repository_validation_status": self.repository_validation_status,
            "confidence": self.confidence,
            "evidence": list(self.evidence),
            "warnings": list(self.warnings),
            "metadata_sources": list(self.metadata_sources),
        }


@dataclass(frozen=True)
class ResolverSettings:
    timeout: float = 10.0
    use_cache: bool = True
    cache_dir: str | None = None
    strict: bool = False
    no_network: bool = False
    verify_release_links: bool = False
    validate_repositories: bool = True
    use_deps_dev_fallback: bool = True
    use_scraper_fallback: bool = True
    user_agent: str = "purl2repo/2.x"
