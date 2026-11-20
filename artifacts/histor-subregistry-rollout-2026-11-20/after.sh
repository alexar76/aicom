#!/usr/bin/env bash
# One-shot (owner 2026-11-20: «Yes, deploy»): switch HISTOR to histor-histor:subregistry-20261120 after the
# signed-fingerprints rollout of the same morning has finished its own checks and while no crawl run is open.
# Guards: that rollout logged SWITCH-OK and its last check line; the running image is signed-fingerprints-20261119;
# give up at 2026-11-20 16:00Z (the next crawl starts about 18:30Z). A failed switch rolls back.
# Log: after.log (SWITCH-OK / SWITCH-FAILED / ROLLBACK-OK / SKIP ...). MOMUS rebind runs on admin-vps by its own timer.
set -uo pipefail
D=/root/histor-subregistry-20261120
P=/root/histor-signed-fingerprints-20261119/after-crawl.log
log() { echo "$(date -u +%FT%TZ) $*" >> "$D/after.log"; }
q() { echo "$1" | docker exec -i histor-histor-postgres-1 sh -c 'psql -U ${POSTGRES_USER:-histor} -d ${POSTGRES_DB:-histor} -At'; }
deadline=$(date -u -d '2026-11-20 16:00:00' +%s)
log "start"
while :; do
  if grep -q -e 'SKIP' -e 'SWITCH-FAILED' "$P" 2>/dev/null; then log "SKIP: the signed-fingerprints rollout did not go through ($(tail -1 "$P"))"; exit 0; fi
  if grep -q 'SWITCH-OK' "$P" 2>/dev/null && grep -q 'errors in the log since switch' "$P"; then
    open=$(q "SELECT count(*) FROM runs WHERE kind='crawl' AND finished_at IS NULL;")
    [ "$open" = 0 ] && break
  fi
  if [ "$(date -u +%s)" -ge "$deadline" ]; then log "SKIP: not ready at 16:00Z ($(tail -1 "$P" 2>/dev/null))"; exit 0; fi
  sleep 300
done
img=$(docker inspect -f '{{.Config.Image}}' histor-histor-1)
if [ "$img" != histor-histor:signed-fingerprints-20261119 ]; then log "SKIP: running image is $img"; exit 0; fi
if [ "$(docker inspect -f '{{.State.Health.Status}}' histor-histor-1)" != healthy ]; then log "SKIP: HISTOR is not healthy"; exit 0; fi
log "the earlier rollout is done ($(tail -1 "$P")); no crawl open; disk $(df -h / | awk 'NR==2{print $5" used, "$4" free"}'); switching"
if bash "$D/switch.sh" >> "$D/after.log" 2>&1; then
  log "SWITCH-OK"
  sleep 60
  log "health: $(curl -s -m 10 -o /dev/null -w '%{http_code}' http://127.0.0.1:9490/health)"
  log "/v0.1/servers: $(curl -s -m 20 -o /dev/null -w '%{http_code}' 'http://127.0.0.1:9490/v0.1/servers?limit=1')"
  log "fingerprints route: $(curl -s -m 20 -o /dev/null -w '%{http_code}' 'http://127.0.0.1:9490/api/v1/fingerprints?profile=ai-sdk&endpoint=https://mcp.deepwiki.com/mcp')"
  sleep 900
  log "subregistry: $(curl -s -m 20 http://127.0.0.1:9490/api/v1/subregistry | cut -c1-400)"
  log "errors in the log since switch: $(docker logs --since 17m histor-histor-1 2>&1 | grep -c -i 'traceback')"
  log "memory: $(docker stats --no-stream --format '{{.MemUsage}}' histor-histor-1); disk $(df -h / | awk 'NR==2{print $5" used, "$4" free"}')"
else
  log "SWITCH-FAILED; rolling back"
  if bash "$D/switch.sh" rollback >> "$D/after.log" 2>&1; then log "ROLLBACK-OK"; else log "ROLLBACK-FAILED"; fi
fi
