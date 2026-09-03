from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from purl_resolver.resolver.purl2repo import Purl2RepoResolver
from purl_resolver.router import router
from purl_resolver.sbom_enrichment import SbomEnrichmentPipeline
from purl_resolver.schemas import ResolveResponse
from purl_resolver.service import PurlResolutionService
from purl_resolver.settings_store import AppSettings, SettingsStore
from purl_resolver.storage.inmemory import InMemoryCache
from purl_resolver.url_validator import UrlValidationOutput, UrlValidationResult
from purl_resolver.validation_service import UrlValidationService


def _url_output(result: UrlValidationResult, final_url: str | None = None) -> UrlValidationOutput:
    return UrlValidationOutput(result=result, final_url=final_url)


@pytest.fixture
def client() -> TestClient:
    test_app = FastAPI()
    test_app.state.storage = InMemoryCache()
    test_app.state.settings_store = SettingsStore()
    test_app.state.resolvers = [Purl2RepoResolver()]
    test_app.state.resolution_service = PurlResolutionService(
        storage=test_app.state.storage,
        resolvers=test_app.state.resolvers,
    )
    test_app.include_router(router)
    with TestClient(test_app) as c:
        yield c


class TestValidateExistingRefs:

    @pytest.fixture
    def settings_store_with_validation(self) -> MagicMock:
        store = MagicMock()
        store.load.return_value = AppSettings(
            validate_db_urls=True, validate_sbom_refs=True,
            url_validation_timeout=5,
            revalidation_cooldown_hours=24,
            sbom_multiple_vcs_behavior="keep-first",
        )
        return store

    @pytest.fixture
    def settings_store_with_validation_keep_all(self) -> MagicMock:
        store = MagicMock()
        store.load.return_value = AppSettings(
            validate_db_urls=True, validate_sbom_refs=True,
            url_validation_timeout=5,
            revalidation_cooldown_hours=24,
            sbom_multiple_vcs_behavior="keep-all",
        )
        return store

    @pytest.fixture
    def settings_store_no_validation(self) -> MagicMock:
        store = MagicMock()
        store.load.return_value = AppSettings(
            validate_db_urls=True, validate_sbom_refs=False,
            url_validation_timeout=5,
            revalidation_cooldown_hours=24,
        )
        return store

    @pytest.mark.asyncio
    async def test_invalid_url_triggers_reresolution(
        self,
        fake_resolvers,
        settings_store_with_validation,
    ):
        sbom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "components": [
                {
                    "type": "library",
                    "name": "requests",
                    "version": "2.31.0",
                    "purl": "pkg:pypi/requests@2.31.0",
                    "externalReferences": [
                        {"type": "vcs", "url": "https://github.com/psf/requests-invalid"},
                    ],
                }
            ],
        }
        storage = InMemoryCache()
        pipeline = SbomEnrichmentPipeline(
            resolution_service=PurlResolutionService(
                storage, fake_resolvers,
                settings_store=settings_store_with_validation,
            ),
        )
        with patch(
            "purl_resolver.sbom_enrichment.validate_url",
            new_callable=AsyncMock,
            return_value=_url_output(UrlValidationResult.INVALID),
        ):
            await pipeline.process(sbom)
        enriched_refs = sbom["components"][0].get("externalReferences", [])
        found_new_ref = any(
            r.get("type") == "vcs" and "github.com" in (r.get("url") or "")
            for r in enriched_refs
        )
        assert found_new_ref, "Expected a new VCS ref from resolution, got: %s" % enriched_refs

    @pytest.mark.asyncio
    async def test_valid_url_skips_reresolution(
        self,
        fake_resolvers,
        settings_store_with_validation,
    ):
        sbom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "components": [
                {
                    "type": "library",
                    "name": "requests",
                    "version": "2.31.0",
                    "purl": "pkg:pypi/requests@2.31.0",
                    "externalReferences": [
                        {"type": "vcs", "url": "https://github.com/psf/requests"},
                    ],
                }
            ],
        }
        original_refs = list(sbom["components"][0].get("externalReferences", []))
        storage = InMemoryCache()
        pipeline = SbomEnrichmentPipeline(
            resolution_service=PurlResolutionService(
                storage, fake_resolvers,
                settings_store=settings_store_with_validation,
            ),
        )
        with patch(
            "purl_resolver.sbom_enrichment.validate_url",
            new_callable=AsyncMock,
            return_value=_url_output(UrlValidationResult.VALID),
        ):
            await pipeline.process(sbom)
        enriched_refs = sbom["components"][0].get("externalReferences", [])
        assert len(enriched_refs) == len(original_refs)
        assert enriched_refs[0]["url"] == original_refs[0]["url"]

    @pytest.mark.asyncio
    async def test_default_off(
        self,
        fake_resolvers,
        settings_store_no_validation,
    ):
        sbom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "components": [
                {
                    "type": "library",
                    "name": "requests",
                    "version": "2.31.0",
                    "purl": "pkg:pypi/requests@2.31.0",
                    "externalReferences": [
                        {"type": "vcs", "url": "https://github.com/psf/requests-invalid"},
                    ],
                }
            ],
        }
        storage = InMemoryCache()
        pipeline = SbomEnrichmentPipeline(
            resolution_service=PurlResolutionService(
                storage, fake_resolvers,
                settings_store=settings_store_no_validation,
            ),
        )
        with patch(
            "purl_resolver.sbom_enrichment.validate_url", new_callable=AsyncMock
        ) as mock_validate:
            await pipeline.process(sbom)
        mock_validate.assert_not_called()

    @pytest.mark.asyncio
    async def test_network_error_removes_ref_and_triggers_reresolution(
        self,
        fake_resolvers,
        settings_store_with_validation,
    ):
        sbom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "components": [
                {
                    "type": "library",
                    "name": "requests",
                    "version": "2.31.0",
                    "purl": "pkg:pypi/requests@2.31.0",
                    "externalReferences": [
                        {"type": "vcs", "url": "https://unknown-vcs.example.com/repo"},
                    ],
                }
            ],
        }
        storage = InMemoryCache()
        pipeline = SbomEnrichmentPipeline(
            resolution_service=PurlResolutionService(
                storage, fake_resolvers,
                settings_store=settings_store_with_validation,
            ),
        )
        with patch(
            "purl_resolver.sbom_enrichment.validate_url",
            new_callable=AsyncMock,
            return_value=_url_output(UrlValidationResult.NETWORK_ERROR),
        ):
            await pipeline.process(sbom)
        enriched_refs = sbom["components"][0].get("externalReferences", [])
        found_new_ref = any(
            r.get("type") == "vcs" and "github.com" in (r.get("url") or "")
            for r in enriched_refs
        )
        assert found_new_ref, (
            "Expected NETWORK_ERROR ref to be removed and "
            "re-resolution to add a new VCS ref, got: %s" % enriched_refs
        )

    @pytest.mark.asyncio
    async def test_mixed_refs_non_vcs_preserved_when_vcs_invalid(
        self,
        fake_resolvers,
        settings_store_with_validation,
    ):
        sbom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "components": [
                {
                    "type": "library",
                    "name": "requests",
                    "version": "2.31.0",
                    "purl": "pkg:pypi/requests@2.31.0",
                    "externalReferences": [
                        {"type": "website", "url": "https://example.com"},
                        {"type": "vcs", "url": "https://github.com/psf/requests-invalid"},
                    ],
                }
            ],
        }
        storage = InMemoryCache()
        pipeline = SbomEnrichmentPipeline(
            resolution_service=PurlResolutionService(
                storage, fake_resolvers,
                settings_store=settings_store_with_validation,
            ),
        )
        with patch(
            "purl_resolver.sbom_enrichment.validate_url",
            new_callable=AsyncMock,
            return_value=_url_output(UrlValidationResult.INVALID),
        ):
            await pipeline.process(sbom)
        enriched_refs = sbom["components"][0].get("externalReferences", [])
        website_refs = [r for r in enriched_refs if r["type"] == "website"]
        assert len(website_refs) == 1, "Non-VCS ref should be preserved"
        assert website_refs[0]["url"] == "https://example.com"

    @pytest.mark.asyncio
    async def test_multiple_vcs_keep_first_retains_only_first_valid(
        self,
        fake_resolvers,
        settings_store_with_validation,
    ):
        sbom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "components": [
                {
                    "type": "library",
                    "name": "requests",
                    "version": "2.31.0",
                    "purl": "pkg:pypi/requests@2.31.0",
                    "externalReferences": [
                        {"type": "website", "url": "https://example.com"},
                        {"type": "vcs", "url": "https://github.com/psf/requests-first"},
                        {"type": "vcs", "url": "https://github.com/psf/requests-second"},
                    ],
                }
            ],
        }
        storage = InMemoryCache()
        pipeline = SbomEnrichmentPipeline(
            resolution_service=PurlResolutionService(
                storage, fake_resolvers,
                settings_store=settings_store_with_validation,
            ),
        )
        with patch(
            "purl_resolver.sbom_enrichment.validate_url",
            new_callable=AsyncMock,
            return_value=_url_output(UrlValidationResult.VALID),
        ):
            await pipeline.process(sbom)
        enriched_refs = sbom["components"][0].get("externalReferences", [])
        vcs_refs = [r for r in enriched_refs if r["type"] == "vcs"]
        assert len(vcs_refs) == 1, "Only one VCS ref should remain with keep-first"
        assert vcs_refs[0]["url"] == "https://github.com/psf/requests-first"

    @pytest.mark.asyncio
    async def test_multiple_vcs_keep_all_retains_all_valid(
        self,
        fake_resolvers,
        settings_store_with_validation_keep_all,
    ):
        sbom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "components": [
                {
                    "type": "library",
                    "name": "requests",
                    "version": "2.31.0",
                    "purl": "pkg:pypi/requests@2.31.0",
                    "externalReferences": [
                        {"type": "website", "url": "https://example.com"},
                        {"type": "vcs", "url": "https://github.com/psf/requests-first"},
                        {"type": "vcs", "url": "https://github.com/psf/requests-second"},
                    ],
                }
            ],
        }
        storage = InMemoryCache()
        pipeline = SbomEnrichmentPipeline(
            resolution_service=PurlResolutionService(
                storage, fake_resolvers,
                settings_store=settings_store_with_validation_keep_all,
            ),
        )
        with patch(
            "purl_resolver.sbom_enrichment.validate_url",
            new_callable=AsyncMock,
            return_value=_url_output(UrlValidationResult.VALID),
        ):
            await pipeline.process(sbom)
        enriched_refs = sbom["components"][0].get("externalReferences", [])
        vcs_refs = [r for r in enriched_refs if r["type"] == "vcs"]
        assert len(vcs_refs) == 2, "Both VCS refs should remain with keep-all"
        assert vcs_refs[0]["url"] == "https://github.com/psf/requests-first"
        assert vcs_refs[1]["url"] == "https://github.com/psf/requests-second"

    @pytest.mark.asyncio
    async def test_all_vcs_invalid_triggers_reresolution_with_keep_all(
        self,
        fake_resolvers,
        settings_store_with_validation_keep_all,
    ):
        sbom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "components": [
                {
                    "type": "library",
                    "name": "requests",
                    "version": "2.31.0",
                    "purl": "pkg:pypi/requests@2.31.0",
                    "externalReferences": [
                        {"type": "vcs", "url": "https://github.com/psf/requests-invalid1"},
                        {"type": "vcs", "url": "https://github.com/psf/requests-invalid2"},
                    ],
                }
            ],
        }
        storage = InMemoryCache()
        pipeline = SbomEnrichmentPipeline(
            resolution_service=PurlResolutionService(
                storage, fake_resolvers,
                settings_store=settings_store_with_validation_keep_all,
            ),
        )
        with patch(
            "purl_resolver.sbom_enrichment.validate_url",
            new_callable=AsyncMock,
            return_value=_url_output(UrlValidationResult.INVALID),
        ):
            await pipeline.process(sbom)
        enriched_refs = sbom["components"][0].get("externalReferences", [])
        found_new_ref = any(
            r.get("type") == "vcs" and "github.com" in (r.get("url") or "")
            for r in enriched_refs
        )
        assert found_new_ref, "Expected re-resolution when all VCS refs are invalid"

    @pytest.mark.asyncio
    async def test_redirect_updates_ref_url(
        self,
        fake_resolvers,
        settings_store_with_validation,
    ):
        sbom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "components": [
                {
                    "type": "library",
                    "name": "requests",
                    "version": "2.31.0",
                    "purl": "pkg:pypi/requests@2.31.0",
                    "externalReferences": [
                        {"type": "vcs", "url": "https://old-url.com/psf/requests"},
                    ],
                }
            ],
        }
        storage = InMemoryCache()
        pipeline = SbomEnrichmentPipeline(
            resolution_service=PurlResolutionService(
                storage, fake_resolvers,
                settings_store=settings_store_with_validation,
            ),
        )
        with patch(
            "purl_resolver.sbom_enrichment.validate_url",
            new_callable=AsyncMock,
            return_value=_url_output(UrlValidationResult.VALID, final_url="https://github.com/psf/requests"),
        ):
            await pipeline.process(sbom)
        enriched_refs = sbom["components"][0].get("externalReferences", [])
        assert len(enriched_refs) == 1
        assert enriched_refs[0]["url"] == "https://github.com/psf/requests"

    @pytest.mark.asyncio
    async def test_validate_existing_refs_delegates_to_validation_service(
        self,
        fake_resolvers,
        settings_store_with_validation,
    ):
        sbom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "components": [
                {
                    "type": "library",
                    "name": "requests",
                    "version": "2.31.0",
                    "purl": "pkg:pypi/requests@2.31.0",
                    "externalReferences": [
                        {"type": "vcs", "url": "https://github.com/psf/requests"},
                    ],
                }
            ],
        }
        storage = InMemoryCache()
        mock_validation = AsyncMock(spec=UrlValidationService)
        mock_validation.validate_url = AsyncMock(
            return_value=_url_output(UrlValidationResult.VALID),
        )
        pipeline = SbomEnrichmentPipeline(
            resolution_service=PurlResolutionService(
                storage, fake_resolvers,
                settings_store=settings_store_with_validation,
                validation_service=mock_validation,
            ),
        )
        await pipeline.process(sbom)
        mock_validation.validate_url.assert_called_once_with(
            "https://github.com/psf/requests",
            timeout=5,
        )

    @pytest.mark.asyncio
    async def test_duplicate_invalid_url_validated_once_and_removed_everywhere(
        self,
        fake_resolvers,
        settings_store_with_validation,
    ):
        shared_url = "https://github.com/psf/requests-invalid"
        sbom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "components": [
                {
                    "type": "library",
                    "name": "requests",
                    "version": "2.31.0",
                    "purl": "pkg:pypi/requests@2.31.0",
                    "externalReferences": [
                        {"type": "vcs", "url": shared_url},
                    ],
                },
                {
                    "type": "library",
                    "name": "requests-cli",
                    "version": "2.31.0",
                    "purl": "pkg:pypi/requests-cli@2.31.0",
                    "externalReferences": [
                        {"type": "vcs", "url": shared_url},
                    ],
                },
            ],
        }
        storage = InMemoryCache()
        pipeline = SbomEnrichmentPipeline(
            resolution_service=PurlResolutionService(
                storage, fake_resolvers,
                settings_store=settings_store_with_validation,
            ),
        )
        with patch(
            "purl_resolver.sbom_enrichment.validate_url",
            new_callable=AsyncMock,
            return_value=_url_output(UrlValidationResult.INVALID),
        ) as mock_validate:
            await pipeline.process(sbom)
        mock_validate.assert_called_once_with(shared_url, timeout=5)
        for comp in sbom["components"]:
            refs = comp.get("externalReferences", [])
            assert not any(
                r.get("type") == "vcs" and r.get("url") == shared_url
                for r in refs
            ), (
                "Duplicate invalid ref should be removed from %s, got: %s"
                % (comp["name"], refs)
            )

    @pytest.mark.asyncio
    async def test_duplicate_valid_url_validated_once_and_redirect_applied_everywhere(
        self,
        fake_resolvers,
        settings_store_with_validation,
    ):
        shared_url = "https://old-url.com/psf/requests"
        final_url = "https://github.com/psf/requests"
        sbom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "components": [
                {
                    "type": "library",
                    "name": "requests",
                    "version": "2.31.0",
                    "purl": "pkg:pypi/requests@2.31.0",
                    "externalReferences": [
                        {"type": "vcs", "url": shared_url},
                    ],
                },
                {
                    "type": "library",
                    "name": "requests-cli",
                    "version": "2.31.0",
                    "purl": "pkg:pypi/requests-cli@2.31.0",
                    "externalReferences": [
                        {"type": "vcs", "url": shared_url},
                    ],
                },
            ],
        }
        storage = InMemoryCache()
        pipeline = SbomEnrichmentPipeline(
            resolution_service=PurlResolutionService(
                storage, fake_resolvers,
                settings_store=settings_store_with_validation,
            ),
        )
        with patch(
            "purl_resolver.sbom_enrichment.validate_url",
            new_callable=AsyncMock,
            return_value=_url_output(
                UrlValidationResult.VALID, final_url=final_url
            ),
        ) as mock_validate:
            await pipeline.process(sbom)
        mock_validate.assert_called_once_with(shared_url, timeout=5)
        for comp in sbom["components"]:
            vcs_refs = [
                r
                for r in comp.get("externalReferences", [])
                if r.get("type") == "vcs"
            ]
            assert len(vcs_refs) == 1, (
                "Redirected ref should remain once in %s, got: %s"
                % (comp["name"], vcs_refs)
            )
            assert vcs_refs[0]["url"] == final_url

    @pytest.mark.asyncio
    async def test_duplicate_url_validated_once_via_validation_service(
        self,
        fake_resolvers,
        settings_store_with_validation,
    ):
        shared_url = "https://github.com/psf/requests-invalid"
        sbom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "components": [
                {
                    "type": "library",
                    "name": "requests",
                    "version": "2.31.0",
                    "purl": "pkg:pypi/requests@2.31.0",
                    "externalReferences": [
                        {"type": "vcs", "url": shared_url},
                    ],
                },
                {
                    "type": "library",
                    "name": "requests-cli",
                    "version": "2.31.0",
                    "purl": "pkg:pypi/requests-cli@2.31.0",
                    "externalReferences": [
                        {"type": "vcs", "url": shared_url},
                    ],
                },
            ],
        }
        storage = InMemoryCache()
        mock_validation = AsyncMock(spec=UrlValidationService)
        mock_validation.validate_url = AsyncMock(
            return_value=_url_output(UrlValidationResult.INVALID),
        )
        pipeline = SbomEnrichmentPipeline(
            resolution_service=PurlResolutionService(
                storage, fake_resolvers,
                settings_store=settings_store_with_validation,
                validation_service=mock_validation,
            ),
        )
        await pipeline.process(sbom)
        shared_calls = [
            c
            for c in mock_validation.validate_url.call_args_list
            if c.args and c.args[0] == shared_url
        ]
        assert len(shared_calls) == 1, (
            "Shared URL should be validated once, got: %s"
            % mock_validation.validate_url.call_args_list
        )
        mock_validation.validate_url.assert_any_call(shared_url, timeout=5)
        for comp in sbom["components"]:
            refs = comp.get("externalReferences", [])
            assert not any(
                r.get("type") == "vcs" and r.get("url") == shared_url
                for r in refs
            ), (
                "Duplicate invalid ref should be removed from %s, got: %s"
                % (comp["name"], refs)
            )


