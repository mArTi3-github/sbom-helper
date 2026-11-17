#!/usr/bin/env bash
set -euo pipefail

# ------------------------------------------------------------------
# sbom-helper database restore script
# Restores one or both CSV.gz backups produced by scripts/db_backup.sh:
#   - resolved_purls.csv.gz       (purl, repository_url, ...)
#   - source archives.csv.gz      (purl, version, match_type, ...)
# The table is detected from the exact CSV header, so files may be
# passed in any order. Default mode is "merge": existing rows win,
# only missing PURLs are added.
# ------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INVOCATION_DIR="$(pwd)"
cd "$SCRIPT_DIR"

umask 077

COMPOSE_FILES=("-f" "docker-compose.yml")
DB_SERVICE="${DB_SERVICE:-db}"
DB_USER="${DB_USER:-sbom}"
DB_NAME="${DB_NAME:-sbom}"

PURLS_TABLE="resolved_purls"
ARCHIVES_TABLE="purl_source_archives"
PURLS_HEADER="purl,repository_url,resolver,resolved_at"
ARCHIVES_HEADER="purl,version,match_type,reason,archive_url,archive_url_commit,matched_ref,matched_ref_type,matched_version,repository_url,resolver,resolved_at"
PURLS_COLUMNS="purl, repository_url, resolver, resolved_at"
ARCHIVES_COLUMNS="purl, version, match_type, reason, archive_url, archive_url_commit, matched_ref, matched_ref_type, matched_version, repository_url, resolver, resolved_at"

MODE="merge"
ASSUME_YES=false
FILES=()

ts()   { date '+%Y-%m-%d %H:%M:%S'; }
log()  { printf "[restore %s] %s\n" "$(ts)" "$*"; }
error(){ printf "[restore %s] ERROR: %s\n" "$(ts)" "$*" >&2; }

usage() {
  cat <<'EOF'
Usage: ./scripts/db_restore.sh FILE [FILE] [OPTIONS]

Options:
      --mode merge|replace  Restore mode (default: merge)
      --yes                 Do not ask for confirmation in replace mode
  -h, --help                Show this help

Files:
  Pass the PURL mapping backup, the source archive backup, or both (in any
  order). The target table is detected from the exact CSV header, so
  "sbom_purls_<UTC>.csv.gz" and "sbom_source_archives_<UTC>.csv.gz" can be
  restored in a single invocation. Old backups containing only the PURL
  mapping file keep working.

Modes:
  merge    Add missing PURLs; existing rows in the target database are kept.
  replace  Replace the whole table with the backup contents. Rows missing
           from the backup are deleted. Applied independently per table.

Environment:
  DB_SERVICE  Docker Compose service name (default: db)
  DB_USER     PostgreSQL user (default: sbom)
  DB_NAME     Database name (default: sbom)
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --mode)
      [ $# -ge 2 ] || { error "missing value for $1"; exit 1; }
      MODE="$2"
      shift 2
      ;;
    --yes|-y)
      ASSUME_YES=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    -*)
      error "unknown argument: $1"
      usage >&2
      exit 1
      ;;
    *)
      FILES+=("$1")
      shift
      ;;
  esac
done

if [ "${#FILES[@]}" -eq 0 ]; then
  error "backup file is required"
  usage >&2
  exit 1
fi

if [ "${#FILES[@]}" -gt 2 ]; then
  error "at most two backup files are supported (purl mapping and source archives)"
  exit 1
fi

if [ "$MODE" != "merge" ] && [ "$MODE" != "replace" ]; then
  error "--mode must be 'merge' or 'replace'"
  exit 1
fi

