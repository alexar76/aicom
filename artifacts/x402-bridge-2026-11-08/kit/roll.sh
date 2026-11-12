#!/usr/bin/env bash
# roll.sh EXPECTED_IMAGE NEW_TAG [NAME=VALUE ...] — back up the live hub DB, then swap modelmarket-hub onto NEW_TAG
# with rollout_container.py (keeps the old container stopped as *-security-prev-<stamp>, recreates THEMIS in the new
# namespace, rolls back by itself on a failed health check). NAME=VALUE pairs are set on the new container
# (names are reported, values never). Refuses to start if the container no longer runs EXPECTED_IMAGE.
set -euo pipefail
C=modelmarket-hub; EXPECT="$1"; TAG="$2"; shift 2
now="$(docker inspect -f '{{.Config.Image}}' "$C")"
[[ "$now" == "$EXPECT" ]] || { echo "$C runs $now, not $EXPECT — stop"; exit 1; }
TS="$(date -u +%Y%m%dT%H%M%SZ)"
DBP="$(docker exec "$C" python -c 'from aimarket_hub.config import HubConfig; print(HubConfig().db_path)')"
B="$(dirname "$DBP")/hub-backup-pre-xb-$TS.db"
docker exec "$C" python -c "import sqlite3, sys; s = sqlite3.connect(sys.argv[1]); d = sqlite3.connect(sys.argv[2]); s.backup(d); d.close(); print('backup', sys.argv[2], sqlite3.connect(sys.argv[2]).execute('PRAGMA integrity_check').fetchone()[0])" "$DBP" "$B"
sets=(); for kv in "$@"; do sets+=(--set "$kv"); done
cd /root/hub-3160-main-20261021
python3 rollout_container.py "$C" --image "$TAG" --health http://127.0.0.1:9083/ai-market/v2/health \
  --health http://127.0.0.1:9460/health ${sets[@]+"${sets[@]}"}
