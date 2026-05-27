#!/usr/bin/env bash
# modelmarket.dev — nginx vhost + AIMarket Hub (9083) + Let's Encrypt via certbot.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
EMAIL="${CERTBOT_EMAIL:-}"
DOMAINS=(modelmarket.dev www.modelmarket.dev)
HUB_PORT="${AIMARKET_HUB_HOST_PORT:-9083}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo $0" >&2
  exit 1
fi

if ! command -v certbot >/dev/null; then
  apt-get update -qq
  apt-get install -y -qq certbot python3-certbot-nginx
fi

systemctl enable certbot.timer
systemctl start certbot.timer

cp "$ROOT/deploy/nginx/modelmarket.dev.conf" /etc/nginx/sites-available/modelmarket.dev
ln -sf /etc/nginx/sites-available/modelmarket.dev /etc/nginx/sites-enabled/modelmarket.dev
nginx -t
systemctl reload nginx

echo "Building AIMarket Hub (repo root context)..."
docker build -f "$ROOT/aimarket-hub/Dockerfile" -t modelmarket-hub:latest "$ROOT"

docker rm -f modelmarket-hub 2>/dev/null || true
docker run -d --name modelmarket-hub --restart unless-stopped \
  -p "127.0.0.1:${HUB_PORT}:9083" \
  -e AIMARKET_HUB_NAME=modelmarket.dev \
  -e AIMARKET_HUB_URL="https://modelmarket.dev" \
  -e AIMARKET_SEED_LIST="https://magic-ai-factory.com/.well-known/ai-market.json" \
  -v modelmarket_hub_data:/app/data \
  modelmarket-hub:latest

for _ in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:${HUB_PORT}/.well-known/ai-market.json" >/dev/null; then
    break
  fi
  sleep 1
done

CERTBOT_ARGS=(--nginx --non-interactive --agree-tos --redirect)
for d in "${DOMAINS[@]}"; do CERTBOT_ARGS+=(-d "$d"); done
if [[ -n "$EMAIL" ]]; then
  CERTBOT_ARGS+=(-m "$EMAIL")
else
  CERTBOT_ARGS+=(--register-unsafely-without-email)
fi

certbot "${CERTBOT_ARGS[@]}"

nginx -t && systemctl reload nginx
certbot renew --dry-run --cert-name modelmarket.dev || certbot renew --dry-run

echo "Done. https://modelmarket.dev"
echo "Renewal: systemctl status certbot.timer"
