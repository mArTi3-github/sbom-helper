from __future__ import annotations

import csv
import gzip
import os
import shutil
import stat
import subprocess
import uuid
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_BACKUP = REPO_ROOT / "scripts" / "db_backup.sh"
SCRIPT_RESTORE = REPO_ROOT / "scripts" / "db_restore.sh"
SCHEMA = REPO_ROOT / "src" / "purl_resolver" / "storage" / "schema.sql"

TEST_DB = f"sbom_backup_test_{uuid.uuid4().hex[:8]}"

SOURCE_ROWS = [
    ("pkg:pypi/alpha", "https://github.com/example/alpha", "purl2repo", "2026-01-01T00:00:00+00"),
    ("pkg:pypi/beta", "https://github.com/example/beta", "import-csv", "2026-01-02T03:04:05+00"),
]

ARCHIVE_HEADER = (
    "purl",
    "version",
    "match_type",
    "reason",
    "archive_url",
    "archive_url_commit",
    "matched_ref",
    "matched_ref_type",
    "matched_version",
    "repository_url",
    "resolver",
    "resolved_at",
)

ARCHIVE_ROWS = [
    (
        "pkg:pypi/alpha",
        "1.0.0",
        "exact",
        None,
        "https://github.com/example/alpha/archive/refs/tags/v1.0.0.tar.gz",
        "https://github.com/example/alpha/archive/abc123.tar.gz",
        "refs/tags/v1.0.0",
        "tag",
        "1.0.0",
        "https://github.com/example/alpha",
        "git-ls-remote",
        "2026-01-03T04:05:06+00",
    ),
]


def _docker_db_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        result = subprocess.run(
            ["docker", "compose", "ps", "--status", "running", "--services"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and "db" in result.stdout.split()


def _psql(database: str, sql: str, extra: list[str] | None = None):
    cmd = [
        "docker", "compose", "exec", "-T", "db",
        "psql", "-U", "sbom", "-d", database, "-v", "ON_ERROR_STOP=1",
        *(extra or []),
        "-c", sql,
    ]
    return subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, check=True)


def _apply_schema(database: str) -> None:
    cmd = [
        "docker", "compose", "exec", "-T", "db",
        "psql", "-U", "sbom", "-d", database, "-v", "ON_ERROR_STOP=1",
    ]
    subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        input=SCHEMA.read_text(),
        capture_output=True,
        text=True,
        check=True,
    )


def _seed(database: str, rows=SOURCE_ROWS) -> None:
    values = ", ".join(
        f"('{purl}', '{repo}', '{resolver}', '{resolved_at}')"
        for purl, repo, resolver, resolved_at in rows
    )
    _psql(
        database,
        "TRUNCATE resolved_purls, purl_source_archives; "
        "INSERT INTO resolved_purls (purl, repository_url, resolver, resolved_at) "
        f"VALUES {values}",
    )


def _sql_literal(value: object) -> str:
    if value is None:
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def _write_archive_rows(database: str, rows=ARCHIVE_ROWS) -> None:
    values = ", ".join(
        "(" + ", ".join(_sql_literal(value) for value in row) + ")" for row in rows
    )
    _psql(
        database,
        "TRUNCATE purl_source_archives; "
        f"INSERT INTO purl_source_archives ({', '.join(ARCHIVE_HEADER)}) "
        f"VALUES {values}",
    )


def _fetch_rows(database: str) -> dict[str, str]:
    result = _psql(
        database,
        "SELECT purl, repository_url FROM resolved_purls ORDER BY purl",
        extra=["-tA", "-F", "|"],
    )
    rows: dict[str, str] = {}
    for line in result.stdout.strip().splitlines():
        if line:
            purl, repo = line.split("|", 1)
            rows[purl] = repo
    return rows


def _run_script(script: Path, *args: str, env: dict[str, str] | None = None, **kwargs):
    full_env = {**os.environ, **(env or {})}
    return subprocess.run(
        [str(script), *args],
        cwd=REPO_ROOT,
        env=full_env,
        capture_output=True,
        text=True,
        **kwargs,
    )


