#!/usr/bin/env bash
# Start the UNI lottery relayer — binds to Monitor's Anvil + pushes live metrics.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE="$ROOT/lottery/docker-compose.uni.yml"
ENV_FILE="$ROOT/.env"
MONITOR="${MONITOR_URL:-http://127.0.0.1:9100}"
RELAYER_PORT="${LOTTERY_RELAYER_PORT:-9195}"

echo "=== UNI lottery relayer ==="

# Load .env for ALIEN_API_TOKEN / lottery addresses
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

HEALTH="$(curl -sf "$MONITOR/api/health" 2>/dev/null || echo '{}')"
LOTTERY_ADDR="$(echo "$HEALTH" | python3 -c "
import json,sys
d=json.load(sys.stdin)
c=d.get('contracts') or {}
print(c.get('evm_lottery') or '')
" 2>/dev/null || true)"

if [[ -z "$LOTTERY_ADDR" ]]; then
  CFG="$ROOT/data/alien-monitor/universe/universe_config.json"
  if [[ -f "$CFG" ]]; then
    LOTTERY_ADDR="$(python3 -c "import json; print(json.load(open('$CFG')).get('evm_lottery',''))" 2>/dev/null || true)"
  fi
fi

if [[ -z "$LOTTERY_ADDR" ]]; then
  echo "ERROR: evm_lottery not found — run ./scripts/redeploy_uni_contracts.sh first" >&2
  exit 1
fi

export LOTTERY_ADDRESS="$LOTTERY_ADDR"
export HUB_LOTTERY_ADDRESS="${HUB_LOTTERY_ADDRESS:-$LOTTERY_ADDR}"
export MONITOR_URL="$MONITOR"
export MONITOR_TOKEN="${MONITOR_TOKEN:-${ALIEN_API_TOKEN:-}}"
export RPC_URL="${RPC_URL:-http://127.0.0.1:8545}"
export CHAIN_ID="${LOTTERY_CHAIN_ID:-31337}"

echo "Lottery: $LOTTERY_ADDRESS"
echo "Monitor: $MONITOR"
echo "Relayer port: $RELAYER_PORT"

docker rm -f ailottery-relayer-uni 2>/dev/null || true
docker compose -f "$COMPOSE" up -d --build

echo "Waiting for relayer health on :$RELAYER_PORT..."
READY=0
for i in $(seq 1 60); do
  if curl -sf "http://127.0.0.1:${RELAYER_PORT}/healthz" >/dev/null 2>&1; then
    READY=1
    break
  fi
  sleep 2
done

if [[ "$READY" != "1" ]]; then
  echo "ERROR: relayer not healthy" >&2
  docker logs ailottery-relayer-uni --tail 60 2>/dev/null || true
  exit 1
fi
echo "Relayer: OK"

echo "Waiting for live lottery feed in Monitor (round > 0)..."
LIVE=0
for i in $(seq 1 45); do
  ROUND="$(curl -sf "$MONITOR/api/state" 2>/dev/null | python3 -c "
import json,sys
d=json.load(sys.stdin)
lot=next((n for n in d.get('nodes',[]) if n.get('id')=='lottery'),{})
print(lot.get('metrics',{}).get('round',0))
" 2>/dev/null || echo 0)"
  if [[ "${ROUND:-0}" != "0" && "${ROUND:-0}" != "0.0" ]]; then
    LIVE=1
    echo "Monitor lottery round: $ROUND"
    break
  fi
  sleep 2
done

if [[ "$LIVE" != "1" ]]; then
  echo "WARNING: Monitor lottery metrics still idle — check relayer logs" >&2
  docker logs ailottery-relayer-uni --tail 40 2>/dev/null || true
else
  echo "Live lottery feed: OK"
fi

echo ""
echo "Done. Relayer economy: http://127.0.0.1:${RELAYER_PORT}/economy"
