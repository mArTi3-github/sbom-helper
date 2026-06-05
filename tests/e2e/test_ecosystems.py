from __future__ import annotations

import os

import pytest

from purl_resolver.resolver.ecosystems import EcosystemsResolver

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_E2E") == "1",
    reason="Set SKIP_E2E=1 to skip e2e tests (require network)",
)


class TestE2EEcosystemsResolver:

    def test_resolve_real_request(self) -> None:
        r = EcosystemsResolver(timeout=15.0)
        result = r.resolve("pkg:pypi/requests")
        assert result.repository_url == "https://github.com/psf/requests"
        assert result.confidence == "medium"
        assert result.repository_kind == "vcs"
        assert len(result.evidence) > 0

    def test_resolve_unknown_package(self) -> None:
        r = EcosystemsResolver(timeout=15.0)
        result = r.resolve("pkg:pypi/nonexistent-pkg-xyz-12345")
        assert result.repository_url is None
        assert len(result.warnings) > 0

    def test_resolve_npm_package(self) -> None:
        r = EcosystemsResolver(timeout=15.0)
        result = r.resolve("pkg:npm/express")
        assert result.repository_url is not None
        assert "github.com" in result.repository_url
