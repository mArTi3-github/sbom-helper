from __future__ import annotations

import pytest

from purl_resolver.resolver.interface import Resolution, Resolver


class DummyResolver(Resolver):
    @property
    def name(self) -> str:
        return "dummy"

    def resolve(self, purl: str) -> Resolution:
        raise NotImplementedError


class TestResolverName:
    def test_name_property(self) -> None:
        r = DummyResolver()
        assert r.name == "dummy"

    def test_subclass_must_implement_name(self) -> None:
        with pytest.raises(TypeError):
            Resolver()  # type: ignore[abstract]
