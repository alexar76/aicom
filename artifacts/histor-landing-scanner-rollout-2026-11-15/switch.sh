#!/usr/bin/env bash
# Production HISTOR onto histor-histor:landing-scanner-20261115 (= warden-0.27.0b-prod + landing cadence text
# + scanner line-split fix). Only the image line of the override changes.
# Rollback: ./switch.sh rollback  (restores docker-compose.warden-image.yml.pre, same compose up)
set -euo pipefail
D=/root/histor-landing-scanner-20261115
C="docker compose -p histor -f docker-compose.yml -f docker-compose.postgres.yml -f docker-compose.warden-image.yml"
cd /opt/histor
if [ "${1:-}" = rollback ]; then
  cp -a "$D/docker-compose.warden-image.yml.pre" docker-compose.warden-image.yml
  WANT=$(docker image inspect -f '{{.Id}}' histor-histor:warden-0.27.0b-prod)
else
  NEW=$(cat "$D/new-image-id")
  [ "$(docker image inspect -f '{{.Id}}' histor-histor:landing-scanner-20261115)" = "$NEW" ]
  grep -q 'image: histor-histor:warden-0.27.0b-prod' docker-compose.warden-image.yml
  cp -a docker-compose.warden-image.yml "$D/docker-compose.warden-image.yml.pre"
  sed -i 's#image: histor-histor:warden-0.27.0b-prod#image: histor-histor:landing-scanner-20261115#' docker-compose.warden-image.yml
  WANT=$NEW
fi
$C up -d --no-deps histor
for i in $(seq 1 60); do
  s="$(docker inspect -f '{{.State.Health.Status}}' histor-histor-1)"
  [ "$s" = healthy ] && break
  sleep 5
done
echo "$(date -u +%FT%TZ) health=$s image=$(docker inspect -f '{{.Image}}' histor-histor-1)"
[ "$s" = healthy ] && [ "$(docker inspect -f '{{.Image}}' histor-histor-1)" = "$WANT" ]
