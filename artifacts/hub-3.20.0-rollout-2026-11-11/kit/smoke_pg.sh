#!/usr/bin/env bash
# smoke_pg.sh HUB_CONTAINER NEW_TAG PG_CONTAINER — pg_dump of the live hub database into a throw-away Postgres
# (same image, on an --internal network with no way out); the new image migrates the copy and runs the app on
# it; then the running hub image starts on the migrated copy (rollback proven). Nothing touches the live DB
# except the read-only pg_dump. The throw-away password is generated here and never printed.
set -euo pipefail
C="$1"; NEW="$2"; PGC="$3"; D="$(cd "$(dirname "$0")" && pwd)"
OLD="$(docker inspect -f '{{.Image}}' "$C")"
PGIMG="$(docker inspect -f '{{.Image}}' "$PGC")"
PGUSER_="$(docker exec "$PGC" printenv POSTGRES_USER || echo postgres)"
PGDB_="$(docker exec "$PGC" printenv POSTGRES_DB || echo "$PGUSER_")"
W="$(mktemp -d /root/hub320-pgsmoke-XXXX)"; chmod 700 "$W"
NET="hub320-smoke-$$"; TMPPG="hub320-pg-$$"; PW="$(openssl rand -hex 16)"
cleanup() { docker rm -f "$TMPPG" >/dev/null 2>&1 || true; docker network rm "$NET" >/dev/null 2>&1 || true; rm -rf "$W"; }
trap cleanup EXIT
docker exec "$PGC" pg_dump -U "$PGUSER_" -d "$PGDB_" -Fc > "$W/hub.dump"
echo "dump $(du -h "$W/hub.dump" | cut -f1)"
docker network create --internal "$NET" >/dev/null
docker run -d --name "$TMPPG" --network "$NET" -e POSTGRES_PASSWORD="$PW" -e POSTGRES_DB=smoke "$PGIMG" >/dev/null
for i in $(seq 1 60); do docker exec "$TMPPG" pg_isready -U postgres -d smoke >/dev/null 2>&1 && break; sleep 1; done
docker exec -i "$TMPPG" pg_restore -U postgres -d smoke --no-owner --no-privileges < "$W/hub.dump" 2>&1 | tail -3 || true
URL="postgresql://postgres:${PW}@${TMPPG}:5432/smoke"
for mode in new old; do
  IMG="$NEW"; [[ "$mode" == old ]] && IMG="$OLD"
  docker run --rm --network "$NET" -e SMOKE_MODE=$mode -e SMOKE_DATABASE_URL="$URL" \
    -v "$D/smoke_db.py:/tmp/smoke_db.py:ro" --entrypoint python "$IMG" /tmp/smoke_db.py 2>&1 | tail -2
done
