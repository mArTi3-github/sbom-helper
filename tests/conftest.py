from __future__ import annotations

import pytest

from purl_resolver.resolver.interface import Resolution
from tests.helpers import FakeResolver


@pytest.fixture
def fake_resolvers() -> list[FakeResolver]:
    return [
        FakeResolver(
            resolution=Resolution(
                purl="pkg:pypi/requests@2.31.0",
                repository_url="https://github.com/psf/requests",
            ),
        ),
    ]


@pytest.fixture
def fake_empty_resolvers() -> list[FakeResolver]:
    return [FakeResolver()]
