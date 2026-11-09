#!/usr/bin/env bash
set -euo pipefail

# ------------------------------------------------------------------
# sbom-helper database restore script
# Restores a CSV.gz backup produced by scripts/db_backup.sh.
# Default mode is "merge": existing rows win, only missing PURLs are added.
# ------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INVOCATION_DIR="$(pwd)"
cd "$SCRIPT_DIR"

umask 077

COMPOSE_FILES=("-f" "docker-compose.yml")
DB_SERVICE="${DB_SERVICE:-db}"
DB_USER="${DB_USER:-sbom}"
DB_NAME="${DB_NAME:-sbom}"
STAGING_TABLE="resolved_purls_import_$$"

MODE="merge"
ASSUME_YES=false
FILE=""

ts()   { date '+%Y-%m-%d %H:%M:%S'; }
log()  { printf "[restore %s] %s\n" "$(ts)" "$*"; }
error(){ printf "[restore %s] ERROR: %s\n" "$(ts)" "$*" >&2; }

usage() {
  cat <<'EOF'
Usage: ./scripts/db_restore.sh FILE [OPTIONS]

Options:
      --mode merge|replace  Restore mode (default: merge)
      --yes                 Do not ask for confirmation in replace mode
  -h, --help                Show this help

Modes:
  merge    Add missing PURLs; existing rows in the target database are kept.
  replace  Replace the whole table with the backup contents. Rows missing
           from the backup are deleted.

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
      if [ -z "$FILE" ]; then
        FILE="$1"
        shift
      else
        error "unexpected argument: $1"
        usage >&2
        exit 1
      fi
      ;;
  esac
done

if [ -z "$FILE" ]; then
  error "backup file is required"
  usage >&2
  exit 1
fi

if [[ "$FILE" != /* ]]; then
  FILE="$INVOCATION_DIR/$FILE"
fi

if [ "$MODE" != "merge" ] && [ "$MODE" != "replace" ]; then
  error "--mode must be 'merge' or 'replace'"
  exit 1
fi

[ -f "$FILE" ] && [ -r "$FILE" ] || { error "backup file not found or not readable: $FILE"; exit 1; }

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
log "file: $FILE"
log "target: database='$DB_NAME', service='$DB_SERVICE', user='$DB_USER'"

EXPECTED_HEADER="purl,repository_url,resolver,resolved_at"
HEADER="$( set +o pipefail; gunzip -c "$FILE" | head -n 1 )"
HEADER="${HEADER%$'\r'}"
HEADER="${HEADER#$'\xEF\xBB\xBF'}"
if [ "$HEADER" != "$EXPECTED_HEADER" ]; then
  error "invalid backup header: expected '$EXPECTED_HEADER', got '$HEADER'"
  exit 1
fi

if [ "$MODE" = "replace" ]; then
  log "WARNING: replace deletes rows missing from the backup and locks resolved_purls during the swap"
fi

if [ "$MODE" = "replace" ] && [ "$ASSUME_YES" != true ]; then
  if [ ! -t 0 ]; then
    error "mode replace requires --yes in non-interactive mode"
    exit 1
  fi
  printf "Replace all rows in resolved_purls? Rows missing from the backup will be deleted. [y/N] "
  if ! read -r answer; then
    error "aborted"
    exit 1
  fi
  case "$answer" in
    y|Y|yes|YES) ;;
    *) error "aborted"; exit 1 ;;
  esac
fi

STAGING_EXISTS=false
cleanup() {
  if [ "$STAGING_EXISTS" = true ]; then
    db_psql -c "DROP TABLE IF EXISTS $STAGING_TABLE" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

STAGING_EXISTS=true
db_psql -c "CREATE TABLE IF NOT EXISTS $STAGING_TABLE (LIKE resolved_purls INCLUDING DEFAULTS); TRUNCATE $STAGING_TABLE;"

log "loading backup into staging table"
if ! gunzip -c "$FILE" | db_psql -c "\\copy $STAGING_TABLE (purl, repository_url, resolver, resolved_at) FROM STDIN WITH (FORMAT csv, HEADER true)"; then
  error "failed to load backup file"
  exit 1
fi

TOTAL="$(db_psql -tA -c "SELECT count(*) FROM $STAGING_TABLE")"

if [ "$MODE" = "replace" ] && [ "$TOTAL" -eq 0 ]; then
  error "backup contains no rows; refusing to replace the table"
  exit 1
fi

if [ "$MODE" = "merge" ]; then
  COUNTS="$(
    db_psql -tA -F '|' -c "
      WITH ins AS (
        INSERT INTO resolved_purls (purl, repository_url, resolver, resolved_at)
        SELECT purl, repository_url, resolver, resolved_at FROM $STAGING_TABLE
        ON CONFLICT (purl) DO NOTHING
        RETURNING 1
      )
      SELECT (SELECT count(*) FROM $STAGING_TABLE), (SELECT count(*) FROM ins)
    "
  )"
  IFS='|' read -r TOTAL INSERTED <<< "$COUNTS"
  SKIPPED=$((TOTAL - INSERTED))
  log "inserted: $INSERTED"
  log "skipped: $SKIPPED"
  log "total: $TOTAL"
else
  db_psql -c "BEGIN; TRUNCATE resolved_purls; INSERT INTO resolved_purls (purl, repository_url, resolver, resolved_at) SELECT DISTINCT ON (purl) purl, repository_url, resolver, resolved_at FROM $STAGING_TABLE ORDER BY purl, resolved_at DESC; COMMIT;"
  INSERTED="$TOTAL"
  log "inserted: $INSERTED"
  log "total: $TOTAL"
fi

db_psql -c "DROP TABLE IF EXISTS $STAGING_TABLE"
STAGING_EXISTS=false

log "restore complete (mode: $MODE)"
