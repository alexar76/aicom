#!/usr/bin/env bash
# Recount of stored newAddresses in a one-off container of the production image, beside the live one.
# $1 = status | apply
set -euo pipefail
D=/root/histor-addresses-20261122
cd /opt/histor
C="docker compose -p histor -f docker-compose.yml -f docker-compose.postgres.yml -f docker-compose.warden-image.yml"
if [ "$1" = apply ]; then
  $C run --rm --no-deps -T -v "$D/recount_addresses.py:/app/histor/recount_addresses.py:ro" -v "$D/backup:/backup" --entrypoint python histor -m histor.recount_addresses apply --backup /backup/replaced.jsonl > "$D/recount-apply.json" 2> "$D/recount-apply.log"
else
  $C run --rm --no-deps -T -v "$D/recount_addresses.py:/app/histor/recount_addresses.py:ro" --entrypoint python histor -m histor.recount_addresses status > "$D/recount-status.json" 2> "$D/recount-status.log"
fi
echo "$(date -u +%FT%TZ) $1 done" >> "$D/recount.done"
