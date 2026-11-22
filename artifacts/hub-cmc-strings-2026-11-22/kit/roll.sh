#!/usr/bin/env bash
# roll.sh CONTAINER NEW_TAG HEALTH_URLS(comma separated) — back up the hub's SQLite database, then swap the
# container onto NEW_TAG with rollout_container.py (it restores the previous container if a health URL fails).
set -euo pipefail
C="$1"; NEW="$2"; HEALTH="$3"
D="$(cd "$(dirname "$0")" && pwd)"
T="$(date -u +%Y%m%dT%H%M%SZ)"; mkdir -p /root/hub-backups; chmod 700 /root/hub-backups
SRC="$(docker exec "$C" printenv AIMARKET_DB_PATH)"
B="/root/hub-backups/$C-pre-nocmcpage-$T.db"
docker exec "$C" python3 -c "import sqlite3,sys; s=sqlite3.connect('file:'+sys.argv[1]+'?mode=ro', uri=True); d=sqlite3.connect('/tmp/nocmcpage-backup.db'); s.backup(d); d.close()" "$SRC"
docker cp "$C:/tmp/nocmcpage-backup.db" "$B"; docker exec -u 0 "$C" rm -f /tmp/nocmcpage-backup.db
chmod 600 "$B"; echo "backup $B $(du -h "$B" | cut -f1)"
ARGS=(); IFS=',' read -ra URLS <<< "$HEALTH"; for u in "${URLS[@]}"; do ARGS+=(--health "$u"); done
echo "previous image $(docker inspect -f '{{.Image}}' "$C")"
cd "$D" && python3 rollout_container.py "$C" --image "$NEW" "${ARGS[@]}"
docker ps --format '{{.Names}}\t{{.Image}}\t{{.Status}}' | grep -E "^$C\b|themis" || true
