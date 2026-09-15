#!/usr/bin/env bash
# Snapshot Factory IQ metrics for R6 live-vs-frozen tracking (run after builds accumulate).
set -euo pipefail
BASE="${AICOM_API_URL:-http://127.0.0.1:9080}"
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
OUT="${1:-/tmp/factory-iq-snapshots.jsonl}"

admin=$(curl -sf --max-time 10 "${BASE}/api/analytics/factory-iq" || echo '{"error":"unavailable"}')
public=$(curl -sf --max-time 10 "${BASE}/api/public/factory-iq" || echo '{"error":"unavailable"}')

line=$(ADMIN="$admin" PUBLIC="$public" TS="$TS" python3 - <<'PY'
import json, os
admin = json.loads(os.environ["ADMIN"])
public = json.loads(os.environ["PUBLIC"])
print(json.dumps({
    "ts": os.environ["TS"],
    "factory_iq": admin.get("factory_iq"),
    "builds_live": (admin.get("builds") or {}).get("live"),
    "builds_frozen": (admin.get("builds") or {}).get("frozen"),
    "gap": (admin.get("learning_curve") or {}).get("gap"),
    "paying_off": (admin.get("learning_curve") or {}).get("paying_off"),
    "ship_rate": admin.get("ship_rate"),
    "ev_slope": admin.get("ev_slope"),
    "public_enabled": public.get("enabled"),
}, separators=(",", ":")))
PY
)

echo "$line" | tee -a "$OUT"
echo "--- Factory IQ @ $TS ---"
echo "$line" | python3 -m json.tool
