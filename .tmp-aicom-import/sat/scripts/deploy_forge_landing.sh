#!/usr/bin/env bash
# Deploy the HEPHAESTUS landing to forge.modelmarket.dev on the HUB host
# (same origin as modelmarket.dev / studio). This is NOT BASANOS.
#
# On the Hub:
#   sudo ./scripts/deploy_forge_landing.sh --local
# From a laptop:
#   ./scripts/deploy_forge_landing.sh --remote USER@HOST [--identity PATH]
#
# DNS: A record  forge  →  Hub IP (same as modelmarket.dev). Not hunt.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE="$ROOT/hephaestus/docs/landing"
NGINX_SOURCE="$ROOT/deploy/nginx/forge.modelmarket.dev.conf"
DOMAIN="forge.modelmarket.dev"
WEB_ROOT="/var/www/${DOMAIN}"
REMOTE=""
IDENTITY=""
LOCAL=0
EMAIL="${CERTBOT_EMAIL:-}"

usage() {
  sed -n '2,10p' "$0"
  echo "Usage: $0 --remote USER@HOST [--identity PATH] | --local"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --remote) REMOTE="${2:-}"; shift 2 ;;
    --identity) IDENTITY="${2:-}"; shift 2 ;;
    --local) LOCAL=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done

install_http_bootstrap() {
  cat > "/etc/nginx/sites-available/${DOMAIN}" <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN};
    root ${WEB_ROOT};
    index index.html;
    client_max_body_size 1m;
    location ^~ /.well-known/acme-challenge/ {
        root /var/www/certbot;
        default_type "text/plain";
        try_files \$uri =404;
    }
    location / {
        try_files \$uri \$uri/ /index.html;
    }
}
EOF
}

wire_nginx() {
  mkdir -p "$WEB_ROOT" /var/www/certbot
  if [[ -f "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" ]]; then
    install -m 0644 "$NGINX_SOURCE" "/etc/nginx/sites-available/${DOMAIN}"
  else
    install_http_bootstrap
  fi
  ln -sf "/etc/nginx/sites-available/${DOMAIN}" "/etc/nginx/sites-enabled/${DOMAIN}"
  nginx -t
  systemctl reload nginx

  host_ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
  dns_ip="$(dig +short "$DOMAIN" A 2>/dev/null | tail -n1 || true)"
  if [[ -n "$dns_ip" && -n "$host_ip" && "$dns_ip" != "$host_ip" ]]; then
    echo "DNS ${DOMAIN} → ${dns_ip}, this Hub host is ${host_ip}."
    echo "Landing is on disk. Flip the A record to the Hub, then re-run for TLS."
    return 0
  fi
  if [[ ! -f "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" ]]; then
    if ! command -v certbot >/dev/null; then
      apt-get install -y -qq certbot python3-certbot-nginx
    fi
    CERTBOT_ARGS=(--nginx --non-interactive --agree-tos --redirect --cert-name "${DOMAIN}" -d "${DOMAIN}")
    if [[ -n "$EMAIL" ]]; then CERTBOT_ARGS+=(-m "$EMAIL"); else CERTBOT_ARGS+=(--register-unsafely-without-email); fi
    certbot "${CERTBOT_ARGS[@]}"
    install -m 0644 "$NGINX_SOURCE" "/etc/nginx/sites-available/${DOMAIN}"
    nginx -t
    systemctl reload nginx
  fi
  echo "HEPHAESTUS landing at https://${DOMAIN}/"
}

if [[ "$LOCAL" -eq 1 ]]; then
  if [[ "$(id -u)" -ne 0 ]]; then
    echo "Run --local as root on the Hub host: sudo $0 --local" >&2
    exit 1
  fi
  [[ -f "$SOURCE/index.html" ]] || { echo "missing landing: $SOURCE/index.html" >&2; exit 1; }
  [[ -f "$NGINX_SOURCE" ]] || { echo "missing nginx: $NGINX_SOURCE" >&2; exit 1; }
  grep -q "HEPHAESTUS" "$SOURCE/index.html" || { echo "landing is not HEPHAESTUS" >&2; exit 1; }
  rsync -a --delete --exclude '.well-known' "$SOURCE/" "$WEB_ROOT/"
  if [[ -d "$ROOT/hephaestus/docs/screenshots" ]]; then
    rsync -a "$ROOT/hephaestus/docs/screenshots/" "$WEB_ROOT/screenshots/"
  fi
  wire_nginx
  exit 0
fi

