#!/usr/bin/env bash
# Deploy BASANOS — Solidity touchstone — on the ORACLE HOST, alongside MOMUS /
# LOGOS / GAIA, published on basanos.modelmarket.dev.
#
#   sudo ./scripts/deploy_basanos.sh
#   sudo ./scripts/deploy_basanos.sh --no-tls
#   sudo CERTBOT_EMAIL=you@x.dev ./scripts/deploy_basanos.sh
#
# Prereqs:
#   * DNS A record  basanos.modelmarket.dev → this host (oracle, not hunt, not Hub)
#   * Docker + compose, nginx, certbot
#   * shared `ecosystem` docker network
#   * monorepo checkout so ACEX / lottery / core sources are readable
#
# forge.modelmarket.dev is HEPHAESTUS and is deployed on the Hub host
# (scripts/deploy_forge_landing.sh). Do not put this vhost there.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOMAIN="${BASANOS_PUBLIC_DOMAIN:-basanos.modelmarket.dev}"
COMPOSE="$ROOT/basanos/docker-compose.yml"
NGINX_CONF_SRC="$ROOT/deploy/nginx/basanos.modelmarket.dev.conf"
NGINX_AVAIL="/etc/nginx/sites-available/${DOMAIN}"
NGINX_ENABLED="/etc/nginx/sites-enabled/${DOMAIN}"
EMAIL="${CERTBOT_EMAIL:-}"
DO_TLS=1
for arg in "$@"; do
  case "$arg" in
    --no-tls) DO_TLS=0 ;;
    -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
    *) echo "Unknown option: $arg" >&2; exit 1 ;;
  esac
done

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root on the oracle host: sudo $0" >&2
  exit 1
fi

echo "=== BASANOS deploy → https://${DOMAIN} (Solidity assurance) ==="

if ! docker network inspect ecosystem >/dev/null 2>&1; then
  echo "Creating shared 'ecosystem' docker network (was absent)…"
  docker network create ecosystem
fi

export BASANOS_CONTRACT_ROOT="${BASANOS_CONTRACT_ROOT:-$ROOT}"
echo "Building + starting basanos (127.0.0.1:9470), contracts from ${BASANOS_CONTRACT_ROOT}"
docker compose -f "$COMPOSE" up -d --build

echo -n "Waiting for basanos health on 127.0.0.1:9470 "
for i in $(seq 1 60); do
  if curl -sf --max-time 3 http://127.0.0.1:9470/health >/dev/null; then
    echo "— ok"; break
  fi
  echo -n "."
  sleep 1
  if [[ "$i" -eq 60 ]]; then
    echo
    echo "basanos did not become healthy; check: docker compose -f $COMPOSE logs basanos" >&2
    exit 1
  fi
done

health="$(curl -sf --max-time 5 http://127.0.0.1:9470/health)"
echo "$health" | grep -q '"agent":"basanos"' || {
  echo "health did not identify as basanos: $health" >&2
  exit 1
}

if ! command -v nginx >/dev/null; then
  apt-get update -qq && apt-get install -y -qq nginx
fi
mkdir -p /var/www/certbot

install_http_bootstrap() {
  cat > "$NGINX_AVAIL" <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN};
    client_max_body_size 1m;
    location ^~ /.well-known/acme-challenge/ {
        root /var/www/certbot;
        default_type "text/plain";
        try_files \$uri =404;
    }
    location / {
        proxy_pass http://127.0.0.1:9470;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF
}

host_ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
dns_ip="$(dig +short "$DOMAIN" A 2>/dev/null | tail -n1 || true)"
if [[ "$DO_TLS" -eq 1 && -n "$dns_ip" && -n "$host_ip" && "$dns_ip" != "$host_ip" ]]; then
  echo "DNS ${DOMAIN} → ${dns_ip}, this host is ${host_ip}."
  echo "Skipping certbot until the A record points at the oracle host."
  DO_TLS=0
fi

if [[ "$DO_TLS" -eq 1 && -f "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" ]]; then
  install -m 0644 "$NGINX_CONF_SRC" "$NGINX_AVAIL"
else
  install_http_bootstrap
fi
ln -sf "$NGINX_AVAIL" "$NGINX_ENABLED"
nginx -t
systemctl enable nginx >/dev/null 2>&1 || true
systemctl reload nginx

if [[ "$DO_TLS" -eq 1 ]]; then
  if ! command -v certbot >/dev/null; then
    apt-get install -y -qq certbot python3-certbot-nginx
  fi
  CERTBOT_ARGS=(--nginx --non-interactive --agree-tos --redirect --cert-name "${DOMAIN}" -d "${DOMAIN}")
  if [[ -n "$EMAIL" ]]; then CERTBOT_ARGS+=(-m "$EMAIL"); else CERTBOT_ARGS+=(--register-unsafely-without-email); fi
  certbot "${CERTBOT_ARGS[@]}"
  install -m 0644 "$NGINX_CONF_SRC" "$NGINX_AVAIL"
  nginx -t
  systemctl reload nginx
  systemctl enable --now certbot.timer >/dev/null 2>&1 || true
else
  echo "Serving plain HTTP on :80 (TLS skipped)."
fi

echo
echo "=== BASANOS on this host ==="
echo "  Health:  http://127.0.0.1:9470/health"
echo "  Public:  https://${DOMAIN}/  (after DNS + TLS)"
echo "  Invoke:  https://${DOMAIN}/invoke"
echo
echo "Verify from outside once the A record hits this host:"
echo "  curl -sS https://${DOMAIN}/health"
