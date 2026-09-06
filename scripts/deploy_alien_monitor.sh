#!/usr/bin/env bash
# Build Alien Monitor + Pulse Terminal, start Docker, wire:
#   https://monitor.modelmarket.dev/     → :9101 (LIVE)
#   https://monitor-uni.modelmarket.dev/ → :9100 (UNI)
#   https://magic-ai-factory.com/pulse/  → :5199
# Factory /monitor and /monitor-live redirect to those subdomains.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MONITOR="$ROOT/alien-monitor"
NGINX_SITE="${NGINX_SITE:-/etc/nginx/sites-enabled/magic-ai-factory.com}"
SNIPPET_MONITOR="$ROOT/deploy/nginx/snippets/alien-monitor.conf"
SNIPPET_PULSE="$ROOT/deploy/nginx/snippets/pulse-terminal.conf"
MONITOR_DOMAIN="${ALIEN_MONITOR_PUBLIC_DOMAIN:-monitor.modelmarket.dev}"
UNI_DOMAIN="${ALIEN_UNI_PUBLIC_DOMAIN:-monitor-uni.modelmarket.dev}"
NGINX_MONITOR_SRC="$ROOT/deploy/nginx/monitor.modelmarket.dev.conf"
NGINX_MONITOR_AVAIL="/etc/nginx/sites-available/${MONITOR_DOMAIN}"
NGINX_MONITOR_ENABLED="/etc/nginx/sites-enabled/${MONITOR_DOMAIN}"
PUBLIC_MONITOR="${ALIEN_MONITOR_PUBLIC_URL:-https://${MONITOR_DOMAIN}/}"
PUBLIC_UNI="${ALIEN_UNIVERSE_MAP_URL:-https://${UNI_DOMAIN}/}"
PUBLIC_PULSE="${PULSE_TERMINAL_PUBLIC_URL:-https://magic-ai-factory.com/pulse/}"
# Subdomain serves at `/` — Vite assets must not be prefixed `/monitor/`.
# Local path-based demos can still override: ALIEN_MONITOR_BASE_PATH=/monitor/
export ALIEN_MONITOR_BASE_PATH="${ALIEN_MONITOR_BASE_PATH:-/}"
export ALIEN_UNIVERSE_MAP_URL="${ALIEN_UNIVERSE_MAP_URL:-https://${UNI_DOMAIN}/}"
export ALIEN_LIVE_MAP_URL="${ALIEN_LIVE_MAP_URL:-https://${MONITOR_DOMAIN}/}"

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
# Re-apply subdomain defaults after .env (host .env may still pin the old /monitor/ URL).
PUBLIC_MONITOR="${ALIEN_MONITOR_PUBLIC_URL:-https://${MONITOR_DOMAIN}/}"
PUBLIC_UNI="${ALIEN_UNIVERSE_MAP_URL:-https://${UNI_DOMAIN}/}"
export ALIEN_MONITOR_BASE_PATH="${ALIEN_MONITOR_BASE_PATH:-/}"
export ALIEN_UNIVERSE_MAP_URL="${ALIEN_UNIVERSE_MAP_URL:-https://${UNI_DOMAIN}/}"
export ALIEN_LIVE_MAP_URL="${ALIEN_LIVE_MAP_URL:-https://${MONITOR_DOMAIN}/}"
if [[ "$ALIEN_MODE" == "real" ]]; then
  # LIVE uses the real chain — don't spin up the embedded universe chains
  # (they aren't read in LIVE and only add ~2GB of memory load).
  export ALIEN_UNIVERSE_AUTO_START="${ALIEN_UNIVERSE_AUTO_START:-0}"
elif [[ "$ALIEN_MODE" == "universe" ]]; then
  # UNI runs Anvil by default; embedded Solana costs ~1.5GB — opt-in via .env.
  export ALIEN_UNIVERSE_ENABLE_SOLANA="${ALIEN_UNIVERSE_ENABLE_SOLANA:-0}"
fi

echo "=== Alien Monitor + Pulse Terminal deploy (mode=${ALIEN_MODE}) ==="
echo "Public LIVE map: ${PUBLIC_MONITOR}  · UNI map: ${PUBLIC_UNI}  (Vite base=${ALIEN_MONITOR_BASE_PATH})"
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

