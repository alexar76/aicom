#!/usr/bin/env bash
# Deploy AIMarket Playground on the ORACLE HOST (203.0.113.20 / admin-vps),
# published at https://play.modelmarket.dev/
#
#   sudo ./scripts/deploy_playground.sh              # build + up + nginx + TLS
#   sudo ./scripts/deploy_playground.sh --no-tls     # skip certbot (HTTP only)
#   sudo CERTBOT_EMAIL=you@x.dev ./scripts/deploy_playground.sh
#
# Prereqs:
#   * DNS A record  play.modelmarket.dev → 203.0.113.20  (not the factory 212)
#   * Docker + docker compose, nginx, certbot (oracle host already has them)
#   * PLAYGROUND_METIS_KEY in aimarket-playground/.env (or monorepo .env) —
#     Metis rejects unauthenticated /v1/chat/completions (401). Copy the live
#     METIS_API_KEY from the Metis host; never put it in the browser.
#
# Idempotent: re-run after a pull. Loopback-only container; nginx is the TLS edge.
# certbot.timer (or /etc/cron.d/certbot) renews the lineage automatically.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOMAIN="${PLAYGROUND_PUBLIC_DOMAIN:-play.modelmarket.dev}"
COMPOSE_DIR="$ROOT/aimarket-playground"
COMPOSE="$COMPOSE_DIR/docker-compose.yml"
NGINX_CONF_SRC="$ROOT/deploy/nginx/play.modelmarket.dev.conf"
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
  echo "Run as root on the oracle host (203.0.113.20): sudo $0" >&2
  exit 1
fi

# Refuse accidental deploy on the factory box (modelmarket.dev / 212).
HOST_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
if [[ "${HOST_IP}" == "203.0.113.10" ]]; then
  echo "ERROR: this host is the factory (203.0.113.10). Playground lives on 203.0.113.20." >&2
  exit 1
fi

if [[ ! -f "$COMPOSE" ]]; then
  echo "ERROR: missing $COMPOSE — sync aimarket-playground/ onto this host first." >&2
  exit 1
fi
if [[ ! -f "$NGINX_CONF_SRC" ]]; then
  echo "ERROR: missing $NGINX_CONF_SRC" >&2
  exit 1
fi

echo "=== Playground deploy → https://${DOMAIN} (oracle host) ==="

if ! docker network inspect ecosystem >/dev/null 2>&1; then
  echo "Creating shared 'ecosystem' docker network (was absent)…"
  docker network create ecosystem
fi

COMPOSE_ENV=()
if [[ -f "$COMPOSE_DIR/.env" ]]; then
  COMPOSE_ENV+=(--env-file "$COMPOSE_DIR/.env")
elif [[ -f "$ROOT/.env" ]]; then
  COMPOSE_ENV+=(--env-file "$ROOT/.env")
fi

_env_has_metis_key=0
for f in "$COMPOSE_DIR/.env" "$ROOT/.env"; do
  if [[ -f "$f" ]] && grep -qE '^PLAYGROUND_METIS_KEY=.+' "$f"; then
    _env_has_metis_key=1
    break
  fi
done
if [[ "$_env_has_metis_key" -ne 1 ]]; then
  echo "WARN: PLAYGROUND_METIS_KEY not set in aimarket-playground/.env or monorepo .env." >&2
  echo "      Metis returns 401 without it — copy METIS_API_KEY from the Metis host." >&2
fi

echo "Building + starting playground (127.0.0.1:8075)…"
docker compose -f "$COMPOSE" "${COMPOSE_ENV[@]}" up -d --build

echo -n "Waiting for playground health on 127.0.0.1:8075 "
for i in $(seq 1 45); do
  if curl -sf --max-time 3 http://127.0.0.1:8075/health >/dev/null; then
    echo "— ok"; break
  fi
  echo -n "."; sleep 1
  if [[ "$i" -eq 45 ]]; then
    echo
    echo "playground did not become healthy; check: docker compose -f $COMPOSE logs playground" >&2
    exit 1
  fi
done

if ! command -v nginx >/dev/null; then
  apt-get update -qq && apt-get install -y -qq nginx
fi
mkdir -p /var/www/certbot

install_http_bootstrap() {
  # ACME-only :80 until the lineage exists — full HTTPS conf fails nginx -t without PEMs.
  cat >"$NGINX_AVAIL" <<EOF
upstream playground_app { server 127.0.0.1:8075; keepalive 4; }
server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN};
    location ^~ /.well-known/acme-challenge/ {
        root /var/www/certbot;
        default_type "text/plain";
        try_files \$uri =404;
    }
    location = /health {
        proxy_pass http://playground_app;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
    location / {
        proxy_pass http://playground_app;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF
}

install_full_nginx() {
  install -m 0644 "$NGINX_CONF_SRC" "$NGINX_AVAIL"
}

CERT_LIVE="/etc/letsencrypt/live/${DOMAIN}/fullchain.pem"
ln -sf "$NGINX_AVAIL" "$NGINX_ENABLED"

if [[ "$DO_TLS" -eq 1 && ! -f "$CERT_LIVE" ]]; then
  install_http_bootstrap
else
  install_full_nginx
fi

nginx -t
systemctl enable nginx >/dev/null 2>&1 || true
systemctl reload nginx

if [[ "$DO_TLS" -eq 1 ]]; then
  if ! command -v certbot >/dev/null; then
    apt-get install -y -qq certbot python3-certbot-nginx
  fi
  if [[ -f "$CERT_LIVE" ]]; then
    echo "TLS lineage ${DOMAIN} already present — keeping repo nginx conf."
  else
    if ! getent hosts "$DOMAIN" >/dev/null 2>&1; then
      echo "ERROR: ${DOMAIN} does not resolve yet — add DNS A → this host, then re-run." >&2
      exit 1
    fi
    for _ in $(seq 1 12); do
      if [[ ! -e /var/lib/letsencrypt/.certbot.lock && ! -e /tmp/certbot.lock ]]; then
        break
      fi
      echo "certbot lock held — waiting"
      sleep 5
    done
    CERTBOT_ARGS=(certonly --webroot -w /var/www/certbot --non-interactive --agree-tos --cert-name "${DOMAIN}" -d "${DOMAIN}")
    if [[ -n "$EMAIL" ]]; then CERTBOT_ARGS+=(-m "$EMAIL"); else CERTBOT_ARGS+=(--register-unsafely-without-email); fi
    certbot "${CERTBOT_ARGS[@]}"
  fi
  [[ -f "$CERT_LIVE" ]] || { echo "ERROR: missing $CERT_LIVE" >&2; exit 1; }
  install_full_nginx
  nginx -t
  systemctl reload nginx

  systemctl enable --now certbot.timer >/dev/null 2>&1 || true
  if systemctl is-active --quiet certbot.timer 2>/dev/null; then
    echo "certbot.timer active — certificates renew automatically."
  elif [[ -f /etc/cron.d/certbot ]]; then
    echo "certbot cron present at /etc/cron.d/certbot — renewal scheduled."
  else
    echo "WARN: no certbot.timer/cron found — install certbot package for auto-renew." >&2
  fi
else
  echo "Skipping certbot (--no-tls). Serving plain HTTP on :80."
fi

echo
echo "=== Playground live ==="
echo "  UI:      https://${DOMAIN}/"
echo "  Health:  https://${DOMAIN}/health"
echo "  API:     POST https://${DOMAIN}/api/playground/runs"
echo
echo "Verify from OUTSIDE the host:"
echo "  curl -sS https://${DOMAIN}/health"
echo
echo "This service must NOT run on the factory (203.0.113.10)."
