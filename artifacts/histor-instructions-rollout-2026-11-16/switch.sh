#!/usr/bin/env bash
# Production HISTOR onto histor-histor:instructions-20261115 (= landing-scanner-20261115 + the instructions record,
# main f8ed320e8). Only the image line of the override changes; on start HISTOR applies migration 024.
# Rollback: ./switch.sh rollback — stops HISTOR, drops observations.instructions and schema row 24 (the
# instructions recorded since the switch are lost; their blobs stay, harmless), restores the override, starts
# landing-scanner-20261115. Rehearsed on a throw-away Postgres 2026-11-15 (old image refuses 24, accepts after).
# After either direction: MOMUS rebind on admin-vps to the running image digest.
set -euo pipefail
D=/root/histor-instructions-20261115
C="docker compose -p histor -f docker-compose.yml -f docker-compose.postgres.yml -f docker-compose.warden-image.yml"
PSQL='docker exec -i histor-histor-postgres-1 sh -c "psql -v ON_ERROR_STOP=1 -U \${POSTGRES_USER:-histor} -d \${POSTGRES_DB:-histor} -At"'
cd /opt/histor
if [ "${1:-}" = rollback ]; then
  $C stop histor
  echo "ALTER TABLE observations DROP COLUMN IF EXISTS instructions; DELETE FROM schema_migrations WHERE version=24;" | eval "$PSQL"
  cp -a "$D/docker-compose.warden-image.yml.pre" docker-compose.warden-image.yml
  WANT=$(docker image inspect -f '{{.Id}}' histor-histor:landing-scanner-20261115)
else
  NEW=$(cat "$D/new-image-id")
  [ "$(docker image inspect -f '{{.Id}}' histor-histor:instructions-20261115)" = "$NEW" ]
  grep -q 'image: histor-histor:landing-scanner-20261115' docker-compose.warden-image.yml
  cp -a docker-compose.warden-image.yml "$D/docker-compose.warden-image.yml.pre"
  sed -i 's#image: histor-histor:landing-scanner-20261115#image: histor-histor:instructions-20261115#' docker-compose.warden-image.yml
  WANT=$NEW
fi
$C up -d --no-deps histor
for i in $(seq 1 60); do
  s="$(docker inspect -f '{{.State.Health.Status}}' histor-histor-1)"
  [ "$s" = healthy ] && break
  sleep 5
done
echo "$(date -u +%FT%TZ) health=$s image=$(docker inspect -f '{{.Image}}' histor-histor-1)"
echo "SELECT max(version) FROM schema_migrations;" | eval "$PSQL"
[ "$s" = healthy ] && [ "$(docker inspect -f '{{.Image}}' histor-histor-1)" = "$WANT" ]
