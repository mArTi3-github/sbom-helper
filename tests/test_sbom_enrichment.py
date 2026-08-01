from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from purl_resolver.resolver.interface import Resolution
from purl_resolver.sbom_enrichment import SbomEnrichmentPipeline
from purl_resolver.service import PurlResolutionService
from purl_resolver.settings_store import AppSettings
from purl_resolver.storage.inmemory import InMemoryCache
from tests.helpers import FakeResolver


class RecordingReporter:
    def __init__(self) -> None:
        self.phases: list[str] = []
        self.progress: list[tuple[int, int]] = []

    async def on_phase(self, phase: str) -> None:
        self.phases.append(phase)

    async def on_resolved(self, current: int, total: int) -> None:
        self.progress.append((current, total))


def _sbom_with_purls(purls: list[str]) -> dict:
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "components": [
            {"type": "library", "name": f"comp{i}", "version": "1.0.0", "purl": p}
            for i, p in enumerate(purls)
        ],
    }


@pytest.fixture
def resolution_service() -> PurlResolutionService:
    resolver = FakeResolver(
        resolution=Resolution(
            purl="pkg:pypi/requests@2.31.0",
            repository_url="https://github.com/psf/requests",
        ),
    )
    return PurlResolutionService(InMemoryCache(), [resolver])


class TestProgressReporter:

    @pytest.mark.asyncio
    async def test_reports_phases_and_progress(self, resolution_service) -> None:
        reporter = RecordingReporter()
        pipeline = SbomEnrichmentPipeline(resolution_service)
        await pipeline.process(
            _sbom_with_purls(["pkg:pypi/requests@2.31.0", "pkg:npm/express@4.17.1"]),
            progress_reporter=reporter,
        )
        assert reporter.phases == ["parsing", "resolving", "enriching"]
        assert reporter.progress[0] == (0, 2)
        assert reporter.progress[-1] == (2, 2)
        assert len(reporter.progress) == 3

    @pytest.mark.asyncio
    async def test_zero_total_still_reports_initial_call(self, resolution_service) -> None:
        reporter = RecordingReporter()
        pipeline = SbomEnrichmentPipeline(resolution_service)
        await pipeline.process(
            _sbom_with_purls(["not-a-purl"]),
            progress_reporter=reporter,
        )
        assert reporter.phases == ["parsing", "resolving", "enriching"]
        assert reporter.progress == [(0, 0)]

    @pytest.mark.asyncio
    async def test_validating_refs_phase_when_enabled(self) -> None:
        settings_store = MagicMock()
        settings_store.load.return_value = AppSettings(validate_sbom_refs=True)
        service = PurlResolutionService(
            InMemoryCache(), [FakeResolver()], settings_store=settings_store,
        )
        pipeline = SbomEnrichmentPipeline(service)
        pipeline._validate_external_references = AsyncMock()
        reporter = RecordingReporter()
        await pipeline.process(
            _sbom_with_purls(["pkg:pypi/requests@2.31.0"]),
            progress_reporter=reporter,
        )
        assert reporter.phases == ["parsing", "validating_refs", "resolving", "enriching"]

    @pytest.mark.asyncio
    async def test_without_reporter_unchanged(self, resolution_service) -> None:
        pipeline = SbomEnrichmentPipeline(resolution_service)
        result = await pipeline.process(_sbom_with_purls(["pkg:pypi/requests@2.31.0"]))
        assert result.enriched_sbom["components"][0]["externalReferences"]
