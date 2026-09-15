#!/usr/bin/env bash
# modeldev.modelmarket.dev — ecosystem landing (static) + Let's Encrypt + auto-renew.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
EMAIL="${CERTBOT_EMAIL:-}"
DOMAIN="modeldev.modelmarket.dev"
WEB_ROOT="/var/www/${DOMAIN}"
SRC="${ROOT}/ecosystem-landing"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo $0" >&2
  exit 1
fi

if ! command -v certbot >/dev/null; then
  apt-get update -qq
  apt-get install -y -qq certbot python3-certbot-nginx
fi

# certbot.timer — twice daily renew + nginx reload hook (Ubuntu package default)
systemctl enable certbot.timer
systemctl start certbot.timer

echo "Deploying ${SRC} → ${WEB_ROOT} ..."
"$ROOT/scripts/deploy_ecosystem_landing.sh"

# First-time TLS + vhost (idempotent on renewals)

echo "Waiting for HTTP vhost ..."
for _ in $(seq 1 20); do
  if curl -sf --max-time 5 -H "Host: ${DOMAIN}" "http://127.0.0.1/" | grep -q 'AICOM'; then
    break
  fi
  sleep 1
done

CERTBOT_ARGS=(--nginx --non-interactive --agree-tos --redirect -d "${DOMAIN}")
if [[ -n "$EMAIL" ]]; then
  CERTBOT_ARGS+=(-m "$EMAIL")
else
  CERTBOT_ARGS+=(--register-unsafely-without-email)
fi

certbot "${CERTBOT_ARGS[@]}"
nginx -t && systemctl reload nginx

echo "Renewal timer:"
systemctl status certbot.timer --no-pager | head -5
certbot renew --dry-run --cert-name "${DOMAIN}" 2>/dev/null || certbot renew --dry-run

echo ""
echo "OK: https://${DOMAIN}/"
curl -sf "https://${DOMAIN}/" | head -c 200
echo ""
