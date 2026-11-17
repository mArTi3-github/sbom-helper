from __future__ import annotations

from .source_archive import SourceArchiveRow, SourceArchiveStorage


class InMemorySourceArchiveStorage(SourceArchiveStorage):

    def __init__(self) -> None:
        self._store: dict[str, SourceArchiveRow] = {}

    async def lookup_archive(self, purl: str) -> SourceArchiveRow | None:
        return self._store.get(purl)

    async def store_archive(self, row: SourceArchiveRow) -> None:
        self._store[row.purl] = row

    def clear(self) -> None:
        self._store.clear()
