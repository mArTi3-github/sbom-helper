#!/usr/bin/env bash
set -euo pipefail

# ------------------------------------------------------------------
# sbom-helper production update script
# Pulls latest code, rebuilds, redeploys with health-check and rollback.
# ------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SCRIPT_DIR"

# ------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------
VERBOSE=false
while getopts "v" opt; do
  case $opt in
    v) VERBOSE=true ;;
    *) echo "Usage: $0 [-v] [branch]" >&2; exit 1 ;;
  esac
done
shift $((OPTIND - 1))
BRANCH="${1:-main}"
COMPOSE_FILES=("-f" "docker-compose.yml")
PULL_TIMEOUT="${PULL_TIMEOUT:-300}"
ts()  { date '+%Y-%m-%d %H:%M:%S'; }
log()  { printf "[deploy %s] %s\n" "$(ts)" "$*"; }
error(){ printf "[deploy %s] ERROR: %s\n" "$(ts)" "$*"; }
debug(){ [ "$VERBOSE" = true ] && printf "[deploy %s] DEBUG: %s\n" "$(ts)" "$*" || true; }

cleanup() {
  local exit_code=$?
  if [ $exit_code -ne 0 ]; then
    error "Deploy failed (exit $exit_code). Attempting to restart previous containers..."
    docker compose "${COMPOSE_FILES[@]}" up -d || \
      error "Rollback failed — manual intervention required."
  fi
}
trap cleanup EXIT

# ------------------------------------------------------------------
# 1. Check git working tree and switch to target branch
# ------------------------------------------------------------------
log "Checking git state..."

if ! git diff --quiet; then
  log "Uncommitted changes detected — stashing..."
  git stash push -m "auto-stash before deploy $(date '+%Y-%m-%d %H:%M:%S')"
  STASHED=true
else
  STASHED=false
fi

log "Switching to branch '$BRANCH'..."
git checkout "$BRANCH"

# ------------------------------------------------------------------
# 2. Pull latest code (server is still running)
# ------------------------------------------------------------------
log "Pulling latest changes from origin/$BRANCH..."
git pull origin "$BRANCH"

# ------------------------------------------------------------------
# 3. Pull updated base images
# ------------------------------------------------------------------
log "Pulling base images (db service only, timeout=${PULL_TIMEOUT}s)..."
PULL_START=$(date +%s)
PULL_SERVICE="db"
PULL_FLAGS=("${COMPOSE_FILES[@]}" "pull")
if [ "$VERBOSE" = false ]; then
  PULL_FLAGS+=("--quiet")
fi
if ! timeout "$PULL_TIMEOUT" docker compose "${PULL_FLAGS[@]}" "$PULL_SERVICE" 2>&1; then
  PULL_EXIT=$?
  PULL_ELAPSED=$(($(date +%s) - PULL_START))
  case $PULL_EXIT in
    124) error "Pull timed out after ${PULL_TIMEOUT}s — continuing with local image cache." ;;
    *)   error "Pull failed (exit $PULL_EXIT) after ${PULL_ELAPSED}s — continuing with local image cache." ;;
  esac
  debug "Pull command: docker compose ${PULL_FLAGS[*]} $PULL_SERVICE"
else
  PULL_ELAPSED=$(($(date +%s) - PULL_START))
  log "Base images pulled in ${PULL_ELAPSED}s."
fi

# ------------------------------------------------------------------
# 4. Rebuild, restart, and wait for health checks
# ------------------------------------------------------------------
log "Rebuilding and restarting containers..."
BUILD_START=$(date +%s)
debug "Build command: docker compose ${COMPOSE_FILES[*]} up -d --build --remove-orphans --wait --wait-timeout 120"
if ! docker compose "${COMPOSE_FILES[@]}" up -d --build --remove-orphans --wait --wait-timeout 120 2>&1; then
  error "Containers failed to become healthy within 120s."
  debug "Container logs may provide more detail: docker compose ${COMPOSE_FILES[*]} logs --tail=50"
  exit 1
fi
BUILD_ELAPSED=$(($(date +%s) - BUILD_START))
log "All containers healthy (build took ${BUILD_ELAPSED}s)."

# ------------------------------------------------------------------
# 5. Cleanup stale images
# ------------------------------------------------------------------
log "Cleaning up dangling images..."
PRUNE_OUTPUT=$(docker image prune -f 2>&1) || true
debug "docker image prune output: ${PRUNE_OUTPUT}"

# ------------------------------------------------------------------
# 6. Restore stashed changes (if any)
# ------------------------------------------------------------------
if [ "$STASHED" = true ]; then
  log "Restoring stashed changes..."
  git stash pop || true
fi

log "Deploy complete."