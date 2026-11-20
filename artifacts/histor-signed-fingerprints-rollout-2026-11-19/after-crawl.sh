#!/usr/bin/env bash
# One-shot (owner 2026-11-19: «хистор после исправлений выкатишь»; a release with a migration goes out after the
# crawl, as on 2026-11-16): switch HISTOR to histor-histor:signed-fingerprints-20261119 once no crawl run is open.
# Guards: the running image is still warden-0.31.0-prod; give up at 2026-11-20 10:00Z. A failed switch rolls back
# (switch.sh rollback). Log: after-crawl.log (SWITCH-OK / SWITCH-FAILED / ROLLBACK-OK / SKIP ...).
# MOMUS rebind runs on admin-vps by its own timer.
set -uo pipefail
D=/root/histor-signed-fingerprints-20261119
log() { echo "$(date -u +%FT%TZ) $*" >> "$D/after-crawl.log"; }
q() { echo "$1" | docker exec -i histor-histor-postgres-1 sh -c 'psql -U ${POSTGRES_USER:-histor} -d ${POSTGRES_DB:-histor} -At'; }
deadline=$(date -u -d '2026-11-20 10:00:00' +%s)
log "start"
while :; do
  open=$(q "SELECT count(*) FROM runs WHERE kind='crawl' AND finished_at IS NULL;")
  [ "$open" = 0 ] && break
  if [ "$(date -u +%s)" -ge "$deadline" ]; then log "SKIP: crawl still open at 10:00Z (open=$open)"; exit 0; fi
  sleep 300
done
img=$(docker inspect -f '{{.Config.Image}}' histor-histor-1)
if [ "$img" != histor-histor:warden-0.31.0-prod ]; then log "SKIP: running image is $img"; exit 0; fi
log "no crawl open (last finished $(q "SELECT max(finished_at) FROM runs WHERE kind='crawl';")); switching"
if bash "$D/switch.sh" >> "$D/after-crawl.log" 2>&1; then
  log "SWITCH-OK"
  sleep 60
  log "fingerprints route: $(curl -s -m 20 -o /dev/null -w '%{http_code}' 'http://127.0.0.1:9490/api/v1/fingerprints?profile=ai-sdk&endpoint=https://mcp.deepwiki.com/mcp')"
  log "health: $(curl -s -m 10 -o /dev/null -w '%{http_code}' http://127.0.0.1:9490/health)"
  sleep 900
  log "remote polling failures since switch: $(docker logs --since 17m histor-histor-1 2>&1 | grep -c 'remote polling failed')"
  log "errors in the log since switch: $(docker logs --since 17m histor-histor-1 2>&1 | grep -c -i 'traceback')"
else
  log "SWITCH-FAILED; rolling back"
  if bash "$D/switch.sh" rollback >> "$D/after-crawl.log" 2>&1; then log "ROLLBACK-OK"; else log "ROLLBACK-FAILED"; fi
fi
