from __future__ import annotations

from purl_resolver.sbom.collector import SbomComponent
from purl_resolver.sbom.reporter import build_report


class TestBuildReport:
    def test_all_found(self) -> None:
        components = [
            SbomComponent(name="a", version="1", purl="pkg:pypi/a@1", path=("components", 0), needs_enrichment=True),
            SbomComponent(name="b", version="2", purl="pkg:pypi/b@2", path=("components", 1), needs_enrichment=True),
        ]
        resolved = {"pkg:pypi/a": "https://example.com/a", "pkg:pypi/b": "https://example.com/b"}
        report = build_report(components, resolved, skipped=0)
        assert report["summary"]["total_purls"] == 2
        assert report["summary"]["found"] == 2
        assert report["summary"]["not_found"] == 0
        assert report["summary"]["skipped"] == 0

    def test_partial_results(self) -> None:
        components = [
            SbomComponent(name="a", version="1", purl="pkg:pypi/a@1", path=("components", 0), needs_enrichment=True),
            SbomComponent(name="b", version="2", purl="pkg:pypi/b@2", path=("components", 1), needs_enrichment=True),
        ]
        resolved = {"pkg:pypi/a": "https://example.com/a"}
        report = build_report(components, resolved, skipped=1)
        assert report["summary"]["total_purls"] == 2
        assert report["summary"]["found"] == 1
        assert report["summary"]["not_found"] == 1
        assert report["summary"]["skipped"] == 1

    def test_result_items_have_correct_structure(self) -> None:
        components = [
            SbomComponent(name="a", version="1", purl="pkg:pypi/a@1", path=("components", 0), needs_enrichment=True),
        ]
        resolved = {"pkg:pypi/a": "https://example.com/a"}
        report = build_report(components, resolved, skipped=0)
        item = report["results"][0]
        assert item["purl"] == "pkg:pypi/a"
        assert item["status"] == "found"
        assert item["repository_url"] == "https://example.com/a"

    def test_not_found_status(self) -> None:
        components = [
            SbomComponent(name="a", version="1", purl="pkg:pypi/a@1", path=("components", 0), needs_enrichment=True),
        ]
        resolved: dict[str, str] = {}
        report = build_report(components, resolved, skipped=0)
        item = report["results"][0]
        assert item["status"] == "not_found"
        assert item["repository_url"] is None

    def test_deduplicates_by_normalized_purl_in_report(self) -> None:
        components = [
            SbomComponent(name="a", version="1", purl="pkg:pypi/a@1", path=("components", 0), needs_enrichment=True),
            SbomComponent(name="a", version="2", purl="pkg:pypi/a@2", path=("components", 1), needs_enrichment=True),
        ]
        resolved = {"pkg:pypi/a": "https://example.com/a"}
        report = build_report(components, resolved, skipped=0)
        assert len(report["results"]) == 1

    def test_skips_components_without_enrichment_needed(self) -> None:
        components = [
            SbomComponent(name="a", version="1", purl="pkg:pypi/a@1", path=("components", 0), needs_enrichment=False),
            SbomComponent(name="b", version="2", purl="pkg:pypi/b@2", path=("components", 1), needs_enrichment=True),
        ]
        resolved = {"pkg:pypi/b": "https://example.com/b"}
        report = build_report(components, resolved, skipped=0)
        assert report["summary"]["total_purls"] == 1
        assert report["summary"]["found"] == 1
        assert len(report["results"]) == 1
        assert report["results"][0]["purl"] == "pkg:pypi/b"

    def test_removed_count_in_summary(self) -> None:
        components = [
            SbomComponent(name="a", version="1", purl="pkg:pypi/a@1", path=("components", 0), needs_enrichment=True),
        ]
        resolved = {"pkg:pypi/a": "https://example.com/a"}
        removed = [{"purl": "pkg:pypi/b@2", "name": "b", "version": "2"}]
        report = build_report(components, resolved, skipped=0, removed=removed)
        assert report["summary"]["removed"] == 1
        assert report["summary"]["found"] == 1

    def test_removed_entries_in_results(self) -> None:
        components = [
            SbomComponent(name="a", version="1", purl="pkg:pypi/a@1", path=("components", 0), needs_enrichment=True),
        ]
        resolved = {"pkg:pypi/a": "https://example.com/a"}
        removed = [{"purl": "pkg:pypi/b@2", "name": "b", "version": "2"}]
        report = build_report(components, resolved, skipped=0, removed=removed)
        removed_results = [r for r in report["results"] if r["status"] == "removed"]
        assert len(removed_results) == 1
        assert removed_results[0]["purl"] == "pkg:pypi/b@2"
        assert removed_results[0]["name"] == "b"
        assert removed_results[0]["version"] == "2"

    def test_no_removed_when_empty_list(self) -> None:
        components = [
            SbomComponent(name="a", version="1", purl="pkg:pypi/a@1", path=("components", 0), needs_enrichment=True),
        ]
        resolved = {"pkg:pypi/a": "https://example.com/a"}
        report = build_report(components, resolved, skipped=0, removed=[])
        assert report["summary"]["removed"] == 0
        assert all(r["status"] != "removed" for r in report["results"])

    def test_no_removed_when_parameter_omitted(self) -> None:
        components = [
            SbomComponent(name="a", version="1", purl="pkg:pypi/a@1", path=("components", 0), needs_enrichment=True),
        ]
        resolved = {"pkg:pypi/a": "https://example.com/a"}
        report = build_report(components, resolved, skipped=0)
        assert report["summary"]["removed"] == 0