#!/usr/bin/env bash
# smoke_sqlite.sh CONTAINER NEW_TAG — online copy of the container's live SQLite hub DB; the new image migrates
# the copy and runs the app on it; then the running image starts on the migrated copy (rollback proven).
set -euo pipefail
C="$1"; NEW="$2"; D="$(cd "$(dirname "$0")" && pwd)"
OLD="$(docker inspect -f '{{.Image}}' "$C")"
W="$(mktemp -d /root/hub321-smoke-XXXX)"; chmod 700 "$W"
SRC="$(docker exec "$C" printenv AIMARKET_DB_PATH)"
docker exec "$C" python3 -c "import sqlite3,sys; s=sqlite3.connect('file:'+sys.argv[1]+'?mode=ro', uri=True); d=sqlite3.connect('/tmp/hub321-copy.db'); s.backup(d); d.close()" "$SRC"
docker cp "$C:/tmp/hub321-copy.db" "$W/hub.db"; docker exec -u 0 "$C" rm -f /tmp/hub321-copy.db
chmod 666 "$W/hub.db"; chmod 777 "$W"
for mode in new old; do
  IMG="$NEW"; [[ "$mode" == old ]] && IMG="$OLD"
  docker run --rm --network none -e SMOKE_MODE=$mode -e SMOKE_DB_PATH=/smoke/hub.db -v "$W:/smoke" \
    -v "$D/smoke_db.py:/tmp/smoke_db.py:ro" --entrypoint python "$IMG" /tmp/smoke_db.py 2>&1 | tail -2
done
rm -rf "$W"
