from __future__ import annotations

from ..schemas import ResolveResponse
from .interface import Storage


class InMemoryCache(Storage):

    def __init__(self) -> None:
        self._store: dict[str, ResolveResponse] = {}

    async def lookup(self, purl: str) -> ResolveResponse | None:
        return self._store.get(purl)

    async def store(self, result: ResolveResponse) -> None:
        self._store[result.purl] = result

    def clear(self) -> None:
        self._store.clear()