class TestFileUrlInvalidation:
    """Verify that file:// URLs in cache are invalidated and deleted during SBOM pipeline."""

    @pytest.fixture
    def storage_with_file_url(self) -> InMemoryCache:
        cache = InMemoryCache()
        cache._store["pkg:pypi/ptaf-task-manager"] = ResolveResponse(
            purl="pkg:pypi/ptaf-task-manager",
            repository_url="file:///usr/src/app/ptaf-task-mgr",
            resolver="import-sbom",
        )
        return cache

    @pytest.fixture
    def settings_store_with_validation(self) -> MagicMock:
        store = MagicMock()
        store.load.return_value = AppSettings(
            validate_db_urls=True,
            url_validation_timeout=5,
            revalidation_cooldown_hours=24,
        )
        return store

    @pytest.fixture
    def validation_service(self) -> AsyncMock:
        vs = AsyncMock(spec=UrlValidationService)
        vs.validate_url.return_value = _url_output(UrlValidationResult.INVALID)
        return vs

    @pytest.mark.asyncio
    async def test_resolve_batch_deletes_file_url_entry(
        self,
        storage_with_file_url,
        settings_store_with_validation,
        fake_empty_resolvers,
        validation_service,
    ):
        """resolve_batch deletes invalid file:// entries from cache."""
        svc = PurlResolutionService(
            storage_with_file_url,
            fake_empty_resolvers,
            settings_store=settings_store_with_validation,
            validation_service=validation_service,
        )
        result = await svc.resolve_batch(
            ["pkg:pypi/ptaf-task-manager"],
            resolver="import-sbom",
        )
        # Entry should be absent from storage (deleted by _validate_stored_url)
        remaining = await storage_with_file_url.lookup("pkg:pypi/ptaf-task-manager")
        assert remaining is None, "file:// entry should have been deleted from storage"
        # Batch result should be empty (no resolver found a valid URL)
        assert "pkg:pypi/ptaf-task-manager" not in result

    @pytest.mark.asyncio
    async def test_sbom_pipeline_deletes_file_url_entry(
        self,
        storage_with_file_url,
        settings_store_with_validation,
        fake_empty_resolvers,
        validation_service,
    ):
        """SbomEnrichmentPipeline.process cleans up file:// entries during enrichment."""
        sbom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "components": [
                {
                    "type": "library",
                    "name": "ptaf-task-manager",
                    "version": "1.0",
                    "purl": "pkg:pypi/ptaf-task-manager",
                }
            ],
        }
        pipeline = SbomEnrichmentPipeline(
            resolution_service=PurlResolutionService(
                storage_with_file_url,
                fake_empty_resolvers,
                settings_store=settings_store_with_validation,
                validation_service=validation_service,
            ),
        )
        result = await pipeline.process(sbom)
        # DB entry should be deleted after processing
        remaining = await storage_with_file_url.lookup("pkg:pypi/ptaf-task-manager")
        assert remaining is None, (
            "file:// entry should have been deleted from storage after pipeline run"
        )
        # Report should show not_found (resolvers can't find this package)
        summary = result.report["summary"]
        assert summary["not_found"] >= 1, "Component with file:// URL should show as not_found"


class TestConnectivityPreCheck:
    """Integration tests: connectivity check happens once per user action."""

    def test_batch_resolve_fails_when_connectivity_down(self, client: TestClient) -> None:
        with patch(
            "purl_resolver.routes.resolve.ensure_connectivity",
            new_callable=AsyncMock,
            side_effect=ConnectionError("Cannot reach https://github.com"),
        ):
            response = client.post(
                "/api/v1/resolve/batch",
                json={"purls": ["pkg:pypi/requests@2.31.0"]},
            )
        assert response.status_code == 503
        data = response.json()
        assert data["error"] == "network_unavailable"