# ── Public URLs must be public ──────────────────────────────────────────────
# This script wires nginx for a real domain, so every URL the Monitor hands to a
# BROWSER has to be reachable from that browser. A localhost value here is not a
# harmless default: it is a dead link for every visitor.
#
# It happened. `AIFACTORY_PUBLIC_URL=http://localhost:9080` sat in the host .env,
# and docker-compose.prod.yml resolves
#     ALIEN_PUBLIC_FACTORY_URL: ${ALIEN_PUBLIC_FACTORY_URL:-${AIFACTORY_PUBLIC_URL:-https://magic-ai-factory.com}}
# so the correct default at the end of that chain was never reached — every
# product in the Monitor's Products card linked to http://localhost:9080/product/…
# The compose file looked right; only the resolved value was wrong, which is why
# this check reads the environment rather than the file.
#
# Warn, do not refuse: the same script is used for local and staging runs where
# localhost is exactly right. The point is that nobody deploys past this silently.
_public_localhost=()
for _v in ALIEN_PUBLIC_FACTORY_URL AIFACTORY_PUBLIC_URL ALIEN_PUBLIC_ARGUS_URL \
          ALIEN_PUBLIC_METIS_URL ALIEN_PUBLIC_MOMUS_URL ALIEN_PUBLIC_SKOPOS_URL \
          ALIEN_PUBLIC_ATLAS_URL ALIEN_PUBLIC_TREASURY_URL ALIEN_MONITOR_PUBLIC_URL; do
  case "${!_v:-}" in
    *localhost*|*127.0.0.1*) _public_localhost+=("$_v=${!_v}") ;;
  esac
done
if [[ "${#_public_localhost[@]}" -gt 0 ]]; then
  echo ""
  echo "WARNING: these are advertised to browsers but point at the deploy host itself:"
  for _h in "${_public_localhost[@]}"; do echo "    · $_h"; done
  echo "  Every visitor gets a dead link. Set them to the public address in .env"
  echo "  (e.g. ALIEN_PUBLIC_FACTORY_URL=https://magic-ai-factory.com) and re-run."
  echo "  Ignore this only if you are deploying for local access."
  echo ""
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
    echo "WARNING: UNI mode but blockchain_ready=false — see docs/uni-and-live.md"
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

# ── Factory /monitor → redirect (replace any old proxy block) ────────────────
replace_factory_monitor_redirect() {
  if [[ ! -f "$NGINX_SITE" ]] || [[ ! -f "$SNIPPET_MONITOR" ]]; then
    return 1
  fi
  echo "Rewriting factory /monitor → ${MONITOR_DOMAIN} in $NGINX_SITE …"
  # Live vhosts often sandwich /monitor-live between = /monitor and ^~ /monitor/,
  # so replace each block on its own — never touch /monitor-live.
  python3 - "$NGINX_SITE" <<'PY'
import re
import sys
from pathlib import Path

site = Path(sys.argv[1])
text = site.read_text(encoding="utf-8")
eq = """    location = /monitor {
        return 302 https://monitor-uni.modelmarket.dev/;
    }
"""
pref = """    location ^~ /monitor/ {
        rewrite ^/monitor/(.*)$ https://monitor-uni.modelmarket.dev/$1 permanent;
    }
"""
pat_eq = re.compile(r"[ \t]*location = /monitor \{.*?\n[ \t]*\}\n", re.S)
pat_pref = re.compile(r"[ \t]*location \^~ /monitor/ \{.*?\n[ \t]*\}\n", re.S)
changed = False
if pat_eq.search(text):
    text = pat_eq.sub(eq + "\n", text, count=1)
    changed = True
if pat_pref.search(text):
    text = pat_pref.sub(pref + "\n", text, count=1)
    changed = True
if not changed:
    marker = "    location / {"
    if "monitor.modelmarket.dev" in text and "location ^~ /monitor/" in text:
        print(f"Already redirecting in {site}")
        raise SystemExit(0)
    if marker not in text:
        raise SystemExit(f"Could not find /monitor block or insertion point in {site}")
    text = text.replace(marker, eq + "\n" + pref + "\n" + marker, 1)
site.write_text(text, encoding="utf-8")
print(f"Updated {site}")
PY
}

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

