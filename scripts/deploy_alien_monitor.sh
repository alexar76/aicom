#!/usr/bin/env bash
# Build Alien Monitor + Pulse Terminal, start Docker, wire nginx /monitor/ and /pulse/.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MONITOR="$ROOT/alien-monitor"
NGINX_SITE="${NGINX_SITE:-/etc/nginx/sites-enabled/magic-ai-factory.com}"
SNIPPET_MONITOR="$ROOT/deploy/nginx/snippets/alien-monitor.conf"
SNIPPET_PULSE="$ROOT/deploy/nginx/snippets/pulse-terminal.conf"
PUBLIC_MONITOR="${ALIEN_MONITOR_PUBLIC_URL:-https://magic-ai-factory.com/monitor/}"
PUBLIC_PULSE="${PULSE_TERMINAL_PUBLIC_URL:-https://magic-ai-factory.com/pulse/}"

# ── Mode selection (set at deploy time) ───────────────────────────────────────
#   universe (default) — self-contained sim: embedded Anvil/Solana + UNI economy.
#   real (LIVE)        — binds to the REAL chain (Base/8453 by default); reads live
#                        contract addresses from chain_net; no embedded dev chains.
#   test               — lightweight scripted simulator.
# Usage:  ALIEN_MODE=real ./scripts/deploy_alien_monitor.sh    (or pass --live)
# We export ALIEN_MODE so docker compose's ${ALIEN_MODE} interpolation in
# docker-compose.prod.yml picks it up — the environment: block otherwise shadows
# whatever is in ../.env, so an exported value is the only thing that switches mode.
ALIEN_MODE="${ALIEN_MODE:-universe}"
for arg in "$@"; do
  case "$arg" in
    --live|--real)    ALIEN_MODE=real ;;
    --universe|--uni) ALIEN_MODE=universe ;;
    --test)           ALIEN_MODE=test ;;
  esac
done
export ALIEN_MODE
_SAVED_ALIEN_MODE="$ALIEN_MODE"
if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi
export ALIEN_MODE="$_SAVED_ALIEN_MODE"
if [[ "$ALIEN_MODE" == "real" ]]; then
  # LIVE uses the real chain — don't spin up the embedded universe chains
  # (they aren't read in LIVE and only add ~2GB of memory load).
  export ALIEN_UNIVERSE_AUTO_START="${ALIEN_UNIVERSE_AUTO_START:-0}"
elif [[ "$ALIEN_MODE" == "universe" ]]; then
  # UNI runs Anvil by default; embedded Solana costs ~1.5GB — opt-in via .env.
  export ALIEN_UNIVERSE_ENABLE_SOLANA="${ALIEN_UNIVERSE_ENABLE_SOLANA:-0}"
fi

echo "=== Alien Monitor + Pulse Terminal deploy (mode=${ALIEN_MODE}) ==="
echo "Remote poll-only (NOT deployed on this VPS): DIOSCURI :8790, HELIOS :8791 on oracle host"
[[ "$ALIEN_MODE" == "real" ]] && echo "LIVE — real chain (Base/8453 by default via chain_net); embedded dev chains disabled"
# Crypto master switch reminder (see docs/deploy-argus-monitor.md + docs/crypto-switch.md).
# In LIVE the on-chain nodes only light up when AIFACTORY_CRYPTO_ENABLED is on;
# otherwise LIVE runs off-chain and those nodes are greyed with a "blockchain
# disabled" badge. UNI always has its own private Anvil chain regardless.
if [[ "$ALIEN_MODE" == "real" ]]; then
  if [[ "${AIFACTORY_CRYPTO_ENABLED:-0}" =~ ^([1]|[tT]rue|[yY]es|[oO]n)$ ]]; then
    echo "crypto ENABLED — LIVE on-chain nodes (chain/escrow/NFT/ACEX/lottery) will light up on Base"
  else
    echo "NOTE: AIFACTORY_CRYPTO_ENABLED is OFF → LIVE runs OFF-CHAIN; on-chain nodes greyed + 'blockchain disabled in settings' badge."
    echo "      To keep the demo on Base, set AIFACTORY_CRYPTO_ENABLED=1 in .env. See docs/deploy-argus-monitor.md"
  fi
fi

if [[ ! -d "$MONITOR" ]]; then
  echo "ERROR: $MONITOR not found" >&2
  exit 1
fi

# Free host-network chain orphans and monitor dev ports before rebuild.
if [[ -x "$ROOT/scripts/ecosystem_process_cleanup.sh" ]]; then
  "$ROOT/scripts/ecosystem_process_cleanup.sh"
else
  # Legacy fallback when script not present yet.
  for port in 9100 5173 5199 8545 8899; do
    if command -v fuser >/dev/null 2>&1; then
      fuser -k "${port}/tcp" 2>/dev/null || true
    fi
  done
  pkill -f "alien-monitor/backend/main.py" 2>/dev/null || true
  sleep 2
fi

# Corrupted Anvil state breaks UNI bootstrap (anvil rpc timeout). Reset if JSON is invalid.
ANVIL_STATE="$ROOT/data/alien-monitor/universe/anvil-state/state.json"
if [[ -f "$ANVIL_STATE" ]]; then
  if ! python3 -c "import json; json.load(open('$ANVIL_STATE'))" 2>/dev/null; then
    echo "WARN: resetting corrupted Anvil state at $ANVIL_STATE"
    rm -rf "$ROOT/data/alien-monitor/universe/anvil-state"
  fi
fi

# Stop dev processes that may hold demo ports (cleanup script already freed most).
sleep 1

cd "$MONITOR"
export AICOM_IMAGE_TAG="${AICOM_IMAGE_TAG:-$("$ROOT/scripts/docker_image_tag.sh")}"
echo "Docker image tag: $AICOM_IMAGE_TAG"
docker compose -f docker-compose.prod.yml build --pull
docker compose -f docker-compose.prod.yml up -d --force-recreate

