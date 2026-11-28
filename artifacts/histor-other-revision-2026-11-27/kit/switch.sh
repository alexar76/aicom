#!/usr/bin/env bash
# Production HISTOR onto histor-histor:other-revision-20261127 = the image `latest` pointed to on 2026-11-27
# (the running application's image plus that day's peer-check modules, tagged histor-histor:pre-other-revision-20261127)
# plus six files of aicom bd0e37996: the handshake reading kept beside the log (migration 027) and /check's
# same-other-revision. Compose runs "histor-histor:latest", so the switch retags latest and recreates the service
# without building. Rollback: ./switch.sh rollback (takes migration 027 out first: the old image refuses a database
# with a migration it does not know).
set -euo pipefail
D=/root/histor-other-revision-20261127
NEW=$(cat $D/new-image-id); OLD=$(cat $D/old-image-id); BASE=$(cat $D/base-image-id)
C="docker compose -p histor -f docker-compose.yml -f docker-compose.postgres.yml"
cd /opt/histor
log() { echo "$(date -u +%FT%TZ) $*" | tee -a "$D/switch.log"; }
sql() { docker exec -i histor-histor-postgres-1 sh -c 'psql -U ${POSTGRES_USER:-histor} -d ${POSTGRES_DB:-histor} -At'; }
crawls_running() { echo "SELECT count(*) FROM runs WHERE kind='crawl' AND finished_at IS NULL;" | sql; }
up() {
  docker tag "$1" histor-histor:latest
  $C up -d --no-deps --no-build histor >> "$D/switch.log" 2>&1
  for i in $(seq 1 60); do
    s="$(docker inspect -f '{{.State.Health.Status}}' histor-histor-1)"; [ "$s" = healthy ] && break; sleep 5
  done
  log "health=$s image=$(docker inspect -f '{{.Image}}' histor-histor-1)"
  [ "$s" = healthy ] && [ "$(docker inspect -f '{{.Image}}' histor-histor-1)" = "$1" ]
}
back() {
  log "taking migration 027 out ($(echo 'SELECT count(*) FROM revision_readings;' | sql 2>/dev/null || echo no table) readings)"
  echo "BEGIN; DROP TABLE IF EXISTS revision_readings; DELETE FROM schema_migrations WHERE version=27; COMMIT;" | sql >> "$D/switch.log" 2>&1
  up "$OLD" || return 1
  # The peer check runs throw-away containers from `latest`; the application keeps its image by id.
  docker tag "$BASE" histor-histor:latest
  if [ -d "$D/opt-prev" ]; then cp -p "$D"/opt-prev/*.py /opt/histor/histor/; log "restored /opt/histor/histor"; fi
}
if [ "${1:-}" = rollback ]; then back && log "ROLLED-BACK"; exit; fi
[ "$(docker image inspect -f '{{.Id}}' histor-histor:other-revision-20261127)" = "$NEW" ]
[ "$(docker inspect -f '{{.Image}}' histor-histor-1)" = "$OLD" ] || { log "production does not run $OLD; not switching"; exit 1; }
[ "$(docker image inspect -f '{{.Id}}' histor-histor:latest)" = "$BASE" ] || { log "latest is not $BASE; not switching"; exit 1; }
[ "$(echo 'SELECT max(version) FROM schema_migrations;' | sql)" = 26 ] || { log "the database is not at migration 26; not switching"; exit 1; }
[ "${ALLOW_CRAWL:-0}" = 1 ] || [ "$(crawls_running)" = 0 ] || { log "a crawl is running; not switching"; exit 1; }
log "start"
if ! up "$NEW"; then log "SWITCH-FAILED"; back && log "ROLLED-BACK" || log "ROLLBACK-FAILED"; exit 1; fi
sleep 20
ok=1
for p in / /health /api/v1/stats "/api/v1/changes?limit=2" /feed.xml /assets/desk.js /api/v1/log/checkpoint/cosigned "/api/v1/check?endpoint=https://www.stackerscan.com/mcp"; do
  c=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 --resolve histor.modelmarket.dev:443:127.0.0.1 "https://histor.modelmarket.dev$p")
  log "route $p $c"; [ "$c" = 200 ] || ok=0
done
m=$(echo 'SELECT max(version) FROM schema_migrations;' | sql)
r=$(docker exec histor-histor-1 python -c "import inspect; from histor.mcpclient import McpReader; from histor import check; print('handshake_only' in inspect.signature(McpReader.list_tools).parameters, 'same-other-revision' in check.NOTES)" 2>&1)
v=$(docker exec histor-histor-1 node -e 'console.log(require("/app/scanner/node_modules/@aimarket/warden/package.json").version)' 2>&1)
log "migration $m; reader and check $r; vendored warden $v"
[ "$m" = 27 ] || ok=0
[ "$r" = "True True" ] || ok=0
[ "$v" = "$(cat $D/warden-before 2>/dev/null || echo "$v")" ] || ok=0
if [ $ok = 1 ]; then
  mkdir -p "$D/opt-prev"
  for f in check.py config.py crawler.py mcpclient.py migrations.py store.py; do cp -p "/opt/histor/histor/$f" "$D/opt-prev/$f"; cp "$D/overlay/histor/$f" "/opt/histor/histor/$f"; done
  log "/opt/histor/histor updated (previous files in $D/opt-prev)"
  log "SWITCH-OK"
else log "CHECK-FAILED: rolling back"; back && log "ROLLED-BACK" || log "ROLLBACK-FAILED"; exit 1; fi
