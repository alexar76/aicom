#!/usr/bin/env bash
# Production HISTOR onto histor-histor:signed-fingerprints-20261119 (= warden-0.31.0-prod + signed publisher
# statements + /api/v1/fingerprints). Only the image line of the override changes; on start HISTOR applies
# migration 025 (declaration_urls.pointer, declaration_urls.statement).
# Rollback: ./switch.sh rollback — stops HISTOR, withdraws the sets taken from signed statements, removes the
# pointer rows, drops the two columns and schema row 25, restores the override, starts warden-0.31.0-prod.
# Rehearsed on a throw-away Postgres 2026-11-19 (old image refuses 25, accepts after the rollback SQL).
# After either direction: MOMUS rebind on admin-vps to the running image digest.
set -euo pipefail
D=/root/histor-signed-fingerprints-20261119
OLD=histor-histor:warden-0.31.0-prod
NEWTAG=histor-histor:signed-fingerprints-20261119
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
  cp -a docker-compose.warden-image.yml "$D/docker-compose.warden-image.yml.pre"
  sed -i "s#image: $OLD#image: $NEWTAG#" docker-compose.warden-image.yml
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
