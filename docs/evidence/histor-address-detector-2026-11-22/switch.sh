#!/usr/bin/env bash
# Production HISTOR onto histor-histor:addresses-20261122 (sha256:c44951f59d00dd8d0a13d2d5d12093a945526d0e70a193b1e49c51d2a1959f90)
# = histor-histor:warden-0.37.1-prod (sha256:cf11d410…, production since 2026-11-22 15:06Z) plus three files of HISTOR's own
# code: histor/diffing.py, histor/tlds.txt, histor/recount_addresses.py (aicom 30a9b8abf). WARDEN is byte-identical.
# It switches only FROM warden-0.37.1-prod and only with no open crawl, checks five routes and rolls back if one fails.
# Rollback by hand: ./switch.sh rollback. After either direction, on admin-vps:
# forward `skopos-warden-quality rebind sha256:c44951f5…`, rollback `skopos-warden-quality rebind sha256:cf11d410…`.
set -euo pipefail
D=/root/histor-addresses-20261122
NEW=sha256:c44951f59d00dd8d0a13d2d5d12093a945526d0e70a193b1e49c51d2a1959f90
OLD=sha256:cf11d410c06ee1ef073f2d0afc1485f9d399e8f012faee4cfc40a8833c46ee63
OLDTAG=histor-histor:warden-0.37.1-prod
NEWTAG=histor-histor:addresses-20261122
C="docker compose -p histor -f docker-compose.yml -f docker-compose.postgres.yml -f docker-compose.warden-image.yml"
cd /opt/histor
log() { echo "$(date -u +%FT%TZ) $*" | tee -a "$D/switch.log"; }
crawls_running() {
  echo "SELECT count(*) FROM runs WHERE kind='crawl' AND finished_at IS NULL;" |
    docker exec -i histor-histor-postgres-1 sh -c 'psql -U ${POSTGRES_USER:-histor} -d ${POSTGRES_DB:-histor} -At'
}
up() {
  $C up -d --no-deps histor >> "$D/switch.log" 2>&1
  for i in $(seq 1 60); do
    s="$(docker inspect -f '{{.State.Health.Status}}' histor-histor-1)"
    [ "$s" = healthy ] && break
    sleep 5
  done
  log "health=$s image=$(docker inspect -f '{{.Image}}' histor-histor-1)"
  [ "$s" = healthy ] && [ "$(docker inspect -f '{{.Image}}' histor-histor-1)" = "$1" ]
}
back() {
  grep -q "image: $NEWTAG" docker-compose.warden-image.yml
  [ "$(docker image inspect -f '{{.Id}}' $OLDTAG)" = "$OLD" ]
  sed -i "s#image: $NEWTAG#image: $OLDTAG#" docker-compose.warden-image.yml
  up "$OLD"
}
if [ "${1:-}" = rollback ]; then back && log "ROLLED-BACK"; exit; fi

[ "$(docker image inspect -f '{{.Id}}' $NEWTAG)" = "$NEW" ]
grep -q "image: $OLDTAG" docker-compose.warden-image.yml || { log "compose does not name $OLDTAG; not switching"; exit 1; }
[ "$(docker inspect -f '{{.Image}}' histor-histor-1)" = "$OLD" ] || { log "production does not run warden-0.37.1-prod; not switching"; exit 1; }
[ "$(crawls_running)" = 0 ] || { log "a crawl is running; not switching"; exit 1; }
cp -a docker-compose.warden-image.yml "$D/docker-compose.warden-image.yml.pre"
sed -i "s#image: $OLDTAG#image: $NEWTAG#" docker-compose.warden-image.yml
log "start"
if ! up "$NEW"; then log "SWITCH-FAILED"; back && log "ROLLED-BACK" || log "ROLLBACK-FAILED"; exit 1; fi
sleep 20
ok=1
for p in / /health /api/v1/stats '/api/v1/changes?limit=2' /api/v1/log/checkpoint/cosigned; do
  c=$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 --resolve histor.modelmarket.dev:443:127.0.0.1 "https://histor.modelmarket.dev$p")
  log "route $p $c"; [ "$c" = 200 ] || ok=0
done
v=$(docker exec histor-histor-1 node -e 'console.log(require("/app/scanner/node_modules/@aimarket/warden/package.json").version)' 2>&1)
t=$(docker exec histor-histor-1 python -c 'from histor import diffing; print(len(diffing.TLDS), sorted(diffing._addresses_in("versions.kitVersion tiles.example.com")))' 2>&1)
log "vendored warden $v; detector $t"
[ "$v" = 0.37.1 ] || ok=0
[ "$t" = "1284 ['tiles.example.com']" ] || ok=0
if [ $ok = 1 ]; then log "SWITCH-OK"; else log "CHECK-FAILED: rolling back"; back && log "ROLLED-BACK" || log "ROLLBACK-FAILED"; exit 1; fi