# ── Subdomain vhost + TLS (same pattern as deploy_atlas.sh) ──────────────────
install_monitor_subdomain() {
  [[ -f "$NGINX_MONITOR_SRC" ]] || { echo "NOTE: missing $NGINX_MONITOR_SRC"; return 0; }
  if [[ "$(id -u)" -ne 0 ]] && ! command -v sudo >/dev/null 2>&1; then
    echo "NOTE: not root and no sudo — skip subdomain nginx install"
    return 0
  fi
  local sudo=()
  [[ "$(id -u)" -eq 0 ]] || sudo=(sudo)

  "${sudo[@]}" install -d /var/www/certbot
  local email_args=(--register-unsafely-without-email)
  [[ -n "${CERTBOT_EMAIL:-}" ]] && email_args=(-m "$CERTBOT_EMAIL")

  if [[ ! -f "/etc/letsencrypt/live/${MONITOR_DOMAIN}/fullchain.pem" ]]; then
    echo "Issuing TLS for ${MONITOR_DOMAIN} (HTTP-only bootstrap)…"
    "${sudo[@]}" tee "$NGINX_MONITOR_AVAIL" >/dev/null <<HTTPONLY
upstream alien_monitor_app { server 127.0.0.1:9100; keepalive 8; }
server {
    listen 80;
    listen [::]:80;
    server_name ${MONITOR_DOMAIN};
    location ^~ /.well-known/acme-challenge/ {
        root /var/www/certbot;
        default_type "text/plain";
        try_files \$uri =404;
    }
    location / {
        proxy_pass http://alien_monitor_app;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }
}
HTTPONLY
    "${sudo[@]}" ln -sfn "$NGINX_MONITOR_AVAIL" "$NGINX_MONITOR_ENABLED"
    "${sudo[@]}" nginx -t && "${sudo[@]}" systemctl reload nginx
    if command -v certbot >/dev/null 2>&1; then
      "${sudo[@]}" certbot certonly --webroot -w /var/www/certbot --non-interactive --agree-tos \
        --keep-until-expiring -d "$MONITOR_DOMAIN" "${email_args[@]}" || {
          echo "WARNING: certbot failed for ${MONITOR_DOMAIN} — is DNS A → this host live?"
          echo "          HTTP vhost is up; re-run after DNS propagates."
          return 0
        }
    else
      echo "WARNING: certbot missing — HTTP-only vhost installed"
      return 0
    fi
  else
    if command -v certbot >/dev/null 2>&1; then
      "${sudo[@]}" certbot certonly --webroot -w /var/www/certbot --non-interactive --agree-tos \
        --keep-until-expiring -d "$MONITOR_DOMAIN" "${email_args[@]}" || true
    fi
  fi

  "${sudo[@]}" install -m 644 "$NGINX_MONITOR_SRC" "$NGINX_MONITOR_AVAIL"
  "${sudo[@]}" ln -sfn "$NGINX_MONITOR_AVAIL" "$NGINX_MONITOR_ENABLED"
  "${sudo[@]}" systemctl enable --now certbot.timer 2>/dev/null || true
}

if [[ -f "$NGINX_SITE" ]]; then
  replace_factory_monitor_redirect || true
  patch_nginx_snippet 'location ^~ /pulse/' "$SNIPPET_PULSE" || true
else
  echo "NOTE: nginx site not found ($NGINX_SITE) — add snippets under deploy/nginx/snippets/ manually"
fi

install_monitor_subdomain || true

if command -v nginx >/dev/null 2>&1; then
  if [[ "$(id -u)" -eq 0 ]]; then
    nginx -t && systemctl reload nginx
  elif command -v sudo >/dev/null 2>&1; then
    sudo nginx -t && sudo systemctl reload nginx
  fi
fi

echo ""
echo "Alien Monitor LIVE: $PUBLIC_MONITOR"
echo "Alien Monitor UNI:  $PUBLIC_UNI"
echo "Factory bookmarks: /monitor → UNI · /monitor-live → LIVE"
echo "Pulse Terminal: $PUBLIC_PULSE"
echo "LIVE health: ${PUBLIC_MONITOR}api/health"
echo "UNI health:  ${PUBLIC_UNI}api/health"
