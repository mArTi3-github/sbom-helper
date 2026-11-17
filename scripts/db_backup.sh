#!/usr/bin/env bash
set -euo pipefail

# ------------------------------------------------------------------
# sbom-helper full database backup script
# Exports every row of the resolved_purls table into a gzipped CSV file
# and every row of purl_source_archives into a companion file.
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
  -o, --output FILE  Output file for resolved_purls (default: backups/sbom_purls_<UTC>.csv.gz)
      --keep N       Keep only the N newest backup sets in the backup directory
  -v, --verbose      Verbose output
  -h, --help         Show this help

The archive cache is written next to FILE as FILE.source_archives.csv.gz
(default: backups/sbom_source_archives_<UTC>.csv.gz, same timestamp).

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
  BACKUP_STAMP="$(date -u +%Y%m%d-%H%M%S)"
  OUTFILE="$BACKUP_DIR/sbom_purls_${BACKUP_STAMP}.csv.gz"
  ARCHIVE_OUTFILE="$BACKUP_DIR/sbom_source_archives_${BACKUP_STAMP}.csv.gz"
else
  if [[ "$OUTFILE" != /* ]]; then
    OUTFILE="$INVOCATION_DIR/$OUTFILE"
  fi
  if [[ "$OUTFILE" == *.csv.gz ]]; then
    ARCHIVE_OUTFILE="${OUTFILE%.csv.gz}.source_archives.csv.gz"
  else
    ARCHIVE_OUTFILE="${OUTFILE}.source_archives.csv.gz"
  fi
fi
mkdir -p "$(dirname "$OUTFILE")" "$(dirname "$ARCHIVE_OUTFILE")"

TMP_FILE="${OUTFILE}.tmp"
ARCHIVE_TMP_FILE="${ARCHIVE_OUTFILE}.tmp"
trap 'rm -f "$TMP_FILE" "$ARCHIVE_TMP_FILE"' EXIT

TOTAL="$(
  docker compose "${COMPOSE_FILES[@]}" exec -T "$DB_SERVICE" \
    psql -U "$DB_USER" -d "$DB_NAME" -tA -v ON_ERROR_STOP=1 \
    -c "SELECT count(*) FROM resolved_purls"
)"

ARCHIVE_TOTAL="$(
  docker compose "${COMPOSE_FILES[@]}" exec -T "$DB_SERVICE" \
    psql -U "$DB_USER" -d "$DB_NAME" -tA -v ON_ERROR_STOP=1 \
    -c "SELECT count(*) FROM purl_source_archives"
)"

log "table: resolved_purls, rows: $TOTAL"
log "table: purl_source_archives, rows: $ARCHIVE_TOTAL"
log "writing $OUTFILE"
log "writing $ARCHIVE_OUTFILE"

EXPORT_SQL="COPY (SELECT purl, repository_url, resolver, resolved_at
                   FROM resolved_purls ORDER BY purl)
            TO STDOUT WITH (FORMAT csv, HEADER true)"
debug "export SQL: $EXPORT_SQL"

ARCHIVE_EXPORT_SQL="COPY (SELECT purl, version, match_type, reason, archive_url,
                                 archive_url_commit, matched_ref, matched_ref_type,
                                 matched_version, repository_url, resolver, resolved_at
                          FROM purl_source_archives ORDER BY purl)
                    TO STDOUT WITH (FORMAT csv, HEADER true)"
debug "archive export SQL: $ARCHIVE_EXPORT_SQL"

docker compose "${COMPOSE_FILES[@]}" exec -T -e PGTZ=UTC "$DB_SERVICE" \
  psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 \
  -c "$EXPORT_SQL" \
  | gzip > "$TMP_FILE"

docker compose "${COMPOSE_FILES[@]}" exec -T -e PGTZ=UTC "$DB_SERVICE" \
  psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 \
  -c "$ARCHIVE_EXPORT_SQL" \
  | gzip > "$ARCHIVE_TMP_FILE"

mv "$TMP_FILE" "$OUTFILE"
mv "$ARCHIVE_TMP_FILE" "$ARCHIVE_OUTFILE"

SIZE="$(du -h "$OUTFILE" | cut -f1)"
ARCHIVE_SIZE="$(du -h "$ARCHIVE_OUTFILE" | cut -f1)"
log "backup complete: $OUTFILE ($SIZE, rows: $TOTAL)"
log "backup complete: $ARCHIVE_OUTFILE ($ARCHIVE_SIZE, archives rows: $ARCHIVE_TOTAL)"

if [ -n "$KEEP" ]; then
  shopt -s nullglob
  CANDIDATES=(
    "$BACKUP_DIR"/sbom_purls_*.csv.gz
    "$BACKUP_DIR"/sbom_source_archives_*.csv.gz
    "$BACKUP_DIR"/*.source_archives.csv.gz
  )
  shopt -u nullglob

  declare -A BACKUP_GROUPS=()
  for candidate in "${CANDIDATES[@]}"; do
    name="$(basename "$candidate")"
    if [[ "$name" =~ ([0-9]{8}-[0-9]{6}) ]]; then
      stamp="${BASH_REMATCH[1]}"
      case "${BACKUP_GROUPS[$stamp]:-}" in
        *"$candidate"$'\n'*) ;;
        *) BACKUP_GROUPS["$stamp"]+="$candidate"$'\n' ;;
      esac
    else
      debug "not rotating backup without timestamp: $candidate"
    fi
  done

  STAMPS=()
  if [ "${#BACKUP_GROUPS[@]}" -gt 0 ]; then
    mapfile -t STAMPS < <(printf '%s\n' "${!BACKUP_GROUPS[@]}" | sort -r)
  fi
  if [ "${#STAMPS[@]}" -gt "$KEEP" ]; then
    for stamp in "${STAMPS[@]:$KEEP}"; do
      while IFS= read -r old; do
        [ -n "$old" ] || continue
        log "removing old backup: $old"
        rm -f "$old"
      done <<< "${BACKUP_GROUPS[$stamp]}"
    done
  fi
fi
