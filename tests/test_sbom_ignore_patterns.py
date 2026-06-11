from __future__ import annotations

import json
from pathlib import Path

import pytest

from purl_resolver.sbom.collector import collect_components
from purl_resolver.sbom.reporter import build_report
from purl_resolver.sbom_enrichment import _component_matches_any_pattern


TEST_SBOM = Path(__file__).parent.parent / ".misc/addictional_materials/sbom_example_missed_references.json"


@pytest.fixture
def sbom_data():
    with open(TEST_SBOM, encoding="utf-8") as f:
        return json.load(f)


def test_ignore_patterns_filter_purl_contains_test(sbom_data):
    ignore_patterns = [
        {"field": "purl", "pattern": "test"},
        {"field": "group", "pattern": "test"},
    ]
    components = collect_components(sbom_data)

    parent = next(c for c in components if c.name == "configure_interfaces-amd64")
    assert _component_matches_any_pattern(sbom_data, parent, ignore_patterns)

    altgraph = next(c for c in components if c.name == "altgraph")
    assert not _component_matches_any_pattern(sbom_data, altgraph, ignore_patterns)

    black = next(c for c in components if c.name == "black")
    assert not _component_matches_any_pattern(sbom_data, black, ignore_patterns)


def test_ignore_patterns_independence_for_nested_components(sbom_data):
    """Parent being ignored must NOT cause children to be ignored."""
    ignore_patterns = [{"field": "purl", "pattern": "test"}]
    components = collect_components(sbom_data)

    matched_names = []
    for comp in components:
        if _component_matches_any_pattern(sbom_data, comp, ignore_patterns):
            matched_names.append(comp.name)

    assert "configure_interfaces-amd64" in matched_names
    assert "altgraph" not in matched_names
    assert "black" not in matched_names
    assert "ptaf-task-manager" not in matched_names
    assert "certifi" not in matched_names
    assert "cffi" not in matched_names


def test_ignore_patterns_no_false_positives(sbom_data):
    ignore_patterns = [{"field": "purl", "pattern": "nonexistent_value_xyz"}]
    components = collect_components(sbom_data)
    for comp in components:
        assert not _component_matches_any_pattern(sbom_data, comp, ignore_patterns)


def test_ignore_patterns_reporter_integration(sbom_data):
    """Verify that running full enrichment pipeline end-to-end with ignore patterns 
    produces correct report including ignored status."""
    from purl_resolver.sbom_enrichment import _component_matches_any_pattern

    ignore_patterns = [{"field": "purl", "pattern": "test"}]
    components = collect_components(sbom_data)

    for comp in components:
        if _component_matches_any_pattern(sbom_data, comp, ignore_patterns):
            comp.ignored = True
            comp.needs_enrichment = False

    report = build_report(components, resolved={})
    
    assert report["summary"]["ignored"] == 1
    ignored_results = [r for r in report["results"] if r["status"] == "ignored"]
    assert len(ignored_results) == 1
    assert "configure_interfaces" in ignored_results[0]["purl"]
