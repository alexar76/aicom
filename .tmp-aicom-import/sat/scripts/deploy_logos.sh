#!/usr/bin/env bash
# Deploy LOGOS — federation analytics engine — on the ORACLE HOST, alongside the
# oracle family / GAIA / MOMUS, published on its own domain logos.modelmarket.dev.
#
#   sudo ./scripts/deploy_logos.sh              # build + up + nginx + TLS
#   sudo ./scripts/deploy_logos.sh --no-tls     # skip certbot (HTTP only / behind another edge)
#   sudo CERTBOT_EMAIL=you@x.dev ./scripts/deploy_logos.sh
#
# Prereqs (same host as the oracles):
#   * DNS A record  logos.modelmarket.dev → this host  (already in place)
#   * Docker + docker compose, nginx, certbot present (the oracle host has them)
#   * the shared `ecosystem` docker network exists (created by the hub/oracles stack)
#
# Until this runs, the hostname resolves here but has no vhost, so it falls
# through to the default server — another service answers and the certificate
# does not cover the name.
#
# Idempotent: re-run to redeploy after a pull. The container binds loopback only;
# nginx is the sole TLS edge (matches the oracle-family topology).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOMAIN="${LOGOS_PUBLIC_DOMAIN:-logos.modelmarket.dev}"
COMPOSE="$ROOT/logos/docker-compose.yml"
NGINX_CONF_SRC="$ROOT/deploy/nginx/logos.modelmarket.dev.conf"
NGINX_AVAIL="/etc/nginx/sites-available/${DOMAIN}"
NGINX_ENABLED="/etc/nginx/sites-enabled/${DOMAIN}"
EMAIL="${CERTBOT_EMAIL:-}"
DO_TLS=1
for arg in "$@"; do
  case "$arg" in
    --no-tls) DO_TLS=0 ;;
    -h|--help) sed -n '2,19p' "$0"; exit 0 ;;
    *) echo "Unknown option: $arg" >&2; exit 1 ;;
  esac
done

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root on the oracle host: sudo $0" >&2
  exit 1
fi

echo "=== LOGOS deploy → https://${DOMAIN} (federation analytics engine) ==="

# ── 1. The shared ecosystem network (LOGOS joins it; never owns it) ───────────
if ! docker network inspect ecosystem >/dev/null 2>&1; then
  echo "Creating shared 'ecosystem' docker network (was absent)…"
  docker network create ecosystem
fi

# ── 2. Build + (re)start the loopback-only containers ────────────────────────
# Build context is the monorepo root (the image needs oracle-core).
echo "Building + starting logos (127.0.0.1:5199) + logos-postgres…"
docker compose -f "$COMPOSE" up -d --build

# ── 3. Health gate — do not touch nginx until the app answers ────────────────
echo -n "Waiting for logos health on 127.0.0.1:5199 "
for i in $(seq 1 60); do
  if curl -sf --max-time 3 http://127.0.0.1:5199/health >/dev/null; then
    echo "— ok"; break
  fi
  echo -n "."; sleep 1
  if [[ "$i" -eq 60 ]]; then
    echo
    echo "logos did not become healthy; check: docker compose -f $COMPOSE logs logos" >&2
    exit 1
  fi
done

# The store is the part that historically failed only in production, because the
# dev default is SQLite and the deploy is Postgres. Prove it opened.
if docker compose -f "$COMPOSE" logs logos 2>&1 | grep -qiE "psycopg2|does not exist|null value in column"; then
  echo "WARN: Postgres errors in the logos log — inspect before announcing the host:" >&2
  docker compose -f "$COMPOSE" logs --tail 40 logos >&2
fi
curl -sf --max-time 5 http://127.0.0.1:5199/api/v1/anomalies?status=open >/dev/null \
  && echo "store reachable through the API — ok" \
  || echo "WARN: /api/v1/anomalies did not answer 200 (check the store)"

# ── 4. nginx edge ────────────────────────────────────────────────────────────
if ! command -v nginx >/dev/null; then
  apt-get update -qq && apt-get install -y -qq nginx
fi
install -m 0644 "$NGINX_CONF_SRC" "$NGINX_AVAIL"
ln -sf "$NGINX_AVAIL" "$NGINX_ENABLED"
mkdir -p /var/www/certbot
nginx -t
systemctl enable nginx >/dev/null 2>&1 || true
systemctl reload nginx

# ── 5. TLS via Let's Encrypt ─────────────────────────────────────────────────
if [[ "$DO_TLS" -eq 1 ]]; then
  if ! command -v certbot >/dev/null; then
    apt-get install -y -qq certbot python3-certbot-nginx
  fi
  CERTBOT_ARGS=(--nginx --non-interactive --agree-tos --redirect --cert-name "${DOMAIN}" -d "${DOMAIN}")
  if [[ -n "$EMAIL" ]]; then CERTBOT_ARGS+=(-m "$EMAIL"); else CERTBOT_ARGS+=(--register-unsafely-without-email); fi
  certbot "${CERTBOT_ARGS[@]}"
  systemctl reload nginx
  systemctl enable --now certbot.timer >/dev/null 2>&1 || true
else
  echo "Skipping certbot (--no-tls). Serving plain HTTP on :80."
fi

echo
echo "=== LOGOS live ==="
echo "  Dashboard:   https://${DOMAIN}/"
echo "  Health:      https://${DOMAIN}/health"
echo "  Snapshot:    https://${DOMAIN}/api/v1/snapshot"
echo "  Consumption: https://${DOMAIN}/api/v1/consumption"
echo "  A2A card:    https://${DOMAIN}/.well-known/agent-card.json"
echo
echo "Verify from OUTSIDE the host (a valid cert for the name is the point):"
echo "  curl -sS https://${DOMAIN}/health"
