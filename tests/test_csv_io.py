from __future__ import annotations

import json

from purl_resolver.csv_io import detect_delimiter, parse_csv_import, render_csv_export
from purl_resolver.storage.interface import PurlRow


class TestDetectDelimiter:

    def test_semicolon_delimiter(self) -> None:
        assert detect_delimiter("purl;repository_url") == ";"

    def test_comma_delimiter(self) -> None:
        assert detect_delimiter("purl,repository_url") == ","

    def test_prefers_semicolon_over_comma(self) -> None:
        assert detect_delimiter("purl,repo;extra") == ";"

    def test_defaults_to_comma(self) -> None:
        assert detect_delimiter("purl repository_url") == ","


class TestParseCsvImport:

    def test_valid_csv_semicolon(self) -> None:
        csv_text = "purl;repository_url\npkg:pypi/requests;https://github.com/psf/requests\n"
        rows, errors = parse_csv_import(csv_text)
        assert len(rows) == 1
        assert len(errors) == 0
        assert rows[0].purl == "pkg:pypi/requests"
        assert rows[0].repository_url == "https://github.com/psf/requests"

    def test_valid_csv_comma(self) -> None:
        csv_text = "purl,repository_url\npkg:pypi/requests,https://github.com/psf/requests\n"
        rows, errors = parse_csv_import(csv_text)
        assert len(rows) == 1
        assert rows[0].purl == "pkg:pypi/requests"

    def test_missing_columns_returns_error(self) -> None:
        csv_text = "purl\npkg:pypi/requests\n"
        rows, errors = parse_csv_import(csv_text)
        assert len(rows) == 0
        assert len(errors) == 1
        assert "repository_url" in errors[0]["error"]

    def test_empty_purl_returns_error(self) -> None:
        csv_text = "purl;repository_url\n;https://example.com\n"
        rows, errors = parse_csv_import(csv_text)
        assert len(rows) == 0
        assert len(errors) == 1
        assert errors[0]["error"] == "empty purl"

    def test_empty_repository_url_returns_error(self) -> None:
        csv_text = "purl;repository_url\npkg:pypi/test;\n"
        rows, errors = parse_csv_import(csv_text)
        assert len(rows) == 0
        assert len(errors) == 1
        assert errors[0]["error"] == "empty repository_url"

    def test_optional_columns_parsed(self) -> None:
        csv_text = (
            "purl;repository_url;confidence;resolver\n"
            "pkg:pypi/test;https://example.com;high;custom\n"
        )
        rows, errors = parse_csv_import(csv_text)
        assert len(rows) == 1
        assert rows[0].confidence == "high"
        assert rows[0].resolver == "custom"

    def test_jsonb_evidence_parsed(self) -> None:
        csv_text = (
            'purl;repository_url;evidence;warnings\n'
            'pkg:pypi/test;https://example.com;["a","b"];["w1"]\n'
        )
        rows, errors = parse_csv_import(csv_text)
        assert len(rows) == 1
        assert rows[0].evidence == ["a", "b"]
        assert rows[0].warnings == ["w1"]

    def test_bom_stripped_by_utf8_sig_decode(self) -> None:
        raw_csv = "\ufeffpurl;repository_url\npkg:pypi/test;https://example.com\n"
        text = raw_csv.encode("utf-8").decode("utf-8-sig")
        rows, errors = parse_csv_import(text)
        assert len(rows) == 1
        assert rows[0].purl == "pkg:pypi/test"

    def test_no_header_returns_error(self) -> None:
        rows, errors = parse_csv_import("")
        assert len(rows) == 0
        assert len(errors) == 1

    def test_multiple_rows(self) -> None:
        csv_text = (
            "purl;repository_url\n"
            "pkg:pypi/a;https://example.com/a\n"
            "pkg:npm/b;https://example.com/b\n"
            "pkg:pypi/c;https://example.com/c\n"
        )
        rows, errors = parse_csv_import(csv_text)
        assert len(rows) == 3
        assert len(errors) == 0


class TestRenderCsvExport:

    def test_renders_header_and_rows(self) -> None:
        rows = [
            PurlRow(
                purl="pkg:pypi/requests",
                repository_url="https://github.com/psf/requests",
                repository_type="github",
                repository_kind="source_code",
                confidence="high",
                evidence=["homepage"],
                warnings=[],
                version_reference=None,
                resolver="purl2repo",
                resolved_at="2024-01-01",
            ),
        ]
        csv_text = render_csv_export(rows)
        lines = csv_text.strip().split("\n")
        assert len(lines) == 2
        assert "purl" in lines[0]
        assert ";" in lines[0]

    def test_uses_semicolon_delimiter(self) -> None:
        rows = [
            PurlRow(
                purl="pkg:pypi/test",
                repository_url="https://example.com",
                repository_type=None,
                repository_kind=None,
                confidence=None,
            ),
        ]
        csv_text = render_csv_export(rows)
        first_line = csv_text.split("\n")[0]
        assert ";" in first_line
        assert "," not in first_line.split(";")[0]

    def test_jsonb_fields_rendered(self) -> None:
        rows = [
            PurlRow(
                purl="pkg:pypi/test",
                repository_url="https://example.com",
                repository_type=None,
                repository_kind=None,
                confidence=None,
                evidence=["a", "b"],
                warnings=["w1"],
            ),
        ]
        csv_text = render_csv_export(rows)
        data_line = csv_text.strip().split("\n")[1]
        assert '"a"' in data_line
        assert '"w1"' in data_line

    def test_empty_rows(self) -> None:
        csv_text = render_csv_export([])
        lines = csv_text.strip().split("\n")
        assert len(lines) == 1
