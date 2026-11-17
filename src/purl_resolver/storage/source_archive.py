from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class SourceArchiveRow:
    purl: str
    version: str
    match_type: str
    reason: str | None = None
    archive_url: str | None = None
    archive_url_commit: str | None = None
    matched_ref: str | None = None
    matched_ref_type: str | None = None
    matched_version: str | None = None
    repository_url: str | None = None
    resolver: str = ""
    resolved_at: str = ""


class SourceArchiveStorage(ABC):

    @abstractmethod
    async def lookup_archive(self, purl: str) -> SourceArchiveRow | None: ...

    @abstractmethod
    async def store_archive(self, row: SourceArchiveRow) -> None: ...
