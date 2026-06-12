from __future__ import annotations

from purl_resolver.sbom.collector import collect_components


class TestCollectComponents:
    def test_flat_components(self) -> None:
        sbom = {
            "components": [
                {
                    "type": "library",
                    "name": "lib-a",
                    "version": "1.0",
                    "purl": "pkg:pypi/lib-a@1.0",
                    "externalReferences": [
                        {"type": "vcs", "url": "https://example.com/lib-a"}
                    ],
                },
                {
                    "type": "library",
                    "name": "lib-b",
                    "version": "2.0",
                    "purl": "pkg:pypi/lib-b@2.0",
                },
            ]
        }
        result = collect_components(sbom)
        assert len(result) == 2

    def test_skips_component_with_vcs_external_reference(self) -> None:
        sbom = {
            "components": [
                {
                    "type": "library",
                    "name": "lib-a",
                    "version": "1.0",
                    "purl": "pkg:pypi/lib-a@1.0",
                    "externalReferences": [
                        {"type": "vcs", "url": "https://example.com/lib-a"}
                    ],
                }
            ]
        }
        result = collect_components(sbom)
        assert len(result) == 1
        comp = result[0]
        assert comp.purl == "pkg:pypi/lib-a@1.0"
        assert comp.needs_enrichment is False

    def test_identifies_component_without_external_references(self) -> None:
        sbom = {
            "components": [
                {
                    "type": "library",
                    "name": "lib-b",
                    "version": "2.0",
                    "purl": "pkg:pypi/lib-b@2.0",
                }
            ]
        }
        result = collect_components(sbom)
        assert len(result) == 1
        comp = result[0]
        assert comp.needs_enrichment is True

    def test_identifies_component_without_vcs_in_external_references(
        self,
    ) -> None:
        sbom = {
            "components": [
                {
                    "type": "library",
                    "name": "lib-c",
                    "version": "3.0",
                    "purl": "pkg:pypi/lib-c@3.0",
                    "externalReferences": [
                        {"type": "website", "url": "https://example.com"}
                    ],
                }
            ]
        }
        result = collect_components(sbom)
        assert len(result) == 1
        assert result[0].needs_enrichment is True

    def test_identifies_component_with_source_distribution(self) -> None:
        sbom = {
            "components": [
                {
                    "type": "library",
                    "name": "lib-d",
                    "version": "4.0",
                    "purl": "pkg:pypi/lib-d@4.0",
                    "externalReferences": [
                        {
                            "type": "source-distribution",
                            "url": "https://example.com/lib-d.tar.gz",
                        }
                    ],
                }
            ]
        }
        result = collect_components(sbom)
        assert len(result) == 1
        assert result[0].needs_enrichment is False

    def test_recursive_components(self) -> None:
        sbom = {
            "components": [
                {
                    "type": "application",
                    "name": "app",
                    "version": "1.0",
                    "purl": "pkg:generic/app@1.0",
                    "components": [
                        {
                            "type": "library",
                            "name": "sub-lib",
                            "version": "0.5",
                            "purl": "pkg:pypi/sub-lib@0.5",
                        }
                    ],
                }
            ]
        }
        result = collect_components(sbom)
        assert len(result) == 2

    def test_skips_component_without_purl(self) -> None:
        sbom = {
            "components": [
                {
                    "type": "library",
                    "name": "no-purl",
                    "version": "1.0",
                }
            ]
        }
        result = collect_components(sbom)
        assert len(result) == 0

    def test_returns_component_paths_for_back_insertion(self) -> None:
        sbom = {
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
            ]
        }
        result = collect_components(sbom)
        app_comp = next(c for c in result if c.purl == "pkg:generic/app@1.0")
        assert app_comp.path == ("components", 0)
        sub_comp = next(c for c in result if c.purl == "pkg:pypi/sub@0.5")
        assert sub_comp.path == ("components", 0, "components", 0)

    def test_empty_components_array(self) -> None:
        result = collect_components({"components": []})
        assert result == []


def test_has_subcomponents_true_when_nested_components_present() -> None:
    sbom = {
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
        ]
    }
    result = collect_components(sbom)
    app = next(c for c in result if c.purl == "pkg:generic/app@1.0")
    assert app.has_subcomponents is True


def test_has_subcomponents_false_when_no_nested_components() -> None:
    sbom = {
        "components": [
            {
                "type": "library",
                "name": "lib-a",
                "version": "1.0",
                "purl": "pkg:pypi/lib-a@1.0",
            }
        ]
    }
    result = collect_components(sbom)
    assert result[0].has_subcomponents is False


def test_has_subcomponents_false_when_empty_components_list() -> None:
    sbom = {
        "components": [
            {
                "type": "library",
                "name": "lib-a",
                "version": "1.0",
                "purl": "pkg:pypi/lib-a@1.0",
                "components": [],
            }
        ]
    }
    result = collect_components(sbom)
    assert result[0].has_subcomponents is False


def test_has_subcomponents_false_when_components_not_a_list() -> None:
    sbom = {
        "components": [
            {
                "type": "library",
                "name": "lib-a",
                "version": "1.0",
                "purl": "pkg:pypi/lib-a@1.0",
                "components": "not-a-list",
            }
        ]
    }
    result = collect_components(sbom)
    assert result[0].has_subcomponents is False
