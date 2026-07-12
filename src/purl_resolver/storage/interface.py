from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date

from ..schemas import ResolveResponse


@dataclass
class PurlFilters:
    search: str | None = None
    resolver: str | None = None
    date_from: date | None = None
    date_to: date | None = None


@dataclass
class PurlRow:
    purl: str
    repository_url: str
    resolver: str = ""
    resolved_at: str = ""

    @classmethod
    def from_response(cls, r: ResolveResponse) -> PurlRow:
        return cls(
            purl=r.purl,
            repository_url=r.repository_url,
            resolver=r.resolver,
            resolved_at=r.resolved_at or "",
        )

    def to_resolve_response(self) -> ResolveResponse:
        return ResolveResponse(
            purl=self.purl,
            repository_url=self.repository_url,
            resolver=self.resolver,
            resolved_at=self.resolved_at,
        )


@dataclass
class UpsertRow:
    purl: str
    repository_url: str
    resolver: str = "purl2repo"


class Storage(ABC):

    @abstractmethod
    async def lookup(self, purl: str) -> ResolveResponse | None: ...

    @abstractmethod
    async def store(self, result: ResolveResponse) -> None: ...

    @abstractmethod
    async def list_purls(
        self,
        offset: int,
        limit: int,
        filters: PurlFilters,
        sort_by: str = "resolved_at",
        sort_order: str = "desc",
    ) -> list[PurlRow]: ...

    @abstractmethod
    async def count_purls(self, filters: PurlFilters) -> int: ...

    @abstractmethod
    async def update_purl(
        self, old_purl: str, purl: str, repository_url: str
    ) -> bool: ...

    @abstractmethod
    async def delete_purls(self, purls: list[str]) -> int: ...

    @abstractmethod
    async def upsert_many(
        self, rows: list[UpsertRow]
    ) -> tuple[int, int]: ...
