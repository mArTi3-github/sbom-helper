from __future__ import annotations

import csv
import io
import json

from .storage.interface import PurlRow, UpsertRow


def detect_delimiter(text: str) -> str:
    first_line = text.split("\n", 1)[0]
    if ";" in first_line:
        return ";"
    return ","


def parse_csv_import(text: str) -> tuple[list[UpsertRow], list[dict]]:
    delimiter = detect_delimiter(text)
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)

    if reader.fieldnames is None or not reader.fieldnames:
        return [], [{"row": 1, "error": "CSV has no header row"}]

    if "purl" not in reader.fieldnames or "repository_url" not in reader.fieldnames:
        return [], [{"row": 1, "error": "CSV must contain 'purl' and 'repository_url' columns"}]

    rows: list[UpsertRow] = []
    errors: list[dict] = []
    row_num = 1

    for row in reader:
        row_num += 1
        purl = (row.get("purl") or "").strip()
        repo = (row.get("repository_url") or "").strip()

        if not purl:
            errors.append({"row": row_num, "error": "empty purl"})
            continue
        if not repo:
            errors.append({"row": row_num, "error": "empty repository_url"})
            continue

        evidence = _parse_jsonb_field(row.get("evidence"))
        warnings = _parse_jsonb_field(row.get("warnings"))

        rows.append(UpsertRow(
            purl=purl,
            repository_url=repo,
            repository_type=row.get("repository_type") or None,
            repository_kind=row.get("repository_kind") or None,
            confidence=row.get("confidence") or None,
            evidence=evidence,
            warnings=warnings,
            version_reference=row.get("version_reference") or None,
            resolver=row.get("resolver") or "purl2repo",
        ))

    return rows, errors


def _parse_jsonb_field(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    except (json.JSONDecodeError, TypeError):
        pass
    return []


def render_csv_export(rows: list[PurlRow]) -> str:
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow([
        "purl", "repository_url", "repository_type", "repository_kind",
        "confidence", "evidence", "warnings", "version_reference",
        "resolver", "resolved_at",
    ])
    for r in rows:
        writer.writerow([
            r.purl,
            r.repository_url,
            r.repository_type or "",
            r.repository_kind or "",
            r.confidence or "",
            json.dumps(r.evidence),
            json.dumps(r.warnings),
            r.version_reference or "",
            r.resolver,
            r.resolved_at,
        ])
    return output.getvalue()