[[ -f "$SOURCE/index.html" && -f "$NGINX_SOURCE" ]] || { echo "incomplete source tree" >&2; exit 1; }
grep -q "HEPHAESTUS" "$SOURCE/index.html" || { echo "landing is not HEPHAESTUS" >&2; exit 1; }
[[ "$REMOTE" =~ ^[A-Za-z0-9._-]+@[A-Za-z0-9._-]+$ ]] \
  || { echo "--remote must be an explicit USER@HOST (or pass --local)" >&2; exit 2; }

ssh_args=(-o BatchMode=yes -o ConnectTimeout=15)
rsync_rsh="ssh -o BatchMode=yes -o ConnectTimeout=15"
if [[ -n "$IDENTITY" ]]; then
  [[ "$IDENTITY" =~ ^[A-Za-z0-9_./-]+$ && -f "$IDENTITY" ]] \
    || { echo "--identity must name an existing path" >&2; exit 2; }
  ssh_args+=(-i "$IDENTITY" -o IdentitiesOnly=yes)
  rsync_rsh+=" -i $IDENTITY -o IdentitiesOnly=yes"
fi

ssh "${ssh_args[@]}" "$REMOTE" "mkdir -p '$WEB_ROOT' /var/www/certbot /etc/nginx/sites-available /etc/nginx/sites-enabled"
rsync -az --delete -e "$rsync_rsh" \
  --exclude '.well-known' \
  "$SOURCE/" "$REMOTE:$WEB_ROOT/"
if [[ -d "$ROOT/hephaestus/docs/screenshots" ]]; then
  rsync -az -e "$rsync_rsh" \
    "$ROOT/hephaestus/docs/screenshots/" "$REMOTE:$WEB_ROOT/screenshots/"
fi
scp "${ssh_args[@]}" "$NGINX_SOURCE" "$REMOTE:/tmp/${DOMAIN}.conf.next"

# shellcheck disable=SC2087
ssh "${ssh_args[@]}" "$REMOTE" bash -s -- "$DOMAIN" "$WEB_ROOT" "$EMAIL" <<'REMOTE'
set -euo pipefail
DOMAIN="${1:?domain required}"
WEB_ROOT="${2:?web root required}"
EMAIL="${3:-}"
as_root() { if [[ "$(id -u)" -eq 0 ]]; then "$@"; else sudo "$@"; fi; }
as_root mkdir -p "$WEB_ROOT" /var/www/certbot
if as_root test -f "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem"; then
  as_root install -m 0644 "/tmp/${DOMAIN}.conf.next" "/etc/nginx/sites-available/${DOMAIN}"
else
  as_root tee "/etc/nginx/sites-available/${DOMAIN}" >/dev/null <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN};
    root ${WEB_ROOT};
    index index.html;
    client_max_body_size 1m;
    location ^~ /.well-known/acme-challenge/ {
        root /var/www/certbot;
        default_type "text/plain";
        try_files \$uri =404;
    }
    location / {
        try_files \$uri \$uri/ /index.html;
    }
}
EOF
fi
as_root ln -sf "/etc/nginx/sites-available/${DOMAIN}" "/etc/nginx/sites-enabled/${DOMAIN}"
as_root nginx -t
as_root systemctl reload nginx
host_ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
dns_ip="$(dig +short "$DOMAIN" A 2>/dev/null | tail -n1 || true)"
if [[ -n "$dns_ip" && -n "$host_ip" && "$dns_ip" != "$host_ip" ]]; then
  echo "DNS ${DOMAIN} → ${dns_ip}, this Hub host is ${host_ip}."
  echo "Landing is on disk. Flip the A record to the Hub, then re-run for TLS."
  exit 0
fi
if ! as_root test -f "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem"; then
  command -v certbot >/dev/null || as_root apt-get install -y -qq certbot python3-certbot-nginx
  extra=(--register-unsafely-without-email)
  if [[ -n "${EMAIL:-}" ]]; then extra=(-m "$EMAIL"); fi
  as_root certbot --nginx --non-interactive --agree-tos --redirect --cert-name "$DOMAIN" -d "$DOMAIN" "${extra[@]}"
  as_root install -m 0644 "/tmp/${DOMAIN}.conf.next" "/etc/nginx/sites-available/${DOMAIN}"
  as_root nginx -t
  as_root systemctl reload nginx
fi
echo "HEPHAESTUS landing installed for ${DOMAIN}"
REMOTE

echo "Landing synced to ${REMOTE}:${WEB_ROOT}"
