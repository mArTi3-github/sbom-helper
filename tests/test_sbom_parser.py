from __future__ import annotations

import pytest

from purl_resolver.sbom.parser import CycloneDXParser, SbomParseError


class TestCycloneDXParser:
    def test_parse_valid_cyclonedx(self) -> None:
        raw = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "metadata": {
                "timestamp": "2024-01-01T00:00:00",
                "component": {"type": "application", "name": "app", "version": "1.0"},
            },
        }
        result = CycloneDXParser.parse(raw)
        assert result["bomFormat"] == "CycloneDX"
        assert result["specVersion"] == "1.6"

    def test_rejects_missing_bom_format(self) -> None:
        with pytest.raises(SbomParseError, match="bomFormat"):
            CycloneDXParser.parse({"specVersion": "1.6"})

    def test_rejects_wrong_bom_format(self) -> None:
        with pytest.raises(SbomParseError, match="bomFormat"):
            CycloneDXParser.parse({"bomFormat": "SPDX", "specVersion": "1.6"})

    def test_rejects_missing_spec_version(self) -> None:
        with pytest.raises(SbomParseError, match="specVersion"):
            CycloneDXParser.parse({"bomFormat": "CycloneDX"})

    def test_rejects_unsupported_spec_version(self) -> None:
        with pytest.raises(SbomParseError, match="specVersion"):
            CycloneDXParser.parse({"bomFormat": "CycloneDX", "specVersion": "1.5"})

    def test_allows_extra_fields(self) -> None:
        raw = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "serialNumber": "urn:uuid:abc",
            "version": 2,
            "metadata": {
                "timestamp": "2026-03-31T17:42:21.497772+00:00",
                "component": {"type": "file", "name": "pkg", "version": "1.0"},
            },
            "components": [],
        }
        result = CycloneDXParser.parse(raw)
        assert result["bomFormat"] == "CycloneDX"

    def test_rejects_non_dict_input(self) -> None:
        with pytest.raises(SbomParseError, match="JSON object"):
            CycloneDXParser.parse([])
