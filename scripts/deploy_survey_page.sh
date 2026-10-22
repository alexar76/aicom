#!/usr/bin/env bash
# Deploy the x402 delivery survey page to survey.modelmarket.dev.
# Same host as verify.modelmarket.dev and dolos.modelmarket.dev.
#
# From a laptop, after the Timeweb A record survey → that host:
#   ./scripts/deploy_survey_page.sh --remote root@factory-vps --issue-cert
#
# On the host:
#   sudo ./scripts/deploy_survey_page.sh --local --issue-cert
#
# Does not install the unpaid systemd timer. Does not run a purchase.
# Never uploads buy.jsonl.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE="$ROOT/scripts/delivery-survey/site"
ROW="$ROOT/scripts/delivery-survey/results/2026-10-20.json"
NGINX_SOURCE="$ROOT/deploy/nginx/survey.modelmarket.dev.conf"
DOMAIN="survey.modelmarket.dev"
WEB_ROOT="/var/www/${DOMAIN}"
TX="0x62c01526c5beb13cad96634ec80e837e576df496905f1bac8019c6ffa3e358c3"
REMOTE=""
IDENTITY=""
LOCAL=0
ISSUE_CERT=0
EMAIL="${CERTBOT_EMAIL:-}"
# ssh drops an empty argv slot, which would shift --issue-cert into the email field.
SSH_EMAIL="${EMAIL:--}"

usage() {
  sed -n '2,12p' "$0"
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

[[ -f "$SOURCE/index.html" && -f "$NGINX_SOURCE" && -f "$ROW" ]] \
  || { echo "incomplete source: need the page, the 2026-10-20 row, and the nginx conf" >&2; exit 1; }
grep -q "$TX" "$SOURCE/index.html" || { echo "page is missing the settled transaction" >&2; exit 1; }
grep -q "$TX" "$ROW" || { echo "row is missing the settled transaction" >&2; exit 1; }

python3 - "$ROOT" <<'PY'
import json, pathlib, sys
root = pathlib.Path(sys.argv[1])
blob = "\n".join([
    (root / "scripts/delivery-survey/site/index.html").read_text(),
    (root / "scripts/delivery-survey/results/2026-10-20.json").read_text(),
    (root / "deploy/nginx/survey.modelmarket.dev.conf").read_text(),
    (root / "scripts/deploy_survey_page.sh").read_text(),
])
buy = root / "scripts/delivery-survey/buy.jsonl"
if buy.is_file():
    for line in buy.read_text().splitlines():
        if not line.strip():
            continue
        signed = json.loads(line).get("signed") or {}
        frm = signed.get("from")
        if isinstance(frm, str) and frm.lower() in blob.lower():
            sys.exit("refusing: payer address is in the public survey files")
if "buy.jsonl" in (root / "scripts/delivery-survey/site/index.html").read_text():
    sys.exit("refusing: page names the private purchase log")
PY

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
    echo "DNS ${DOMAIN} → ${dns_ip}, this host is ${host_ip}."
    echo "Files are on disk. Point the A record at this host, then re-run with --issue-cert."
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
  echo "Survey page at https://${DOMAIN}/ (or http:// until TLS)"
}

upload_local() {
  mkdir -p "$WEB_ROOT"
  rsync -a --exclude '.well-known' --exclude 'buy.jsonl' "$SOURCE/" "$WEB_ROOT/"
  install -m 0644 "$ROW" "$WEB_ROOT/2026-10-20.json"
}

if [[ "$LOCAL" -eq 1 ]]; then
  if [[ "$(id -u)" -ne 0 ]]; then
    echo "Run --local as root on the factory host: sudo $0 --local" >&2
    exit 1
  fi
  upload_local
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
rsync -az --exclude '.well-known' --exclude 'buy.jsonl' -e "$rsync_rsh" \
  "$SOURCE/" "$REMOTE:$WEB_ROOT/"
scp "${ssh_args[@]}" "$ROW" "$REMOTE:$WEB_ROOT/2026-10-20.json"
scp "${ssh_args[@]}" "$NGINX_SOURCE" "$REMOTE:/tmp/${DOMAIN}.conf.next"

# shellcheck disable=SC2087
ssh "${ssh_args[@]}" "$REMOTE" bash -s -- "$DOMAIN" "$WEB_ROOT" "$SSH_EMAIL" "$ISSUE_CERT" <<'REMOTE'
set -euo pipefail
DOMAIN="${1:?domain required}"
WEB_ROOT="${2:?web root required}"
EMAIL="${3:-}"
ISSUE_CERT="${4:-0}"
if [[ "$EMAIL" == "-" ]]; then EMAIL=""; fi
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
  echo "DNS ${DOMAIN} → ${dns_ip}, this host is ${host_ip}."
  echo "Landing is on disk. Point the A record at this host, then re-run with --issue-cert."
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
echo "Survey page ready on this host (${WEB_ROOT})"
REMOTE

echo
echo "Smoke (host local):"
ssh "${ssh_args[@]}" "$REMOTE" "curl -sfm5 -o /dev/null -w 'local %{http_code}\n' -H 'Host: ${DOMAIN}' http://127.0.0.1/ || true"
echo "Public: https://${DOMAIN}/  (needs DNS A → this host + --issue-cert)"
