#!/usr/bin/env bash
# One-off on factory-vps: the esim-node catalogue snapshot from every backup archive of this host, oldest first,
# through the same recorder into a separate history (/var/lib/aicom/esim-price-history/backfill-borg). An archive holds
# the snapshot of the node's last catalogue read before that night's backup, so this is daily resolution at best (weekly
# before 2026-11-05). Read-only on the repository; extracted files go to a temporary folder that is removed.
#   systemd-run --unit esim-price-backfill --wait --pipe bash /root/esim-price-history-install/backfill_from_borg.sh
set -euo pipefail
OUT=/var/lib/aicom/esim-price-history/backfill-borg
REC=/usr/local/lib/aicom/esim-price-history/esim_price_history.py
FILE=opt/esim-node-data/catalog-snapshot.json
TMP="$(mktemp -d /var/tmp/esim-backfill.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT
cd "$TMP"
for archive in $(aicom-borg list --short | sort); do
  rm -rf "$TMP/opt"
  if aicom-borg extract "::$archive" "$FILE" 2>/dev/null && [[ -s "$TMP/$FILE" ]]; then
    python3 "$REC" record --state-dir "$OUT" --snapshot "$TMP/$FILE" --no-poke
    echo "$archive: $(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d["at"], len(d["plans"]), "plans")' "$TMP/$FILE")"
  else
    echo "$archive: no snapshot"
  fi
done
python3 "$REC" report --state-dir "$OUT"
