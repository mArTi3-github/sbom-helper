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
BRANCH="${1:-main}"
COMPOSE_FILES=("-f" "docker-compose.yml")
ts()  { date '+%Y-%m-%d %H:%M:%S'; }
log()  { printf "[deploy %s] %s\n" "$(ts)" "$*"; }
error(){ printf "[deploy %s] ERROR: %s\n" "$(ts)" "$*"; }

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
log "Pulling base images..."
docker compose "${COMPOSE_FILES[@]}" pull --quiet 2>/dev/null || true

# ------------------------------------------------------------------
# 4. Rebuild, restart, and wait for health checks
# ------------------------------------------------------------------
log "Rebuilding and restarting containers..."
if ! docker compose "${COMPOSE_FILES[@]}" up -d --build --remove-orphans --wait --wait-timeout 120; then
  error "Containers failed to become healthy within 120s."
  exit 1
fi

log "All containers healthy."

# ------------------------------------------------------------------
# 5. Cleanup stale images
# ------------------------------------------------------------------
log "Cleaning up dangling images..."
docker image prune -f 2>/dev/null || true

# ------------------------------------------------------------------
# 6. Restore stashed changes (if any)
# ------------------------------------------------------------------
if [ "$STASHED" = true ]; then
  log "Restoring stashed changes..."
  git stash pop || true
fi

log "Deploy complete."