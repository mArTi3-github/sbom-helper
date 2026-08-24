#!/usr/bin/env bash
# End-to-end test for the full Docker Compose stack.
# Tests that:
#   1. Containers start and are healthy
#   2. Resolve API returns correct response
#   3. No "Failed to store" or traceback errors in logs
#   4. Repeat request returns a result (cache works)
#   5. Shutdown cleans up

set -euo pipefail

cd "$(dirname "$0")/../.."

COMPOSE_FILE="docker-compose.yml"
COMPOSE_PROJECT_NAME="sbom-helper-e2e"
PASS=0
FAIL=0

cleanup() {
    echo "=== Cleaning up ==="
    docker compose -f "$COMPOSE_FILE" -p "$COMPOSE_PROJECT_NAME" down --volumes --remove-orphans 2>/dev/null || true
}
trap cleanup EXIT

echo "=== Building and starting containers ==="
docker compose -f "$COMPOSE_FILE" -p "$COMPOSE_PROJECT_NAME" up --build -d

echo "=== Waiting for app to be healthy ==="
for i in $(seq 1 30); do
    if curl -sf http://localhost:8000/health >/dev/null 2>&1; then
        echo "App is healthy (attempt $i)"
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "FAIL: App did not become healthy"
        docker compose -f "$COMPOSE_FILE" -p "$COMPOSE_PROJECT_NAME" logs app
        exit 1
    fi
    sleep 2
done

echo "=== Test 1: Resolve a known PURL ==="
FIRST=$(curl -sf -X POST http://localhost:8000/api/v1/resolve/batch \
    -H "Content-Type: application/json" \
    -d '{"purls":["pkg:pypi/django@1.11.1"]}')
echo "$FIRST" | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert len(d['results']) == 1, f'Expected one result: {d}'
item = d['results'][0]
assert item['repository_url'] == 'https://github.com/django/django', f'Wrong repo: {d}'
assert item['error'] is None, f'Unexpected error: {d}'
assert isinstance(item['warnings'], list), 'warnings is not a list'
print(f\"  OK: {item['repository_url']}\")
"
PASS=$((PASS + 1))

echo "=== Test 2: Check no 'Failed to store' errors in logs ==="
LOGS=$(docker compose -f "$COMPOSE_FILE" -p "$COMPOSE_PROJECT_NAME" logs app 2>&1 || true)
if echo "$LOGS" | grep -q "Failed to store"; then
    echo "FAIL: Found 'Failed to store' errors in logs"
    echo "$LOGS" | grep "Failed to store"
    FAIL=$((FAIL + 1))
else
    echo "  OK: No 'Failed to store' errors"
    PASS=$((PASS + 1))
fi

echo "=== Test 3: Check no traceback/error in logs ==="
if echo "$LOGS" | grep -qi "traceback\|error"; then
    echo "FAIL: Found traceback or error in logs"
    echo "$LOGS" | grep -i "traceback\|error" || true
    FAIL=$((FAIL + 1))
else
    echo "  OK: No traceback or error in logs"
    PASS=$((PASS + 1))
fi

echo "=== Test 4: Repeat request for same PURL (cache) ==="
SECOND=$(curl -sf -X POST http://localhost:8000/api/v1/resolve/batch \
    -H "Content-Type: application/json" \
    -d '{"purls":["pkg:pypi/django@1.11.1"]}')
FIRST_REPO=$(echo "$FIRST" | python3 -c "import sys,json; print(json.load(sys.stdin)['results'][0]['repository_url'])")
SECOND_REPO=$(echo "$SECOND" | python3 -c "import sys,json; print(json.load(sys.stdin)['results'][0]['repository_url'])")
if [ "$FIRST_REPO" = "$SECOND_REPO" ]; then
    echo "  OK: Repeat request returned same result"
    PASS=$((PASS + 1))
else
    echo "FAIL: Repeat request returned different result"
    FAIL=$((FAIL + 1))
fi

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
exit $FAIL