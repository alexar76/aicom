#!/usr/bin/env bash
# Deploy clean Relay Scout, sync helper scripts, verify gates, finalize product.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PID="${RELAY_SCOUT_PID:-prod-relay-scout-6ce5e362}"
FACTORY="${FACTORY_HOST:-root@203.0.113.10}"
SRC="$ROOT/relay-scout-fix"
TAR="/tmp/relay-scout-fix.tgz"
FINALIZE="${RELAY_SCOUT_FINALIZE:-1}"

echo "=== pack product ==="
COPYFILE_DISABLE=1 tar -C "$SRC" --exclude='relay_scout.egg-info' --exclude='__pycache__' --exclude='.pytest_cache' -czf "$TAR" .
scp -o BatchMode=yes "$TAR" "$FACTORY:/tmp/relay-scout-fix.tgz"

echo "=== sync scripts ==="
for s in verify_relay_scout_product.py resume_relay_scout_after_fix.py finalize_relay_scout_product.py refresh_product_storefront_telemetry.py ready_relay_scout_storefront.py; do
  scp -o BatchMode=yes "$ROOT/scripts/$s" "$FACTORY:/tmp/$s"
done

echo "=== deploy into factory ==="
ssh -o BatchMode=yes "$FACTORY" bash -s <<EOF
set -euo pipefail
CODE="/root/claudecode/aicom/data/code/$PID"
BACK="/root/claudecode/aicom/data/code/${PID}.bak.\$(date +%s)"
mkdir -p "\$CODE"
if [ -d "\$CODE/relay_scout" ] || [ "\$(find "\$CODE" -maxdepth 1 | wc -l)" -gt 2 ]; then
  cp -a "\$CODE" "\$BACK" || true
  echo "backup: \$BACK"
fi
find "\$CODE" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
tar -xzf /tmp/relay-scout-fix.tgz -C "\$CODE"
rm -rf "\$CODE/relay_scout.egg-info" "\$CODE/**/__pycache__" 2>/dev/null || true
for s in verify_relay_scout_product.py resume_relay_scout_after_fix.py finalize_relay_scout_product.py refresh_product_storefront_telemetry.py ready_relay_scout_storefront.py; do
  docker cp "/tmp/\$s" aicom-app-1:/app/scripts/\$s
done
docker exec aicom-app-1 bash -lc "cd /app/data/code/$PID && PYTHONPATH=/app/data/code/$PID python3 -m pip install -q pytest respx httpx typer rich pyyaml deepdiff fastapi uvicorn pydantic-settings apscheduler 2>/dev/null || true && PYTHONPATH=/app/data/code/$PID python3 -m pytest -q"
EOF

echo "=== verify automated gates ==="
ssh -o BatchMode=yes "$FACTORY" "docker exec aicom-app-1 python3 /app/scripts/verify_relay_scout_product.py --product-id $PID"

if [ "$FINALIZE" = "1" ]; then
  echo "=== storefront-ready finalize ==="
  ssh -o BatchMode=yes "$FACTORY" "docker exec aicom-app-1 python3 /app/scripts/ready_relay_scout_storefront.py --product-id $PID"
else
  echo "=== queue QA only ==="
  ssh -o BatchMode=yes "$FACTORY" "docker exec aicom-app-1 python3 /app/scripts/resume_relay_scout_after_fix.py --product-id $PID"
fi

echo "=== done ==="
