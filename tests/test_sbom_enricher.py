from __future__ import annotations

from purl_resolver.sbom.collector import collect_components
from purl_resolver.sbom.enricher import enrich_sbom
from purl_resolver.schemas import ResolveResponse


class TestEnrichSbom:
    def test_inserts_vcs_reference_for_component_without_refs(self) -> None:
        sbom = {
            "version": 1,
            "metadata": {"timestamp": "2024-01-01T00:00:00"},
            "components": [
                {
                    "type": "library",
                    "name": "lib-a",
                    "version": "1.0",
                    "purl": "pkg:pypi/lib-a@1.0",
                }
            ],
        }
        resolved = {"pkg:pypi/lib-a": ResolveResponse(purl="pkg:pypi/lib-a", repository_url="https://github.com/example/lib-a")}
        components = collect_components(sbom)
        enrich_sbom(sbom, components, resolved)
        comp = sbom["components"][0]
        assert comp["externalReferences"] == [
            {"type": "vcs", "url": "https://github.com/example/lib-a"}
        ]

    def test_preserves_existing_references_and_appends_vcs(self) -> None:
        sbom = {
            "version": 1,
            "metadata": {"timestamp": "2024-01-01T00:00:00"},
            "components": [
                {
                    "type": "library",
                    "name": "lib-a",
                    "version": "1.0",
                    "purl": "pkg:pypi/lib-a@1.0",
                    "externalReferences": [
                        {"type": "website", "url": "https://example.com"}
                    ],
                }
            ],
        }
        resolved = {"pkg:pypi/lib-a": ResolveResponse(purl="pkg:pypi/lib-a", repository_url="https://github.com/example/lib-a")}
        components = collect_components(sbom)
        enrich_sbom(sbom, components, resolved)
        comp = sbom["components"][0]
        assert len(comp["externalReferences"]) == 2
        assert comp["externalReferences"][0] == {"type": "website", "url": "https://example.com"}
        assert comp["externalReferences"][1] == {"type": "vcs", "url": "https://github.com/example/lib-a"}

    def test_skips_component_not_in_resolved_map(self) -> None:
        sbom = {
            "version": 1,
            "metadata": {"timestamp": "2024-01-01T00:00:00"},
            "components": [
                {
                    "type": "library",
                    "name": "lib-a",
                    "version": "1.0",
                    "purl": "pkg:pypi/lib-a@1.0",
                }
            ],
        }
        resolved: dict[str, ResolveResponse] = {}
        components = collect_components(sbom)
        enrich_sbom(sbom, components, resolved)
        assert "externalReferences" not in sbom["components"][0]

    def test_skips_component_with_vcs_already_present(self) -> None:
        sbom = {
            "version": 1,
            "metadata": {"timestamp": "2024-01-01T00:00:00"},
            "components": [
                {
                    "type": "library",
                    "name": "lib-a",
                    "version": "1.0",
                    "purl": "pkg:pypi/lib-a@1.0",
                    "externalReferences": [
                        {"type": "vcs", "url": "https://github.com/example/lib-a"}
                    ],
                }
            ],
        }
        resolved = {"pkg:pypi/lib-a": ResolveResponse(purl="pkg:pypi/lib-a", repository_url="https://github.com/example/lib-a")}
        components = collect_components(sbom)
        enrich_sbom(sbom, components, resolved)
        comp = sbom["components"][0]
        assert len(comp["externalReferences"]) == 1
        assert comp["externalReferences"][0]["type"] == "vcs"

    def test_increments_version(self) -> None:
        sbom = {
            "version": 2,
            "metadata": {"timestamp": "2024-01-01T00:00:00"},
            "components": [
                {
                    "type": "library",
                    "name": "lib-a",
                    "version": "1.0",
                    "purl": "pkg:pypi/lib-a@1.0",
                }
            ],
        }
        resolved = {"pkg:pypi/lib-a": ResolveResponse(purl="pkg:pypi/lib-a", repository_url="https://github.com/example/lib-a")}
        components = collect_components(sbom)
        enrich_sbom(sbom, components, resolved)
        assert sbom["version"] == 3

    def test_handles_nested_components(self) -> None:
        sbom = {
            "version": 1,
            "metadata": {"timestamp": "2024-01-01T00:00:00"},
            "components": [
                {
                    "type": "application",
                    "name": "app",
                    "version": "1.0",
                    "purl": "pkg:generic/app@1.0",
                    "components": [
                        {
                            "type": "library",
                            "name": "sub",
                            "version": "0.5",
                            "purl": "pkg:pypi/sub@0.5",
                        }
                    ],
                }
            ],
        }
        resolved = {"pkg:pypi/sub": ResolveResponse(purl="pkg:pypi/sub", repository_url="https://github.com/example/sub")}
        components = collect_components(sbom)
        enrich_sbom(sbom, components, resolved)
        sub = sbom["components"][0]["components"][0]
        assert sub["externalReferences"] == [
            {"type": "vcs", "url": "https://github.com/example/sub"}
        ]

    def test_applies_same_url_to_multiple_components_with_matching_purl(
        self,
    ) -> None:
        sbom = {
            "version": 1,
            "metadata": {"timestamp": "2024-01-01T00:00:00"},
            "components": [
                {
                    "type": "library",
                    "name": "lib-a",
                    "version": "1.0",
                    "purl": "pkg:pypi/lib-a@1.0",
                },
                {
                    "type": "library",
                    "name": "lib-a",
                    "version": "2.0",
                    "purl": "pkg:pypi/lib-a@2.0",
                },
            ],
        }
        resolved = {"pkg:pypi/lib-a": ResolveResponse(purl="pkg:pypi/lib-a", repository_url="https://github.com/example/lib-a")}
        components = collect_components(sbom)
        enrich_sbom(sbom, components, resolved)
        assert sbom["components"][0]["externalReferences"][0]["url"] == resolved["pkg:pypi/lib-a"].repository_url
        assert sbom["components"][1]["externalReferences"][0]["url"] == resolved["pkg:pypi/lib-a"].repository_url

    def test_build_report_includes_removed(self) -> None:
        from purl_resolver.sbom.reporter import build_report
        sbom = {
            "version": 1,
            "metadata": {"timestamp": "2024-01-01T00:00:00"},
            "components": [
                {"type": "library", "name": "a", "version": "1.0", "purl": "pkg:pypi/a@1.0"},
            ],
        }
        components = collect_components(sbom)
        resolved = {"pkg:pypi/a": ResolveResponse(purl="pkg:pypi/a", repository_url="https://github.com/example/a")}
        removed = [{"purl": "pkg:pypi/b@2", "name": "b", "version": "2"}]
        report = build_report(components, resolved, skipped=0, removed=removed)
        assert report["summary"]["removed"] == 1
        assert any(r["status"] == "removed" for r in report["results"])
