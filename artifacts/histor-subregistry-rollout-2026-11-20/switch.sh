#!/usr/bin/env bash
# Production HISTOR onto histor-histor:subregistry-20261120 (= signed-fingerprints-20261119 + the subregistry).
# The override gets the new image line and HISTOR_SUBREGISTRY=1; on start HISTOR applies migration 026 (a new
# table) and, 15 s later, begins the first copy of the registry (about 680 pages, minutes).
# Rollback: ./switch.sh rollback — stops HISTOR, drops the table, its meta keys and schema row 26, restores the
# override, starts signed-fingerprints-20261119. Rehearsed on a throw-away Postgres 2026-11-20.
# After either direction: MOMUS rebind on admin-vps to the running image digest.
set -euo pipefail
D=/root/histor-subregistry-20261120
OLD=histor-histor:signed-fingerprints-20261119
NEWTAG=histor-histor:subregistry-20261120
C="docker compose -p histor -f docker-compose.yml -f docker-compose.postgres.yml -f docker-compose.warden-image.yml"
PSQL='docker exec -i histor-histor-postgres-1 sh -c "psql -v ON_ERROR_STOP=1 -U \${POSTGRES_USER:-histor} -d \${POSTGRES_DB:-histor} -At"'
cd /opt/histor
if [ "${1:-}" = rollback ]; then
  $C stop histor
  cat "$D/rollback.sql" | eval "$PSQL"
  cp -a "$D/docker-compose.warden-image.yml.pre" docker-compose.warden-image.yml
  WANT=$(docker image inspect -f '{{.Id}}' "$OLD")
else
  NEW=$(cat "$D/new-image-id")
  [ "$(docker image inspect -f '{{.Id}}' "$NEWTAG")" = "$NEW" ]
  grep -q "image: $OLD" docker-compose.warden-image.yml
  ! grep -q HISTOR_SUBREGISTRY docker-compose.warden-image.yml
  cp -a docker-compose.warden-image.yml "$D/docker-compose.warden-image.yml.pre"
  sed -i "s#image: $OLD#image: $NEWTAG#" docker-compose.warden-image.yml
  printf '    environment:\n      HISTOR_SUBREGISTRY: "1"\n' >> docker-compose.warden-image.yml
  $C config -q
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
