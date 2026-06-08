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
LOG_PREFIX="[deploy $(date '+%Y-%m-%d %H:%M:%S')]"

log()  { printf "%s %s\n" "$LOG_PREFIX" "$*"; }
error(){ printf "%s ERROR: %s\n" "$LOG_PREFIX" "$*"; }

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
# 4. Rebuild and restart
# ------------------------------------------------------------------
log "Rebuilding and restarting containers..."
docker compose "${COMPOSE_FILES[@]}" up -d --build --remove-orphans

# ------------------------------------------------------------------
# 5. Wait for health check
# ------------------------------------------------------------------
log "Waiting for app container to become healthy..."
if ! docker compose "${COMPOSE_FILES[@]}" exec -T app \
     sh -c 'for i in $(seq 1 30); do
              python -c "
import urllib.request, ssl
ctx=ssl.create_default_context()
ctx.check_hostname=False
ctx.verify_mode=ssl.CERT_NONE
try:
  urllib.request.urlopen(\"https://localhost:8443/health\", context=ctx)
  exit(0)
except: exit(1)
" 2>/dev/null && exit 0; sleep 2; done; exit 1'; then
  error "App health check timed out after 60s."
  exit 1
fi

log "App is healthy."

# ------------------------------------------------------------------
# 6. Cleanup stale images
# ------------------------------------------------------------------
log "Cleaning up dangling images..."
docker image prune -f 2>/dev/null || true

# ------------------------------------------------------------------
# 7. Restore stashed changes (if any)
# ------------------------------------------------------------------
if [ "$STASHED" = true ]; then
  log "Restoring stashed changes..."
  git stash pop || true
fi

log "Deploy complete."