def _read_backup(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with gzip.open(path, "rt", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def _write_backup(
    path: Path,
    rows: list[tuple[str, str, str, str]],
    header: tuple[str, ...] = ("purl", "repository_url", "resolver", "resolved_at"),
) -> None:
    with gzip.open(path, "wt", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def _staging_table_count(database: str) -> int:
    result = _psql(
        database,
        "SELECT count(*) FROM pg_tables "
        "WHERE schemaname = 'public' AND tablename LIKE 'resolved_purls_import%'",
        extra=["-tA"],
    )
    return int(result.stdout.strip())


@pytest.fixture(scope="module")
def test_db():
    if not _docker_db_available():
        pytest.skip("docker compose 'db' service is not running")

    _psql("postgres", f'CREATE DATABASE "{TEST_DB}"')
    _apply_schema(TEST_DB)
    try:
        yield TEST_DB
    finally:
        _psql(
            "postgres",
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            f"WHERE datname = '{TEST_DB}'",
        )
        _psql("postgres", f'DROP DATABASE IF EXISTS "{TEST_DB}"')


def test_backup_creates_csv_gz_with_all_columns(test_db, tmp_path):
    _seed(test_db)
    out = tmp_path / "out.csv.gz"

    result = _run_script(SCRIPT_BACKUP, "-o", str(out), env={"DB_NAME": test_db})

    assert result.returncode == 0, result.stderr
    assert out.exists()
    fieldnames, rows = _read_backup(out)
    assert fieldnames == ["purl", "repository_url", "resolver", "resolved_at"]
    by_purl = {row["purl"]: row for row in rows}
    assert set(by_purl) == {"pkg:pypi/alpha", "pkg:pypi/beta"}
    assert by_purl["pkg:pypi/alpha"]["resolver"] == "purl2repo"
    assert by_purl["pkg:pypi/beta"]["resolved_at"].startswith("2026-01-02 03:04:05")
    assert stat.S_IMODE(out.stat().st_mode) == 0o600
    assert "rows: 2" in result.stdout


def test_backup_exports_source_archives_file(test_db, tmp_path):
    _seed(test_db)
    _write_archive_rows(test_db)
    out = tmp_path / "out.csv.gz"
    archive = tmp_path / "out.source_archives.csv.gz"

    result = _run_script(
        SCRIPT_BACKUP,
        "-o",
        str(out),
        env={"DB_NAME": test_db, "BACKUP_DIR": str(tmp_path)},
    )

    assert result.returncode == 0, result.stderr
    assert out.exists()
    assert archive.exists()
    assert stat.S_IMODE(out.stat().st_mode) == 0o600
    assert stat.S_IMODE(archive.stat().st_mode) == 0o600

    fieldnames, rows = _read_backup(archive)
    assert fieldnames == list(ARCHIVE_HEADER)
    assert len(rows) == 1
    expected = dict(zip(ARCHIVE_HEADER, ARCHIVE_ROWS[0]))
    for column in ARCHIVE_HEADER:
        if column == "resolved_at":
            assert rows[0][column].startswith("2026-01-03 04:05:06")
        else:
            assert rows[0][column] == (expected[column] or "")

    assert "archives rows: 1" in result.stdout
    assert str(out) in result.stdout
    assert str(archive) in result.stdout


def test_backup_default_names_share_timestamp_suffix(test_db, tmp_path):
    _seed(test_db)
    _write_archive_rows(test_db)

    result = _run_script(
        SCRIPT_BACKUP,
        env={"DB_NAME": test_db, "BACKUP_DIR": str(tmp_path)},
    )

    assert result.returncode == 0, result.stderr
    purl_files = sorted(tmp_path.glob("sbom_purls_*.csv.gz"))
    archive_files = sorted(tmp_path.glob("sbom_source_archives_*.csv.gz"))
    assert len(purl_files) == 1
    assert len(archive_files) == 1
    suffix = purl_files[0].name[len("sbom_purls_") : -len(".csv.gz")]
    assert suffix
    assert archive_files[0].name == f"sbom_source_archives_{suffix}.csv.gz"


def test_backup_keep_removes_older_file_pairs(test_db, tmp_path):
    _seed(test_db)
    _write_archive_rows(test_db)
    old_purl = tmp_path / "sbom_purls_20000101-000000.csv.gz"
    old_archive = tmp_path / "sbom_source_archives_20000101-000000.csv.gz"
    old_purl.write_bytes(b"old")
    old_archive.write_bytes(b"old")
    out = tmp_path / "sbom_purls_20990101-000000.csv.gz"
    archive = tmp_path / "sbom_purls_20990101-000000.source_archives.csv.gz"

    result = _run_script(
        SCRIPT_BACKUP,
        "-o",
        str(out),
        "--keep",
        "1",
        env={"DB_NAME": test_db, "BACKUP_DIR": str(tmp_path)},
    )

    assert result.returncode == 0, result.stderr
    assert out.exists()
    assert archive.exists()
    assert not old_purl.exists()
    assert not old_archive.exists()


def test_merge_keeps_existing_rows_and_replace_overwrites(test_db, tmp_path):
    _seed(test_db)
    out = tmp_path / "out.csv.gz"
    backup = _run_script(SCRIPT_BACKUP, "-o", str(out), env={"DB_NAME": test_db})
    assert backup.returncode == 0, backup.stderr

    _psql(
        test_db,
        "UPDATE resolved_purls SET repository_url = 'https://target/alpha' "
        "WHERE purl = 'pkg:pypi/alpha'; "
        "DELETE FROM resolved_purls WHERE purl = 'pkg:pypi/beta'; "
        "INSERT INTO resolved_purls (purl, repository_url, resolver, resolved_at) "
        "VALUES ('pkg:pypi/gamma', 'https://target/gamma', 'import-manual', NOW())",
    )

    merge = _run_script(SCRIPT_RESTORE, str(out), env={"DB_NAME": test_db})
    assert merge.returncode == 0, merge.stderr
    assert "mode: merge" in merge.stdout
    assert "inserted: 1" in merge.stdout
    assert "skipped: 1" in merge.stdout
    assert _fetch_rows(test_db) == {
        "pkg:pypi/alpha": "https://target/alpha",
        "pkg:pypi/beta": "https://github.com/example/beta",
        "pkg:pypi/gamma": "https://target/gamma",
    }

    refused = _run_script(
        SCRIPT_RESTORE,
        str(out),
        "--mode",
        "replace",
        env={"DB_NAME": test_db},
        stdin=subprocess.DEVNULL,
    )
    assert refused.returncode != 0
    assert "mode: replace" in refused.stdout
    assert _fetch_rows(test_db)["pkg:pypi/gamma"] == "https://target/gamma"

    replace = _run_script(
        SCRIPT_RESTORE,
        str(out),
        "--mode",
        "replace",
        "--yes",
        env={"DB_NAME": test_db},
    )
    assert replace.returncode == 0, replace.stderr
    assert "mode: replace" in replace.stdout
    assert _fetch_rows(test_db) == {
        "pkg:pypi/alpha": "https://github.com/example/alpha",
        "pkg:pypi/beta": "https://github.com/example/beta",
    }


def test_corrupt_backup_fails_without_leaving_staging_table(test_db, tmp_path):
    bad = tmp_path / "bad.csv.gz"
    bad.write_bytes(b"not gzip")

    result = _run_script(SCRIPT_RESTORE, str(bad), env={"DB_NAME": test_db})

    assert result.returncode != 0
    assert _staging_table_count(test_db) == 0


def test_merge_handles_duplicate_purls(test_db, tmp_path):
    _psql(test_db, "TRUNCATE resolved_purls")
    path = tmp_path / "duplicates.csv.gz"
    _write_backup(
        path,
        [
            ("pkg:pypi/alpha", "https://a/1", "r", "2026-01-01 00:00:00+00"),
            ("pkg:pypi/alpha", "https://a/2", "r", "2026-01-01 00:00:00+00"),
            ("pkg:pypi/beta", "https://b", "r", "2026-01-01 00:00:00+00"),
        ],
    )

    result = _run_script(SCRIPT_RESTORE, str(path), env={"DB_NAME": test_db})

    assert result.returncode == 0, result.stderr
    assert "inserted: 2" in result.stdout
    assert "skipped: 1" in result.stdout
    assert "total: 3" in result.stdout
    assert set(_fetch_rows(test_db)) == {"pkg:pypi/alpha", "pkg:pypi/beta"}


def test_wrong_header_is_rejected_without_changing_data(test_db, tmp_path):
    _seed(test_db)
    path = tmp_path / "wrong-header.csv.gz"
    _write_backup(
        path,
        [("https://a", "pkg:pypi/alpha", "r", "2026-01-01 00:00:00+00")],
        header=("repository_url", "purl", "resolver", "resolved_at"),
    )

    result = _run_script(SCRIPT_RESTORE, str(path), env={"DB_NAME": test_db})

    assert result.returncode != 0
    assert _fetch_rows(test_db) == {
        "pkg:pypi/alpha": "https://github.com/example/alpha",
        "pkg:pypi/beta": "https://github.com/example/beta",
    }


def test_replace_refuses_empty_backup(test_db, tmp_path):
    _seed(test_db)
    path = tmp_path / "empty.csv.gz"
    _write_backup(path, [])

    result = _run_script(
        SCRIPT_RESTORE,
        str(path),
        "--mode",
        "replace",
        "--yes",
        env={"DB_NAME": test_db},
    )

    assert result.returncode != 0
    assert _fetch_rows(test_db) == {
        "pkg:pypi/alpha": "https://github.com/example/alpha",
        "pkg:pypi/beta": "https://github.com/example/beta",
    }


def test_replace_handles_duplicate_purls(test_db, tmp_path):
    _psql(test_db, "TRUNCATE resolved_purls")
    path = tmp_path / "duplicates.csv.gz"
    _write_backup(
        path,
        [
            ("pkg:pypi/alpha", "https://old", "r", "2026-01-01 00:00:00+00"),
            ("pkg:pypi/alpha", "https://new", "r", "2026-02-01 00:00:00+00"),
            ("pkg:pypi/beta", "https://b", "r", "2026-01-01 00:00:00+00"),
        ],
    )

    result = _run_script(
        SCRIPT_RESTORE,
        str(path),
        "--mode",
        "replace",
        "--yes",
        env={"DB_NAME": test_db},
    )

    assert result.returncode == 0, result.stderr
    assert _fetch_rows(test_db) == {
        "pkg:pypi/alpha": "https://new",
        "pkg:pypi/beta": "https://b",
    }


def test_scripts_fail_when_db_service_is_not_running(test_db, tmp_path):
    out = tmp_path / "out.csv.gz"
    backup = _run_script(
        SCRIPT_BACKUP,
        "-o",
        str(out),
        env={"DB_NAME": test_db, "DB_SERVICE": "missing-service"},
    )
    assert backup.returncode != 0
    assert not out.exists()

    path = tmp_path / "valid.csv.gz"
    _write_backup(path, SOURCE_ROWS)
    restore = _run_script(
        SCRIPT_RESTORE,
        str(path),
        env={"DB_NAME": test_db, "DB_SERVICE": "missing-service"},
    )
    assert restore.returncode != 0


def test_backup_keep_removes_old_files(test_db, tmp_path):
    _seed(test_db)
    old = tmp_path / "sbom_purls_20000101-000000.csv.gz"
    old.write_bytes(b"old")
    out = tmp_path / "sbom_purls_20990101-000000.csv.gz"

    result = _run_script(
        SCRIPT_BACKUP,
        "-o",
        str(out),
        "--keep",
        "1",
        env={"DB_NAME": test_db, "BACKUP_DIR": str(tmp_path)},
    )

    assert result.returncode == 0, result.stderr
    assert out.exists()
    assert not old.exists()

    invalid = _run_script(
        SCRIPT_BACKUP,
        "--keep",
        "0",
        env={"DB_NAME": test_db, "BACKUP_DIR": str(tmp_path)},
    )
    assert invalid.returncode != 0
