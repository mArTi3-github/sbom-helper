from __future__ import annotations

from purl_resolver.resolver.interface import Resolution, Resolver


class FakeResolver(Resolver):

    def __init__(
        self, resolution: Resolution | None = None, error: Exception | None = None
    ) -> None:
        self._resolution = resolution
        self._error = error
        self.call_count = 0

    @property
    def name(self) -> str:
        return "fake"

    def resolve(self, purl: str) -> Resolution:
        self.call_count += 1
        if self._error:
            raise self._error
        if self._resolution:
            return self._resolution
        return Resolution(purl=purl)