echo "Waiting for health..."
for _ in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:9100/api/health" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
curl -sf "http://127.0.0.1:9100/api/health" | head -c 400 || {
  echo "ERROR: Alien Monitor backend not healthy on :9100" >&2
  docker compose -f docker-compose.prod.yml logs --tail=40 alien-monitor
  exit 1
}
echo ""

if [[ "$ALIEN_MODE" == "real" ]]; then
  echo "LIVE bootstrap check (mode=real + Base contracts wired)..."
  MODE=""
  for _ in $(seq 1 30); do
    MODE="$(curl -sf "http://127.0.0.1:9100/api/health" 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('mode',''))" 2>/dev/null || true)"
    [[ "$MODE" == "real" ]] && break
    sleep 2
  done
  if [[ "$MODE" != "real" ]]; then
    echo "ERROR: monitor did not come up in LIVE (real) mode (mode='$MODE'). Is ALIEN_MODE exported into compose?" >&2
    docker compose -f docker-compose.prod.yml logs --tail=40 alien-monitor
    exit 1
  fi
  # Confirm LIVE resolves the real on-chain addresses and can poll the live chain.
  docker exec alien-monitor python3 -c "
import asyncio, main, chain_metrics
c = chain_metrics.configured_contracts()
print('  LIVE chain :', chain_metrics.primary_evm_chain())
print('  escrow     :', c.get('escrow_evm'))
print('  nft        :', c.get('nft_evm'))
d = asyncio.run(main.fetch_real_metrics())
assert d.get('mode') == 'real', d
assert d.get('nodes'), 'no nodes returned from the live chain'
print('  LIVE ok — live nodes:', len(d['nodes']))
" || { echo "ERROR: LIVE Base verification failed — check RPC reachability and chain_net addresses" >&2; exit 1; }
  echo ""
else
  echo "UNI bootstrap check (mode + blockchain_ready)..."
  for _ in $(seq 1 45); do
    HEALTH_JSON="$(curl -sf "http://127.0.0.1:9100/api/health" 2>/dev/null || echo '{}')"
    MODE="$(echo "$HEALTH_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin).get('mode',''))" 2>/dev/null || true)"
    BC_READY="$(echo "$HEALTH_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin).get('blockchain_ready', False))" 2>/dev/null || true)"
    if [[ "$MODE" != "universe" ]] || [[ "$BC_READY" == "True" ]]; then
      echo "$HEALTH_JSON" | python3 -m json.tool 2>/dev/null || echo "$HEALTH_JSON"
      break
    fi
    sleep 2
  done
  if [[ "$MODE" == "universe" && "$BC_READY" != "True" ]]; then
    echo "WARNING: UNI mode but blockchain_ready=false — see docs/uni-troubleshooting.md"
    docker compose -f docker-compose.prod.yml logs --tail=60 alien-monitor
  fi
  if [[ -f "$ROOT/data/alien-monitor/universe/hub.env.snippet" ]]; then
    echo ""
    echo "Hub wiring snippet (merge into .env, restart Hub):"
    cat "$ROOT/data/alien-monitor/universe/hub.env.snippet"
  fi
  echo ""
fi

echo "Waiting for Pulse Terminal on :5199..."
for _ in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:5199/" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
curl -sf "http://127.0.0.1:5199/" -o /dev/null || {
  echo "ERROR: Pulse Terminal not serving on :5199" >&2
  docker compose -f docker-compose.prod.yml logs --tail=40 pulse-terminal
  exit 1
}
if curl -sf "http://127.0.0.1:9081/api/v2/capital/pricing?limit=1" >/dev/null 2>&1; then
  echo "Factory capital pricing API: OK"
else
  echo "WARNING: Factory GET /api/v2/capital/pricing not reachable on :9081"
fi
echo ""

patch_nginx_snippet() {
  local needle="$1"
  local snippet_path="$2"
  if [[ ! -f "$NGINX_SITE" ]] || [[ ! -f "$snippet_path" ]]; then
    return 1
  fi
  if grep -q "$needle" "$NGINX_SITE"; then
    echo "nginx: $needle already configured in $NGINX_SITE"
    return 0
  fi
  echo "Patching nginx ($NGINX_SITE) — $needle..."
  python3 - "$NGINX_SITE" "$snippet_path" "$needle" <<'PY'
import sys
from pathlib import Path

site = Path(sys.argv[1])
snippet = Path(sys.argv[2]).read_text(encoding="utf-8")
needle = sys.argv[3]
text = site.read_text(encoding="utf-8")
marker = "    location / {"
if marker not in text:
    raise SystemExit(f"Could not find insertion point in {site}")
if needle in text:
    raise SystemExit(0)
site.write_text(text.replace(marker, snippet + "\n" + marker, 1), encoding="utf-8")
print(f"Patched {site}")
PY
}

if [[ -f "$NGINX_SITE" ]]; then
  patch_nginx_snippet 'location ^~ /monitor/' "$SNIPPET_MONITOR" || true
  patch_nginx_snippet 'location ^~ /pulse/' "$SNIPPET_PULSE" || true
else
  echo "NOTE: nginx site not found ($NGINX_SITE) — add snippets under deploy/nginx/snippets/ manually"
fi

if command -v nginx >/dev/null 2>&1 && [[ -f "$NGINX_SITE" ]]; then
  sudo nginx -t
  sudo systemctl reload nginx
fi

echo ""
echo "Alien Monitor: $PUBLIC_MONITOR"
echo "Pulse Terminal: $PUBLIC_PULSE"
echo "Monitor health: ${PUBLIC_MONITOR}api/health"
