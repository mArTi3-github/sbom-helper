from __future__ import annotations

from abc import ABC, abstractmethod

from ..schemas import ResolveResponse


class Storage(ABC):

    @abstractmethod
    async def lookup(self, purl: str) -> ResolveResponse | None: ...

    @abstractmethod
    async def store(self, result: ResolveResponse) -> None: ...
