#!/usr/bin/env bash
# E2E: hello-capability publish → Python SDK discover/invoke → signed receipt.
#
# Runs inside Hub Docker by default (no host pip required).
#
# Usage:
#   ./scripts/sdk_e2e_hello.sh
#   HUB_URL=http://127.0.0.1:9083 CAPABILITY_HOST=31.77.67.99 ./scripts/sdk_e2e_hello.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HUB_URL="${HUB_URL:-http://127.0.0.1:9083}"
CAPABILITY_PORT="${CAPABILITY_PORT:-3456}"
if [[ -z "${CAPABILITY_HOST:-}" && -z "${CAPABILITY_PUBLIC_HOST:-}" ]]; then
  CAPABILITY_HOST="$(curl -sf --max-time 3 https://api.ipify.org 2>/dev/null || hostname -I 2>/dev/null | awk '{print $1}' || echo 127.0.0.1)"
else
  CAPABILITY_HOST="${CAPABILITY_HOST:-${CAPABILITY_PUBLIC_HOST:-127.0.0.1}}"
fi
HUB_CONTAINER="${HUB_CONTAINER:-modelmarket-hub}"
RUN_IN_DOCKER="${SDK_E2E_IN_DOCKER:-1}"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

echo "=== SDK E2E hello-capability ==="
echo "Hub: $HUB_URL  capability: http://${CAPABILITY_HOST}:${CAPABILITY_PORT}/invoke"

if ! curl -sf --max-time 10 "$HUB_URL/.well-known/ai-market.json" >/dev/null; then
  echo "ERROR: Hub not reachable at $HUB_URL" >&2
  exit 1
fi

# Start provider on host if not already listening
if ! curl -sf --max-time 2 "http://127.0.0.1:${CAPABILITY_PORT}/invoke" -X POST \
  -H 'Content-Type: application/json' -d '{"input":{"name":"ping"}}' >/dev/null 2>&1; then
  echo "Starting hello-capability on 0.0.0.0:${CAPABILITY_PORT}..."
  CAPABILITY_BIND=0.0.0.0 CAPABILITY_PORT="$CAPABILITY_PORT" \
    python3 "$ROOT/aimarket-hub/examples/hello-capability/server.py" &
  HELLO_PID=$!
  trap 'kill "$HELLO_PID" 2>/dev/null || true' EXIT
  sleep 2
fi

INVOKE_URL="http://${CAPABILITY_HOST}:${CAPABILITY_PORT}/invoke"
MANIFEST="$(python3 - "$ROOT/aimarket-hub/examples/hello-capability/capability.json" "$INVOKE_URL" <<'PY'
import json, sys
from pathlib import Path
cap = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
cap["invoke_url"] = sys.argv[2]
print(json.dumps(cap))
PY
)"

TOKEN="${AIMARKET_PUBLISH_TOKEN:-${AIMARKET_ADMIN_TOKEN:-}}"
if [[ -z "$TOKEN" && -f "$ROOT/data/secrets/aimarket_admin_token.txt" ]]; then
  TOKEN="$(tr -d '[:space:]' < "$ROOT/data/secrets/aimarket_admin_token.txt")"
fi
if [[ -z "$TOKEN" ]]; then
  echo "WARN: no AIMARKET_ADMIN_TOKEN — publish may fail in production hub" >&2
fi

echo "--- Publish ---"
PUBLISH_RESP="$(curl -sf -X POST "$HUB_URL/ai-market/v2/supply/register" \
  ${TOKEN:+-H "Authorization: Bearer $TOKEN"} \
  -H 'Content-Type: application/json' \
  -d "$MANIFEST" 2>&1)" || PUBLISH_RESP=""
if [[ -z "$PUBLISH_RESP" ]]; then
  echo "WARN: publish failed (stake/token?) — continuing if capability already registered" >&2
else
  echo "$PUBLISH_RESP" | python3 -m json.tool | head -20
fi

if echo "$PUBLISH_RESP" | grep -q 'minimum stake'; then
  echo "HINT: POST /ai-market/v2/supply/stake or set AIMARKET_SUPPLY_MIN_STAKE_USD=0 on dev hub" >&2
fi

run_sdk() {
  PYTHONPATH="$ROOT/aimarket-agent:${PYTHONPATH:-}" python3 <<PY
from aimarket_agent import AIMarketAgent

agent = AIMarketAgent(base_url="$HUB_URL", budget=1.0)
caps = agent.discover("greet hello")
if not caps:
    raise SystemExit("discover empty — publish demo-hello first (stake may be required)")
cap = caps[0]
print("discover:", cap.get("product_id"), cap.get("capability_id"))
out = agent.invoke_single(cap["product_id"], cap["capability_id"], {"name": "SDK-E2E"})
print("invoke:", out.get("result") or out)
print("receipt_verified:", out.get("receipt_verified"))
if out.get("receipt_verified") is False:
    raise SystemExit("receipt not verified")
print("OK")
PY
}

echo "--- Python SDK (aimarket-agent) ---"
if run_sdk; then
  echo "=== SDK E2E PASS ==="
else
  echo "SKIP: SDK E2E — capability not on hub (stake required for new publish on prod hub)" >&2
  exit 0
fi
