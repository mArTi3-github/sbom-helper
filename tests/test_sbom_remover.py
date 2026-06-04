from __future__ import annotations

from purl_resolver.sbom.collector import SbomComponent
from purl_resolver.sbom.remover import remove_unresolved_components


def _comp(
    name: str,
    purl: str,
    path: tuple,
    version: str = "1.0",
    needs_enrichment: bool = True,
    has_subcomponents: bool = False,
) -> SbomComponent:
    return SbomComponent(
        name=name,
        version=version,
        purl=purl,
        path=path,
        needs_enrichment=needs_enrichment,
        has_subcomponents=has_subcomponents,
    )


class TestRemoveUnresolvedComponents:
    def test_removes_unresolved_without_subcomponents(self) -> None:
        sbom = {
            "components": [
                {"type": "library", "name": "a", "version": "1.0", "purl": "pkg:pypi/a@1.0"},
                {"type": "library", "name": "b", "version": "2.0", "purl": "pkg:pypi/b@2.0"},
            ]
        }
        components = [
            _comp("a", "pkg:pypi/a@1.0", ("components", 0)),
            _comp("b", "pkg:pypi/b@2.0", ("components", 1)),
        ]
        resolved = {"pkg:pypi/a": "https://example.com/a"}
        removed = remove_unresolved_components(sbom, components, resolved)
        assert len(sbom["components"]) == 1
        assert sbom["components"][0]["name"] == "a"
        assert len(removed) == 1
        assert removed[0]["purl"] == "pkg:pypi/b@2.0"

    def test_keeps_unresolved_with_subcomponents(self) -> None:
        sbom = {
            "components": [
                {
                    "type": "application",
                    "name": "parent",
                    "version": "1.0",
                    "purl": "pkg:generic/parent@1.0",
                    "components": [
                        {"type": "library", "name": "child", "version": "1.0", "purl": "pkg:pypi/child@1.0"},
                    ],
                }
            ]
        }
        components = [
            _comp("parent", "pkg:generic/parent@1.0", ("components", 0), has_subcomponents=True),
            _comp("child", "pkg:pypi/child@1.0", ("components", 0, "components", 0)),
        ]
        resolved: dict[str, str] = {}
        removed = remove_unresolved_components(sbom, components, resolved)
        assert len(sbom["components"]) == 1
        assert sbom["components"][0]["name"] == "parent"
        assert len(removed) == 0

    def test_removes_child_but_keeps_parent_with_subcomponents(self) -> None:
        sbom = {
            "components": [
                {
                    "type": "application",
                    "name": "parent",
                    "version": "1.0",
                    "purl": "pkg:generic/parent@1.0",
                    "components": [
                        {"type": "library", "name": "resolved-child", "version": "1.0", "purl": "pkg:pypi/rc@1.0"},
                        {"type": "library", "name": "unresolved-child", "version": "1.0", "purl": "pkg:pypi/uc@1.0"},
                    ],
                }
            ]
        }
        components = [
            _comp("parent", "pkg:generic/parent@1.0", ("components", 0), has_subcomponents=True),
            _comp("resolved-child", "pkg:pypi/rc@1.0", ("components", 0, "components", 0)),
            _comp("unresolved-child", "pkg:pypi/uc@1.0", ("components", 0, "components", 1)),
        ]
        resolved = {"pkg:pypi/rc": "https://example.com/rc"}
        removed = remove_unresolved_components(sbom, components, resolved)
        assert len(sbom["components"]) == 1
        assert sbom["components"][0]["name"] == "parent"
        assert len(sbom["components"][0]["components"]) == 1
        assert sbom["components"][0]["components"][0]["name"] == "resolved-child"
        assert len(removed) == 1
        assert removed[0]["purl"] == "pkg:pypi/uc@1.0"

    def test_no_removal_when_all_resolved(self) -> None:
        sbom = {
            "components": [
                {"type": "library", "name": "a", "version": "1.0", "purl": "pkg:pypi/a@1.0"},
            ]
        }
        components = [
            _comp("a", "pkg:pypi/a@1.0", ("components", 0)),
        ]
        resolved = {"pkg:pypi/a": "https://example.com/a"}
        removed = remove_unresolved_components(sbom, components, resolved)
        assert len(sbom["components"]) == 1
        assert len(removed) == 0

    def test_no_removal_when_enrichment_not_needed(self) -> None:
        sbom = {
            "components": [
                {"type": "library", "name": "a", "version": "1.0", "purl": "pkg:pypi/a@1.0",
                 "externalReferences": [{"type": "vcs", "url": "https://example.com/a"}]},
            ]
        }
        components = [
            _comp("a", "pkg:pypi/a@1.0", ("components", 0), needs_enrichment=False),
        ]
        resolved: dict[str, str] = {}
        removed = remove_unresolved_components(sbom, components, resolved)
        assert len(sbom["components"]) == 1
        assert len(removed) == 0

    def test_removed_list_contains_name_and_version(self) -> None:
        sbom = {
            "components": [
                {"type": "library", "name": "special", "version": "3.2.1", "purl": "pkg:pypi/special@3.2.1"},
            ]
        }
        components = [
            _comp("special", "pkg:pypi/special@3.2.1", ("components", 0), version="3.2.1"),
        ]
        resolved: dict[str, str] = {}
        removed = remove_unresolved_components(sbom, components, resolved)
        assert removed[0] == {"purl": "pkg:pypi/special@3.2.1", "name": "special", "version": "3.2.1"}

    def test_empty_components_list(self) -> None:
        sbom = {"components": []}
        components: list[SbomComponent] = []
        resolved: dict[str, str] = {}
        removed = remove_unresolved_components(sbom, components, resolved)
        assert removed == []
        assert sbom["components"] == []
