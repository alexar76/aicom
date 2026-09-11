#!/usr/bin/env bash
# Run ON the Platon server (203.0.113.20) as root.
# DNS: oracles.modelmarket.dev A → 203.0.113.20 (Timeweb).
# Sets nginx + Let's Encrypt and expects Platon on 127.0.0.1:8080.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
EMAIL="${CERTBOT_EMAIL:-}"
DOMAIN="${PLATON_PUBLIC_DOMAIN:-oracles.modelmarket.dev}"
PLATON_PORT="${PLATON_APP_PORT:-8080}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root on Platon host (203.0.113.20): sudo $0" >&2
  exit 1
fi

if ! command -v nginx >/dev/null; then
  apt-get update -qq
  apt-get install -y -qq nginx
fi
if ! command -v certbot >/dev/null; then
  apt-get install -y -qq certbot python3-certbot-nginx
fi

echo "Checking Platon on 127.0.0.1:${PLATON_PORT} ..."
if ! curl -sf --max-time 10 "http://127.0.0.1:${PLATON_PORT}/api/health" >/dev/null; then
  echo "Platon not on 127.0.0.1:${PLATON_PORT}." >&2
  echo "Set PUBLIC_URL=https://${DOMAIN} and bind the app to 127.0.0.1:${PLATON_PORT}, then re-run." >&2
  exit 1
fi

cp "$ROOT/deploy/nginx/oracles.modelmarket.dev.conf" "/etc/nginx/sites-available/${DOMAIN}"
ln -sf "/etc/nginx/sites-available/${DOMAIN}" "/etc/nginx/sites-enabled/${DOMAIN}"
nginx -t
systemctl enable nginx
systemctl reload nginx

CERTBOT_ARGS=(--nginx --non-interactive --agree-tos --redirect -d "${DOMAIN}")
if [[ -n "$EMAIL" ]]; then
  CERTBOT_ARGS+=(-m "$EMAIL")
else
  CERTBOT_ARGS+=(--register-unsafely-without-email)
fi

certbot "${CERTBOT_ARGS[@]}"
nginx -t && systemctl reload nginx

echo "OK: https://${DOMAIN}/"
curl -sf "https://${DOMAIN}/api/health" | head -c 200
echo ""
curl -sf "https://${DOMAIN}/.well-known/ai-market.json" | head -c 400
echo ""
