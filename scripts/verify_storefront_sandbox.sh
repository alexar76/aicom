#!/usr/bin/env bash
# Smoke-test marketplace + sandbox inside Docker Compose (single `app` container).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

FR="${AICOM_PORT_FRONTEND:-9080}"
API="${AICOM_PORT_API:-9081}"
BASE="http://127.0.0.1:${FR}"
APIB="http://127.0.0.1:${API}"
PID="prod-demo-market-01"

DC="docker compose"
if ! docker compose version &>/dev/null; then
  DC="docker-compose"
fi

echo "== ${DC} up (use 'docker-compose build app' first if the image is stale) =="
${DC} up -d app

echo "== wait for API health =="
for i in $(seq 1 60); do
  if curl -fsS "${APIB}/api/health" >/dev/null 2>&1; then
    echo "API ok"
    break
  fi
  sleep 2
  if [[ "$i" -eq 60 ]]; then
    echo "Timeout waiting for API"
    ${DC} logs --tail 80 app
    exit 1
  fi
done

echo "== seed demo product =="
${DC} exec -T app python3 /app/scripts/seed_marketplace_demo.py

echo "== GET /api/products (direct API) =="
curl -fsS "${APIB}/api/products" | head -c 400
echo ""

echo "== GET /api/products via Next rewrite =="
curl -fsS "${BASE}/api/products" | head -c 400
echo ""

echo "== GET product detail =="
curl -fsS "${APIB}/api/products/${PID}" | head -c 300
echo ""

echo "== start sandbox =="
RESP="$(curl -fsS -X POST "${APIB}/api/sandbox/start/${PID}")"
echo "$RESP"
SID="$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['sandbox_id'])" "$RESP")"

echo "== sandbox view (first 500 bytes) =="
curl -fsS "${APIB}/api/sandbox/view/${SID}" | head -c 500
echo ""

echo "== sandbox index.html via file route =="
curl -fsS "${APIB}/api/sandbox/file/${SID}/index.html" | head -c 200
echo ""

echo "OK — storefront API + sandbox viewer respond. Open in browser: ${BASE}/product/${PID}"
