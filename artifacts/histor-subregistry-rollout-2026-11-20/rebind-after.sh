#!/usr/bin/env bash
# One-shot on admin-vps: once the HISTOR host reports the subregistry image as live, rebind MOMUS to it.
# Does nothing for any other image (e.g. after an automatic rollback). Gives up at 2026-11-20 17:00Z.
set -uo pipefail
D=/root/histor-subregistry-20261120
NEW=@NEW_IMAGE_ID@
log() { echo "$(date -u +%FT%TZ) $*" >> "$D/rebind.log"; }
deadline=$(date -u -d '2026-11-20 17:00:00' +%s)
log "start"
while :; do
  live=$(curl -s --max-time 20 --resolve histor.modelmarket.dev:443:<histor-host> https://histor.modelmarket.dev/.well-known/aicom-histor-runtime.json \
         | python3 -c 'import json,sys; print(json.load(sys.stdin).get("imageDigest",""))' 2>/dev/null)
  if [ "$live" = "$NEW" ]; then
    bound=$(python3 -c 'import json; print(json.load(open("/var/lib/momus-quality/live-image.json")).get("imageDigest",""))')
    [ "$bound" = "$NEW" ] && { log "already bound"; exit 0; }
    cp -a /var/lib/momus-quality/live-image.json "$D/live-image.json.pre"
    if /usr/local/sbin/skopos-warden-quality rebind "$NEW" >> "$D/rebind.log" 2>&1; then log "REBIND-OK"; else log "REBIND-FAILED"; fi
    exit 0
  fi
  if [ "$(date -u +%s)" -ge "$deadline" ]; then log "SKIP: live image is ${live:-unknown} at 17:00Z"; exit 0; fi
  sleep 600
done
