#!/bin/sh
set -e

# Fix permissions on the mounted /app/data directory.
# This directory is mounted from the host (./data) and may be owned by
# an arbitrary uid/gid.  The app user (uid 1001) needs write access.
chown -R 1001:1001 /app/data 2>/dev/null || true

# Drop privileges to the app user when running as root.
# Uses Python (always available in this image) instead of su/gosu.
if [ "$(id -u)" = "0" ] && id -u app >/dev/null 2>&1; then
    exec python3 -c '
import os, sys
os.setgid(1001)
os.setuid(1001)
os.execvp(sys.argv[1], sys.argv[1:])
' "$@"
fi

exec "$@"