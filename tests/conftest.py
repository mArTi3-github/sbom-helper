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
                repository_type="github",
                repository_kind="source_code",
                confidence="high",
                evidence=["verified"],
            ),
        ),
    ]


@pytest.fixture
def fake_empty_resolvers() -> list[FakeResolver]:
    return [FakeResolver()]