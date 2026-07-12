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
    warnings: list[str] = field(default_factory=list)


class Resolver(ABC):

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    async def resolve(self, purl: str) -> Resolution: ...
