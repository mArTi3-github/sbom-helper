from __future__ import annotations

from purl_resolver.sbom.collector import SbomComponent
from purl_resolver.sbom.reporter import build_report
from purl_resolver.schemas import ResolveResponse


class TestBuildReport:
    def test_all_found(self) -> None:
        components = [
            SbomComponent(name="a", version="1", purl="pkg:pypi/a@1", path=("components", 0), needs_enrichment=True),
            SbomComponent(name="b", version="2", purl="pkg:pypi/b@2", path=("components", 1), needs_enrichment=True),
        ]
        resolved = {
            "pkg:pypi/a": ResolveResponse(purl="pkg:pypi/a", repository_url="https://example.com/a"),
            "pkg:pypi/b": ResolveResponse(purl="pkg:pypi/b", repository_url="https://example.com/b"),
        }
        report = build_report(components, resolved)
        assert report["summary"]["total_purls"] == 2
        assert report["summary"]["found"] == 2
        assert report["summary"]["not_found"] == 0
        assert report["summary"]["skipped"] == 0

    def test_partial_results(self) -> None:
        components = [
            SbomComponent(name="a", version="1", purl="pkg:pypi/a@1", path=("components", 0), needs_enrichment=True),
            SbomComponent(name="b", version="2", purl="pkg:pypi/b@2", path=("components", 1), needs_enrichment=True),
        ]
        resolved = {"pkg:pypi/a": ResolveResponse(purl="pkg:pypi/a", repository_url="https://example.com/a")}
        skipped = [{"purl": "pkg:pypi/c@1", "name": "c", "version": "1"}]
        report = build_report(components, resolved, skipped=skipped)
        assert report["summary"]["total_purls"] == 3
        assert report["summary"]["found"] == 1
        assert report["summary"]["not_found"] == 1
        assert report["summary"]["skipped"] == 1

    def test_result_items_have_correct_structure(self) -> None:
        components = [
            SbomComponent(name="a", version="1", purl="pkg:pypi/a@1", path=("components", 0), needs_enrichment=True),
        ]
        resolved = {"pkg:pypi/a": ResolveResponse(purl="pkg:pypi/a", repository_url="https://example.com/a")}
        report = build_report(components, resolved)
        item = report["results"][0]
        assert item["purl"] == "pkg:pypi/a"
        assert item["status"] == "found"
        assert item["repository_url"] == "https://example.com/a"

    def test_not_found_status(self) -> None:
        components = [
            SbomComponent(name="a", version="1", purl="pkg:pypi/a@1", path=("components", 0), needs_enrichment=True),
        ]
        resolved: dict[str, ResolveResponse] = {}
        report = build_report(components, resolved)
        item = report["results"][0]
        assert item["status"] == "not_found"
        assert item["repository_url"] is None

    def test_deduplicates_by_normalized_purl_in_report(self) -> None:
        components = [
            SbomComponent(name="a", version="1", purl="pkg:pypi/a@1", path=("components", 0), needs_enrichment=True),
            SbomComponent(name="a", version="2", purl="pkg:pypi/a@2", path=("components", 1), needs_enrichment=True),
        ]
        resolved = {"pkg:pypi/a": ResolveResponse(purl="pkg:pypi/a", repository_url="https://example.com/a")}
        report = build_report(components, resolved)
        assert len(report["results"]) == 1

    def test_skips_components_without_enrichment_needed(self) -> None:
        components = [
            SbomComponent(name="a", version="1", purl="pkg:pypi/a@1", path=("components", 0), needs_enrichment=False),
            SbomComponent(name="b", version="2", purl="pkg:pypi/b@2", path=("components", 1), needs_enrichment=True),
        ]
        resolved = {"pkg:pypi/b": ResolveResponse(purl="pkg:pypi/b", repository_url="https://example.com/b")}
        report = build_report(components, resolved)
        assert report["summary"]["total_purls"] == 1
        assert report["summary"]["found"] == 1
        assert len(report["results"]) == 1
        assert report["results"][0]["purl"] == "pkg:pypi/b"

    def test_removed_count_in_summary(self) -> None:
        components = [
            SbomComponent(name="a", version="1", purl="pkg:pypi/a@1", path=("components", 0), needs_enrichment=True),
        ]
        resolved = {"pkg:pypi/a": ResolveResponse(purl="pkg:pypi/a", repository_url="https://example.com/a")}
        removed = [{"purl": "pkg:pypi/b@2", "name": "b", "version": "2"}]
        report = build_report(components, resolved, removed=removed)
        assert report["summary"]["removed"] == 1
        assert report["summary"]["found"] == 1

    def test_removed_entries_in_results(self) -> None:
        components = [
            SbomComponent(name="a", version="1", purl="pkg:pypi/a@1", path=("components", 0), needs_enrichment=True),
        ]
        resolved = {"pkg:pypi/a": ResolveResponse(purl="pkg:pypi/a", repository_url="https://example.com/a")}
        removed = [{"purl": "pkg:pypi/b@2", "name": "b", "version": "2"}]
        report = build_report(components, resolved, removed=removed)
        removed_results = [r for r in report["results"] if r["status"] == "removed"]
        assert len(removed_results) == 1
        assert removed_results[0]["purl"] == "pkg:pypi/b@2"
        assert removed_results[0]["name"] == "b"
        assert removed_results[0]["version"] == "2"

    def test_no_removed_when_empty_list(self) -> None:
        components = [
            SbomComponent(name="a", version="1", purl="pkg:pypi/a@1", path=("components", 0), needs_enrichment=True),
        ]
        resolved = {"pkg:pypi/a": ResolveResponse(purl="pkg:pypi/a", repository_url="https://example.com/a")}
        report = build_report(components, resolved, removed=[])
        assert report["summary"]["removed"] == 0
        assert all(r["status"] != "removed" for r in report["results"])

    def test_found_result_includes_found_by_and_resolver(self) -> None:
        from purl_resolver.schemas import ResolveResponse
        components = [
            SbomComponent(name="a", version="1", purl="pkg:pypi/a@1", path=("components", 0), needs_enrichment=True),
        ]
        resolved = {
            "pkg:pypi/a": ResolveResponse(
                purl="pkg:pypi/a",
                repository_url="https://example.com/a",
                found_by="resolver",
                resolver="ecosyste.ms",
            )
        }
        report = build_report(components, resolved)
        item = report["results"][0]
        assert item["found_by"] == "resolver"
        assert item["resolver"] == "ecosyste.ms"

    def test_not_found_result_has_empty_found_by(self) -> None:
        components = [
            SbomComponent(name="a", version="1", purl="pkg:pypi/a@1", path=("components", 0), needs_enrichment=True),
        ]
        resolved: dict[str, ResolveResponse] = {}
        report = build_report(components, resolved)
        item = report["results"][0]
        assert item["found_by"] == ""
        assert item["resolver"] == ""

    def test_no_removed_when_parameter_omitted(self) -> None:
        components = [
            SbomComponent(name="a", version="1", purl="pkg:pypi/a@1", path=("components", 0), needs_enrichment=True),
        ]
        resolved = {"pkg:pypi/a": ResolveResponse(purl="pkg:pypi/a", repository_url="https://example.com/a")}
        report = build_report(components, resolved)
        assert report["summary"]["removed"] == 0