for index in "${!FILES[@]}"; do
  if [[ "${FILES[$index]}" != /* ]]; then
    FILES[$index]="$INVOCATION_DIR/${FILES[$index]}"
  fi
  [ -f "${FILES[$index]}" ] && [ -r "${FILES[$index]}" ] \
    || { error "backup file not found or not readable: ${FILES[$index]}"; exit 1; }
done

read_header() {
  local file="$1" header
  if ! gzip -t "$file" 2>/dev/null; then
    return 1
  fi
  header="$( set +o pipefail; gunzip -c "$file" | head -n 1 )"
  header="${header%$'\r'}"
  header="${header#$'\xEF\xBB\xBF'}"
  printf '%s' "$header"
}

PURLS_FILE=""
ARCHIVES_FILE=""
for file in "${FILES[@]}"; do
  if ! header="$(read_header "$file")"; then
    error "cannot read backup file (not a valid gzip stream): $file"
    exit 1
  fi
  case "$header" in
    "$PURLS_HEADER")
      table="$PURLS_TABLE"
      ;;
    "$ARCHIVES_HEADER")
      table="$ARCHIVES_TABLE"
      ;;
    *)
      error "invalid backup header in $file: got '$header'"
      error "expected '$PURLS_HEADER'"
      error "     or '$ARCHIVES_HEADER'"
      exit 1
      ;;
  esac

  if [ "$table" = "$PURLS_TABLE" ]; then
    if [ -n "$PURLS_FILE" ]; then
      error "duplicate $PURLS_TABLE backup files: $PURLS_FILE and $file"
      exit 1
    fi
    PURLS_FILE="$file"
  else
    if [ -n "$ARCHIVES_FILE" ]; then
      error "duplicate $ARCHIVES_TABLE backup files: $ARCHIVES_FILE and $file"
      exit 1
    fi
    ARCHIVES_FILE="$file"
  fi
done

command -v docker >/dev/null 2>&1 || { error "docker is not installed"; exit 1; }
command -v gzip >/dev/null 2>&1 || { error "gzip is not installed"; exit 1; }

if ! docker compose "${COMPOSE_FILES[@]}" ps --status running --services | grep -qx "$DB_SERVICE"; then
  error "service '$DB_SERVICE' is not running (try: docker compose up -d $DB_SERVICE)"
  exit 1
fi

db_psql() {
  docker compose "${COMPOSE_FILES[@]}" exec -T -e PGTZ=UTC "$DB_SERVICE" \
    psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 -q "$@"
}

log "mode: $MODE"
[ -n "$PURLS_FILE" ] && log "file: $PURLS_FILE (table: $PURLS_TABLE)"
[ -n "$ARCHIVES_FILE" ] && log "file: $ARCHIVES_FILE (table: $ARCHIVES_TABLE)"
log "target: database='$DB_NAME', service='$DB_SERVICE', user='$DB_USER'"

if [ "$MODE" = "replace" ]; then
  TABLES_DESC=""
  if [ -n "$PURLS_FILE" ]; then
    TABLES_DESC="$PURLS_TABLE"
  fi
  if [ -n "$ARCHIVES_FILE" ]; then
    if [ -n "$TABLES_DESC" ]; then
      TABLES_DESC="$TABLES_DESC and $ARCHIVES_TABLE"
    else
      TABLES_DESC="$ARCHIVES_TABLE"
    fi
  fi
  log "WARNING: replace deletes rows missing from the backup and locks $TABLES_DESC during the swap"
fi

if [ "$MODE" = "replace" ] && [ "$ASSUME_YES" != true ]; then
  if [ ! -t 0 ]; then
    error "mode replace requires --yes in non-interactive mode"
    exit 1
  fi
  printf "Replace all rows in the restored tables? Rows missing from the backup will be deleted. [y/N] "
  if ! read -r answer; then
    error "aborted"
    exit 1
  fi
  case "$answer" in
    y|Y|yes|YES) ;;
    *) error "aborted"; exit 1 ;;
  esac
fi

STAGING_PURLS="${PURLS_TABLE}_import_$$"
STAGING_ARCHIVES="${ARCHIVES_TABLE}_import_$$"
PURLS_STAGED=false
ARCHIVES_STAGED=false

cleanup() {
  if [ "$PURLS_STAGED" = true ]; then
    db_psql -c "DROP TABLE IF EXISTS $STAGING_PURLS" >/dev/null 2>&1 || true
  fi
  if [ "$ARCHIVES_STAGED" = true ]; then
    db_psql -c "DROP TABLE IF EXISTS $STAGING_ARCHIVES" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

stage_table() {
  local file="$1" table="$2" staging="$3" columns="$4"
  db_psql -c "CREATE TABLE IF NOT EXISTS $staging (LIKE $table INCLUDING DEFAULTS); TRUNCATE $staging;"
  log "table: $table"
  log "file: $file"
  log "loading $table backup into staging table $staging"
  if ! gunzip -c "$file" | db_psql -c "\\copy $staging ($columns) FROM STDIN WITH (FORMAT csv, HEADER true)"; then
    error "failed to load backup file for $table: $file"
    return 1
  fi
}

apply_merge() {
  local table="$1" staging="$2" columns="$3"
  local counts inserted skipped
  counts="$(
    db_psql -tA -F '|' -c "
      WITH ins AS (
        INSERT INTO $table ($columns)
        SELECT $columns FROM $staging
        ON CONFLICT (purl) DO NOTHING
        RETURNING 1
      )
      SELECT (SELECT count(*) FROM $staging), (SELECT count(*) FROM ins)
    "
  )"
  IFS='|' read -r total inserted <<< "$counts"
  skipped=$((total - inserted))
  log "inserted: $inserted"
  log "skipped: $skipped"
  log "total: $total"
}

apply_replace() {
  local table="$1" staging="$2" columns="$3" total="$4"
  db_psql -c "BEGIN; TRUNCATE $table; INSERT INTO $table ($columns) SELECT DISTINCT ON (purl) $columns FROM $staging ORDER BY purl, resolved_at DESC; COMMIT;"
  log "inserted: $total"
  log "total: $total"
}

PURLS_TOTAL=0
ARCHIVES_TOTAL=0

if [ -n "$PURLS_FILE" ]; then
  PURLS_STAGED=true
  stage_table "$PURLS_FILE" "$PURLS_TABLE" "$STAGING_PURLS" "$PURLS_COLUMNS" || exit 1
  PURLS_TOTAL="$(db_psql -tA -c "SELECT count(*) FROM $STAGING_PURLS")"
fi

if [ -n "$ARCHIVES_FILE" ]; then
  ARCHIVES_STAGED=true
  stage_table "$ARCHIVES_FILE" "$ARCHIVES_TABLE" "$STAGING_ARCHIVES" "$ARCHIVES_COLUMNS" || exit 1
  ARCHIVES_TOTAL="$(db_psql -tA -c "SELECT count(*) FROM $STAGING_ARCHIVES")"
fi

if [ "$MODE" = "replace" ]; then
  if [ -n "$PURLS_FILE" ] && [ "$PURLS_TOTAL" -eq 0 ]; then
    error "backup contains no rows; refusing to replace $PURLS_TABLE"
    exit 1
  fi
  if [ -n "$ARCHIVES_FILE" ] && [ "$ARCHIVES_TOTAL" -eq 0 ]; then
    error "backup contains no rows; refusing to replace $ARCHIVES_TABLE"
    exit 1
  fi
fi

if [ -n "$PURLS_FILE" ]; then
  if [ "$MODE" = "merge" ]; then
    apply_merge "$PURLS_TABLE" "$STAGING_PURLS" "$PURLS_COLUMNS"
  else
    apply_replace "$PURLS_TABLE" "$STAGING_PURLS" "$PURLS_COLUMNS" "$PURLS_TOTAL"
  fi
fi

if [ -n "$ARCHIVES_FILE" ]; then
  if [ "$MODE" = "merge" ]; then
    apply_merge "$ARCHIVES_TABLE" "$STAGING_ARCHIVES" "$ARCHIVES_COLUMNS"
  else
    apply_replace "$ARCHIVES_TABLE" "$STAGING_ARCHIVES" "$ARCHIVES_COLUMNS" "$ARCHIVES_TOTAL"
  fi
fi

if [ "$PURLS_STAGED" = true ]; then
  db_psql -c "DROP TABLE IF EXISTS $STAGING_PURLS"
  PURLS_STAGED=false
fi
if [ "$ARCHIVES_STAGED" = true ]; then
  db_psql -c "DROP TABLE IF EXISTS $STAGING_ARCHIVES"
  ARCHIVES_STAGED=false
fi

log "restore complete (mode: $MODE)"
