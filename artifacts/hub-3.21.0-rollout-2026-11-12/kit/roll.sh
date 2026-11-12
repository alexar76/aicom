#!/usr/bin/env bash
# roll.sh CONTAINER NEW_TAG HEALTH_URLS(comma separated) [PG_CONTAINER] — back up the hub's database, then swap
# the container onto NEW_TAG with rollout_container.py (which restores the previous container if a health URL
# does not answer). The backup goes to /root/hub-backups, readable by root only.
set -euo pipefail
C="$1"; NEW="$2"; HEALTH="$3"; PGC="${4:-}"
D="$(cd "$(dirname "$0")" && pwd)"
T="$(date -u +%Y%m%dT%H%M%SZ)"; mkdir -p /root/hub-backups; chmod 700 /root/hub-backups
if [[ -n "$PGC" ]]; then
  PGUSER_="$(docker exec "$PGC" printenv POSTGRES_USER || echo postgres)"
  PGDB_="$(docker exec "$PGC" printenv POSTGRES_DB || echo "$PGUSER_")"
  B="/root/hub-backups/$C-pre-3210-$T.dump"
  docker exec "$PGC" pg_dump -U "$PGUSER_" -d "$PGDB_" -Fc > "$B"
else
  SRC="$(docker exec "$C" printenv AIMARKET_DB_PATH)"
  B="/root/hub-backups/$C-pre-3210-$T.db"
  docker exec "$C" python3 -c "import sqlite3,sys; s=sqlite3.connect('file:'+sys.argv[1]+'?mode=ro', uri=True); d=sqlite3.connect('/tmp/hub321-backup.db'); s.backup(d); d.close()" "$SRC"
  docker cp "$C:/tmp/hub321-backup.db" "$B"; docker exec -u 0 "$C" rm -f /tmp/hub321-backup.db
fi
chmod 600 "$B"; echo "backup $B $(du -h "$B" | cut -f1)"
ARGS=(); IFS=',' read -ra URLS <<< "$HEALTH"; for u in "${URLS[@]}"; do ARGS+=(--health "$u"); done
echo "previous image $(docker inspect -f '{{.Image}}' "$C")"
cd "$D" && python3 rollout_container.py "$C" --image "$NEW" "${ARGS[@]}"
docker ps --format '{{.Names}}\t{{.Image}}\t{{.Status}}' | grep -E "^$C\b|themis" || true