def test_build_report_includes_ignored_components():
    comps = [
        SbomComponent(
            name="pkg-a", version="1.0", purl="pkg:pypi/pkg-a@1.0",
            path=("components", 0), needs_enrichment=False, ignored=True,
        ),
        SbomComponent(
            name="pkg-b", version="2.0", purl="pkg:pypi/pkg-b@2.0",
            path=("components", 1), needs_enrichment=True, ignored=False,
        ),
    ]
    resolved = {}
    report = build_report(comps, resolved)
    assert report["summary"]["ignored"] == 1
    assert report["summary"]["total_purls"] == 2
    statuses = {r["status"] for r in report["results"]}
    assert "ignored" in statuses
    assert "not_found" in statuses
    ignored = [r for r in report["results"] if r["status"] == "ignored"]
    assert ignored[0]["name"] == "pkg-a"
    assert ignored[0]["version"] == "1.0"


def test_build_report_ignored_deduplicates_by_normalized_purl():
    comps = [
        SbomComponent(
            name="pkg-a", version="1.0", purl="pkg:pypi/pkg-a@1.0",
            path=("components", 0), needs_enrichment=False, ignored=True,
        ),
        SbomComponent(
            name="pkg-a", version="1.0", purl="pkg:pypi/pkg-a@1.0",
            path=("components", 1, "components", 0), needs_enrichment=False, ignored=True,
        ),
        SbomComponent(
            name="pkg-b", version="2.0", purl="pkg:pypi/pkg-b@2.0",
            path=("components", 2), needs_enrichment=False, ignored=True,
        ),
    ]
    report = build_report(comps, {})
    assert report["summary"]["ignored"] == 2
    assert len([r for r in report["results"] if r["status"] == "ignored"]) == 2


def test_build_report_ignored_counted_in_total():
    comps = [
        SbomComponent(
            name="pkg-a", version="1.0", purl="pkg:pypi/pkg-a@1.0",
            path=("components", 0), needs_enrichment=False, ignored=True,
        ),
    ]
    resolved = {}
    report = build_report(comps, resolved)
    assert report["summary"]["ignored"] == 1
    assert report["summary"]["total_purls"] == 1
    assert report["summary"]["found"] == 0
    assert report["summary"]["not_found"] == 0
