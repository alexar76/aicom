#!/usr/bin/env bash
# Deploy the DOLOS landing to dolos.modelmarket.dev on the Hub host
# (same origin as forge.modelmarket.dev / modelmarket.dev).
#
# From a laptop:
#   ./scripts/deploy_dolos_landing.sh --remote root@my-vps \
#     --identity ~/.ssh/id_ed25519_factory [--issue-cert]
#
# On the Hub:
#   sudo ./scripts/deploy_dolos_landing.sh --local [--issue-cert]
#
# DNS: A record  dolos  →  Hub IP (same as forge.modelmarket.dev).
# First TLS: pass --issue-cert once DNS points here.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE="$ROOT/dolos/docs/landing"
NGINX_SOURCE="$ROOT/deploy/nginx/dolos.modelmarket.dev.conf"
DOMAIN="dolos.modelmarket.dev"
WEB_ROOT="/var/www/${DOMAIN}"
REMOTE=""
IDENTITY=""
LOCAL=0
ISSUE_CERT=0
EMAIL="${CERTBOT_EMAIL:-}"

usage() {
  sed -n '2,14p' "$0"
  echo "Usage: $0 --remote USER@HOST [--identity PATH] [--issue-cert] | --local [--issue-cert]"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --remote) REMOTE="${2:-}"; shift 2 ;;
    --identity) IDENTITY="${2:-}"; shift 2 ;;
    --local) LOCAL=1; shift ;;
    --issue-cert) ISSUE_CERT=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done

[[ -f "$SOURCE/index.html" && -f "$NGINX_SOURCE" ]] \
  || { echo "incomplete source: need $SOURCE/index.html and $NGINX_SOURCE" >&2; exit 1; }
grep -qi "DOLOS" "$SOURCE/index.html" || { echo "landing does not look like DOLOS" >&2; exit 1; }

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
    echo "Files are on disk. Point the A record at the Hub, then re-run with --issue-cert."
    return 0
  fi
  if [[ "$ISSUE_CERT" -eq 1 && ! -f "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" ]]; then
    if [[ -z "$dns_ip" ]]; then
      echo "No A record for ${DOMAIN} yet — skipping certbot." >&2
      return 0
    fi
    if ! command -v certbot >/dev/null; then
      apt-get install -y -qq certbot python3-certbot-nginx
    fi
    CERTBOT_ARGS=(--nginx --non-interactive --agree-tos --redirect --cert-name "${DOMAIN}" -d "${DOMAIN}")
    if [[ -n "$EMAIL" ]]; then CERTBOT_ARGS+=(-m "$EMAIL"); else CERTBOT_ARGS+=(--register-unsafely-without-email); fi
    certbot "${CERTBOT_ARGS[@]}"
    install -m 0644 "$NGINX_SOURCE" "/etc/nginx/sites-available/${DOMAIN}"
    nginx -t
    systemctl reload nginx
    systemctl enable --now certbot.timer >/dev/null 2>&1 || true
  fi
  echo "DOLOS landing at https://${DOMAIN}/ (or http:// until TLS)"
}

upload_files() {
  local dest="$1"
  rsync -a --delete --exclude '.well-known' "$SOURCE/" "$dest/"
}

if [[ "$LOCAL" -eq 1 ]]; then
  if [[ "$(id -u)" -ne 0 ]]; then
    echo "Run --local as root on the Hub host: sudo $0 --local" >&2
    exit 1
  fi
  upload_files "$WEB_ROOT"
  wire_nginx
  exit 0
fi

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

echo "== upload → ${REMOTE}:${WEB_ROOT} =="
ssh "${ssh_args[@]}" "$REMOTE" "mkdir -p '$WEB_ROOT' /var/www/certbot /etc/nginx/sites-available /etc/nginx/sites-enabled"
rsync -az --delete -e "$rsync_rsh" \
  --exclude '.well-known' \
  "$SOURCE/" "$REMOTE:$WEB_ROOT/"
scp "${ssh_args[@]}" "$NGINX_SOURCE" "$REMOTE:/tmp/${DOMAIN}.conf.next"

# shellcheck disable=SC2087
ssh "${ssh_args[@]}" "$REMOTE" bash -s -- "$DOMAIN" "$WEB_ROOT" "$EMAIL" "$ISSUE_CERT" <<'REMOTE'
set -euo pipefail
DOMAIN="${1:?domain required}"
WEB_ROOT="${2:?web root required}"
EMAIL="${3:-}"
ISSUE_CERT="${4:-0}"
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
  echo "Landing is on disk. Flip the A record to the Hub, then re-run with --issue-cert."
  exit 0
fi
if [[ "$ISSUE_CERT" == "1" && ! -f "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" ]]; then
  if [[ -z "$dns_ip" ]]; then
    echo "No A record for ${DOMAIN} yet — files served on :80 once DNS points here; re-run --issue-cert after."
    exit 0
  fi
  if ! command -v certbot >/dev/null; then
    as_root apt-get install -y -qq certbot python3-certbot-nginx
  fi
  CERTBOT_ARGS=(--nginx --non-interactive --agree-tos --redirect --cert-name "${DOMAIN}" -d "${DOMAIN}")
  if [[ -n "$EMAIL" ]]; then CERTBOT_ARGS+=(-m "$EMAIL"); else CERTBOT_ARGS+=(--register-unsafely-without-email); fi
  as_root certbot "${CERTBOT_ARGS[@]}"
  as_root install -m 0644 "/tmp/${DOMAIN}.conf.next" "/etc/nginx/sites-available/${DOMAIN}"
  as_root nginx -t
  as_root systemctl reload nginx
  as_root systemctl enable --now certbot.timer >/dev/null 2>&1 || true
fi
echo "DOLOS landing ready on this host (${WEB_ROOT})"
REMOTE

echo
echo "Smoke (Hub local):"
ssh "${ssh_args[@]}" "$REMOTE" "curl -sfm5 -o /dev/null -w 'local %{http_code}\n' -H 'Host: ${DOMAIN}' http://127.0.0.1/ || true"
echo "Public: https://${DOMAIN}/  (needs DNS A → Hub + --issue-cert)"
echo "GitHub Pages: https://alexar76.github.io/dolos/"
