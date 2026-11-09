#!/usr/bin/env bash
set -euo pipefail

# ------------------------------------------------------------------
# sbom-helper full database backup script
# Exports every row of the resolved_purls table into a gzipped CSV file.
# Run this script on the host, from anywhere in the repository.
# ------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INVOCATION_DIR="$(pwd)"
cd "$SCRIPT_DIR"

COMPOSE_FILES=("-f" "docker-compose.yml")
DB_SERVICE="${DB_SERVICE:-db}"
DB_USER="${DB_USER:-sbom}"
DB_NAME="${DB_NAME:-sbom}"
BACKUP_DIR="${BACKUP_DIR:-backups}"

VERBOSE=false
OUTFILE=""
KEEP=""

ts()   { date '+%Y-%m-%d %H:%M:%S'; }
log()  { printf "[backup %s] %s\n" "$(ts)" "$*"; }
error(){ printf "[backup %s] ERROR: %s\n" "$(ts)" "$*" >&2; }
debug(){ [ "$VERBOSE" = true ] && printf "[backup %s] DEBUG: %s\n" "$(ts)" "$*" >&2 || true; }

usage() {
  cat <<'EOF'
Usage: ./scripts/db_backup.sh [OPTIONS]

Options:
  -o, --output FILE  Output file (default: backups/sbom_purls_<UTC>.csv.gz)
      --keep N       Keep only the N newest backups in the backup directory
  -v, --verbose      Verbose output
  -h, --help         Show this help

Environment:
  DB_SERVICE  Docker Compose service name (default: db)
  DB_USER     PostgreSQL user (default: sbom)
  DB_NAME     Database name (default: sbom)
  BACKUP_DIR  Backup directory (default: backups)
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    -o|--output)
      [ $# -ge 2 ] || { error "missing value for $1"; exit 1; }
      OUTFILE="$2"
      shift 2
      ;;
    --keep)
      [ $# -ge 2 ] || { error "missing value for $1"; exit 1; }
      KEEP="$2"
      shift 2
      ;;
    -v|--verbose)
      VERBOSE=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      error "unknown argument: $1"
      usage >&2
      exit 1
      ;;
  esac
done

if [ -n "$KEEP" ] && ! [[ "$KEEP" =~ ^[1-9][0-9]*$ ]]; then
  error "--keep expects a positive integer"
  exit 1
fi

command -v docker >/dev/null 2>&1 || { error "docker is not installed"; exit 1; }
command -v gzip >/dev/null 2>&1 || { error "gzip is not installed"; exit 1; }

if ! docker compose "${COMPOSE_FILES[@]}" ps --status running --services | grep -qx "$DB_SERVICE"; then
  error "service '$DB_SERVICE' is not running (try: docker compose up -d $DB_SERVICE)"
  exit 1
fi

umask 077
mkdir -p "$BACKUP_DIR"

if [ -z "$OUTFILE" ]; then
  OUTFILE="$BACKUP_DIR/sbom_purls_$(date -u +%Y%m%d-%H%M%S).csv.gz"
elif [[ "$OUTFILE" != /* ]]; then
  OUTFILE="$INVOCATION_DIR/$OUTFILE"
fi
mkdir -p "$(dirname "$OUTFILE")"

TMP_FILE="${OUTFILE}.tmp"
trap 'rm -f "$TMP_FILE"' EXIT

TOTAL="$(
  docker compose "${COMPOSE_FILES[@]}" exec -T "$DB_SERVICE" \
    psql -U "$DB_USER" -d "$DB_NAME" -tA -v ON_ERROR_STOP=1 \
    -c "SELECT count(*) FROM resolved_purls"
)"

log "table: resolved_purls, rows: $TOTAL"
log "writing $OUTFILE"

EXPORT_SQL="COPY (SELECT purl, repository_url, resolver, resolved_at
                   FROM resolved_purls ORDER BY purl)
            TO STDOUT WITH (FORMAT csv, HEADER true)"
debug "export SQL: $EXPORT_SQL"

docker compose "${COMPOSE_FILES[@]}" exec -T -e PGTZ=UTC "$DB_SERVICE" \
  psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 \
  -c "$EXPORT_SQL" \
  | gzip > "$TMP_FILE"

mv "$TMP_FILE" "$OUTFILE"

SIZE="$(du -h "$OUTFILE" | cut -f1)"
log "backup complete: $OUTFILE ($SIZE, rows: $TOTAL)"

if [ -n "$KEEP" ]; then
  mapfile -t FILES < <(ls -1t "$BACKUP_DIR"/sbom_purls_*.csv.gz 2>/dev/null || true)
  if [ "${#FILES[@]}" -gt "$KEEP" ]; then
    for old in "${FILES[@]:$KEEP}"; do
      log "removing old backup: $old"
      rm -f "$old"
    done
  fi
fi
