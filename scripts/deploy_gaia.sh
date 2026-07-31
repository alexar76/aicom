#!/usr/bin/env bash
# Deploy GAIA — physical-world oracle gateway — on the ORACLE HOST (78.17.126.214),
# alongside the oracle family, published on its own domain iot.modelmarket.dev.
#
#   sudo ./scripts/deploy_gaia.sh              # build + up + nginx + TLS
#   sudo ./scripts/deploy_gaia.sh --no-tls     # skip certbot (HTTP only / behind another edge)
#   sudo CERTBOT_EMAIL=you@x.dev ./scripts/deploy_gaia.sh
#
# Prereqs (same host as the oracles):
#   * DNS A record  iot.modelmarket.dev → 78.17.126.214  (you add this in the panel)
#   * Docker + docker compose, nginx, certbot present (the oracle host already has them)
#   * the shared `ecosystem` docker network exists (created by the hub/oracles stack)
#
# Idempotent: re-run to redeploy after a `git pull`. Loopback-only containers,
# nginx is the sole TLS edge (matches the oracle-family topology).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# GAIA answers on both a descriptive (iot) and a branded (gaia) hostname; the
# first is the canonical/primary (nginx site filename, cert lineage name).
DOMAINS="${GAIA_PUBLIC_DOMAINS:-iot.modelmarket.dev gaia.modelmarket.dev}"
read -r DOMAIN _ <<<"$DOMAINS"   # primary = first token
COMPOSE="$ROOT/gaia/docker-compose.yml"
NGINX_CONF_SRC="$ROOT/deploy/nginx/iot.modelmarket.dev.conf"
NGINX_AVAIL="/etc/nginx/sites-available/${DOMAIN}"
NGINX_ENABLED="/etc/nginx/sites-enabled/${DOMAIN}"
EMAIL="${CERTBOT_EMAIL:-}"
DO_TLS=1
for arg in "$@"; do
  case "$arg" in
    --no-tls) DO_TLS=0 ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "Unknown option: $arg" >&2; exit 1 ;;
  esac
done

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root on the oracle host (78.17.126.214): sudo $0" >&2
  exit 1
fi

echo "=== GAIA deploy → https://${DOMAIN} (physical-world oracle gateway) ==="

# ── 1. The shared ecosystem network (GAIA joins it; never owns it) ────────────
if ! docker network inspect ecosystem >/dev/null 2>&1; then
  echo "Creating shared 'ecosystem' docker network (was absent)…"
  docker network create ecosystem
fi

# ── 2. Build + (re)start the loopback-only containers ─────────────────────────
# Build context is the monorepo root (the backend image needs oracle-core).
echo "Building + starting gaia-backend (127.0.0.1:9320) + gaia-frontend (127.0.0.1:5182)…"
docker compose -f "$COMPOSE" up -d --build

# ── 3. Health gate — do not touch nginx until the backend answers ─────────────
echo -n "Waiting for gaia-backend health on 127.0.0.1:9320 "
for i in $(seq 1 30); do
  if curl -sf --max-time 3 http://127.0.0.1:9320/health >/dev/null; then
    echo "— ok"; break
  fi
  echo -n "."; sleep 1
  if [[ "$i" -eq 30 ]]; then
    echo; echo "gaia-backend did not become healthy; check: docker compose -f $COMPOSE logs gaia-backend" >&2
    exit 1
  fi
done
curl -sf --max-time 3 http://127.0.0.1:5185/ >/dev/null \
  && echo "gaia-frontend serving on 127.0.0.1:5185 — ok" \
  || echo "WARN: gaia-frontend not answering on 127.0.0.1:5185 yet (check its logs)"

# ── 4. nginx edge ─────────────────────────────────────────────────────────────
if ! command -v nginx >/dev/null; then
  apt-get update -qq && apt-get install -y -qq nginx
fi
install -m 0644 "$NGINX_CONF_SRC" "$NGINX_AVAIL"
ln -sf "$NGINX_AVAIL" "$NGINX_ENABLED"
mkdir -p /var/www/certbot
nginx -t
systemctl enable nginx >/dev/null 2>&1 || true
systemctl reload nginx

# ── 5. TLS via Let's Encrypt ──────────────────────────────────────────────────
if [[ "$DO_TLS" -eq 1 ]]; then
  if ! command -v certbot >/dev/null; then
    apt-get install -y -qq certbot python3-certbot-nginx
  fi
  # One SAN cert (lineage named after the primary) covering every hostname that
  # currently RESOLVES to this host — a not-yet-propagated alias is skipped with
  # a warning rather than failing the whole issuance.
  CERTBOT_ARGS=(--nginx --non-interactive --agree-tos --redirect --cert-name "${DOMAIN}")
  for d in $DOMAINS; do
    if getent hosts "$d" >/dev/null 2>&1; then
      CERTBOT_ARGS+=(-d "$d")
    else
      echo "WARN: ${d} does not resolve yet — skipping it in the cert (re-run after DNS propagates)."
    fi
  done
  if [[ -n "$EMAIL" ]]; then CERTBOT_ARGS+=(-m "$EMAIL"); else CERTBOT_ARGS+=(--register-unsafely-without-email); fi
  certbot "${CERTBOT_ARGS[@]}"
  systemctl reload nginx
else
  echo "Skipping certbot (--no-tls). Serving plain HTTP on :80."
fi

echo
echo "=== GAIA live ==="
echo "  Landing (3D):   https://${DOMAIN}/"
echo "  Manifest:       https://${DOMAIN}/ai-market/v2/manifest"
echo "  Verifier slot:  https://${DOMAIN}/v1/verify"
echo "  WoT directory:  https://${DOMAIN}/wot"
echo "  Health:         https://${DOMAIN}/health"
echo
echo "Point the hub's Pay-on-Verified escrow at GAIA with:"
echo "  AIMARKET_VERIFY_METIS_URL=https://${DOMAIN}  AIMARKET_VERIFY_VERIFIER_ID=gaia.verify@v1"
