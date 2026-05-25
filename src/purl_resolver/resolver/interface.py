from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


class ResolverError(Exception):
    ...


class InvalidPurlError(ResolverError):
    ...


class UpstreamError(ResolverError):
    ...


@dataclass(frozen=True)
class Resolution:
    purl: str
    repository_url: str | None = None
    repository_type: str | None = None
    repository_kind: str | None = None
    confidence: str | None = None
    evidence: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    version_reference: str | None = None


class Resolver(ABC):

    @abstractmethod
    def resolve(self, purl: str) -> Resolution: ...
