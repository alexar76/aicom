#!/usr/bin/env bash
# One-shot (owner 2026-11-15: "After the crawl, ~06Z"): switch HISTOR to histor-histor:instructions-20261115 once the
# package crawl started 2026-11-15T18:21:46Z (run 396663) has finished. Guards: no crawl run open; the running image is
# still landing-scanner-20261115; give up at 10:00Z. A failed switch rolls back (switch.sh rollback).
# Log: after-crawl.log (SWITCH-OK / SWITCH-FAILED / ROLLBACK-OK / SKIP ...). MOMUS rebind runs on admin-vps by its own timer.
set -uo pipefail
D=/root/histor-instructions-20261115
log() { echo "$(date -u +%FT%TZ) $*" >> "$D/after-crawl.log"; }
q() { echo "$1" | docker exec -i histor-histor-postgres-1 sh -c 'psql -U ${POSTGRES_USER:-histor} -d ${POSTGRES_DB:-histor} -At'; }
deadline=$(date -u -d '2026-11-16 10:00:00' +%s)
log "start"
while :; do
  open=$(q "SELECT count(*) FROM runs WHERE kind='crawl' AND finished_at IS NULL;")
  [ "$open" = 0 ] && break
  if [ "$(date -u +%s)" -ge "$deadline" ]; then log "SKIP: crawl still open at 10:00Z (open=$open)"; exit 0; fi
  sleep 300
done
img=$(docker inspect -f '{{.Config.Image}}' histor-histor-1)
if [ "$img" != histor-histor:landing-scanner-20261115 ]; then log "SKIP: running image is $img"; exit 0; fi
log "crawl finished ($(q "SELECT finished_at FROM runs WHERE id=396663;")); switching"
if bash "$D/switch.sh" >> "$D/after-crawl.log" 2>&1; then
  log "SWITCH-OK"
  sleep 900
  log "observations since switch with instructions read: $(q "SELECT count(*) FILTER (WHERE instructions IS NOT NULL), count(*) FILTER (WHERE instructions NOT IN ('')), count(*) FROM observations WHERE id > (SELECT max(id) - 20000 FROM observations) AND observed_at >= to_char(now() at time zone 'UTC' - interval '15 minutes', 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"');")"
  log "remote polling failures since switch: $(docker logs --since 16m histor-histor-1 2>&1 | grep -c 'remote polling failed')"
else
  log "SWITCH-FAILED; rolling back"
  if bash "$D/switch.sh" rollback >> "$D/after-crawl.log" 2>&1; then log "ROLLBACK-OK"; else log "ROLLBACK-FAILED"; fi
fi
