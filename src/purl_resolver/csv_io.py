from __future__ import annotations

import csv
import io

from .storage.interface import PurlRow, UpsertRow


def parse_csv_import(text: str) -> tuple[list[UpsertRow], list[dict]]:
    reader = csv.DictReader(io.StringIO(text), delimiter=",")

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

        rows.append(UpsertRow(
            purl=purl,
            repository_url=repo,
            resolver=row.get("resolver") or "import-csv",
        ))

    return rows, errors


def render_csv_export(rows: list[PurlRow]) -> str:
    output = io.StringIO()
    writer = csv.writer(output, delimiter=",")
    writer.writerow([
        "purl", "repository_url", "resolver", "resolved_at",
    ])
    for r in rows:
        writer.writerow([
            r.purl,
            r.repository_url,
            r.resolver,
            r.resolved_at,
        ])
    return output.getvalue()
