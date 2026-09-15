#!/usr/bin/env bash
# Deploy the WARDEN landing to its nginx web root.
#
#   ./scripts/deploy_warden_landing.sh --remote root@warden-host [--install-nginx] [--issue-cert]
#
# The landing is ONE self-contained document (five languages inlined, no external
# assets), so there is nothing to stage in order: a single atomic file replaces the
# previous release. The package's own suite is what validates it — landing.test.ts
# checks the quoted ruleset, survey figures and test count against the code and the
# docs they describe — so this script runs that first and refuses to publish numbers
# nobody verified.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE="$ROOT/warden/docs/landing/index.html"
NGINX_SOURCE="$ROOT/deploy/nginx/warden.modelmarket.dev.conf"
REMOTE=""
IDENTITY=""
INSTALL_NGINX=0
ISSUE_CERT=0
HOST="warden.modelmarket.dev"
REMOTE_ROOT="/var/www/$HOST"

usage() { sed -n '2,12p' "$0"; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --remote) REMOTE="${2:-}"; shift 2 ;;
    --identity) IDENTITY="${2:-}"; shift 2 ;;
    --install-nginx) INSTALL_NGINX=1; shift ;;
    --issue-cert) ISSUE_CERT=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done

[[ "$REMOTE" =~ ^[A-Za-z0-9._-]+@[A-Za-z0-9._-]+$ ]] \
  || { echo "--remote must be an explicit USER@HOST" >&2; exit 2; }
[[ -f "$SOURCE" ]] || { echo "missing landing: $SOURCE" >&2; exit 1; }
[[ -f "$NGINX_SOURCE" ]] || { echo "missing nginx config: $NGINX_SOURCE" >&2; exit 1; }

echo "== verify the page against the code it describes =="
(cd "$ROOT/warden" && npx vitest run test/landing.test.ts)

ssh_args=(-o BatchMode=yes -o ConnectTimeout=10)
rsync_rsh="ssh -o BatchMode=yes -o ConnectTimeout=10"
if [[ -n "$IDENTITY" ]]; then
  ssh_args+=(-i "$IDENTITY" -o IdentitiesOnly=yes)
  rsync_rsh+=" -i $IDENTITY -o IdentitiesOnly=yes"
fi
remote_exec() { ssh "${ssh_args[@]}" "$REMOTE" "$@"; }

remote_exec "set -eu
mkdir -p '$REMOTE_ROOT'
test ! -L '$REMOTE_ROOT'"

if [[ "$ISSUE_CERT" -eq 1 ]]; then
  # The 80-only server block has to exist before certbot can answer the challenge,
  # so a first-time issue installs an HTTP-only site, gets the cert, then installs
  # the real config. Without that order nginx -t fails on a missing certificate and
  # the deploy looks broken when it is only unsequenced.
  remote_exec "set -eu
  mkdir -p /var/www/certbot
  if [ ! -d /etc/letsencrypt/live/$HOST ]; then
    cat > /etc/nginx/sites-available/$HOST <<'BOOTSTRAP'
server {
    listen 80;
    listen [::]:80;
    server_name $HOST;
    root $REMOTE_ROOT;
    location /.well-known/acme-challenge/ { root /var/www/certbot; }
    location / { try_files \\\$uri \\\$uri/ /index.html; }
}
BOOTSTRAP
    ln -sf /etc/nginx/sites-available/$HOST /etc/nginx/sites-enabled/$HOST
    nginx -t && systemctl reload nginx
    certbot certonly --webroot -w /var/www/certbot -d $HOST --non-interactive --agree-tos --register-unsafely-without-email
  else
    echo 'certificate already present'
  fi"
fi

rsync -az -e "$rsync_rsh" "$SOURCE" "$REMOTE:$REMOTE_ROOT/index.html"

if [[ "$INSTALL_NGINX" -eq 1 ]]; then
  scp "${ssh_args[@]}" "$NGINX_SOURCE" "$REMOTE:/tmp/$HOST.conf.next"
  scp "${ssh_args[@]}" "$ROOT/deploy/nginx/warden-security-headers.conf" "$REMOTE:/tmp/warden-security-headers.conf.next"
  remote_exec "set -eu
  mkdir -p /etc/nginx/snippets
  install -m 0644 /tmp/warden-security-headers.conf.next /etc/nginx/snippets/warden-security-headers.conf"
  remote_exec "set -eu
  target=/etc/nginx/sites-available/$HOST
  if [ -f \"\$target\" ] && [ ! -L \"\$target\" ]; then
    cp -p \"\$target\" \"\${target}.bak.\$(date +%Y%m%d%H%M%S)\"
  fi
  install -m 0644 /tmp/$HOST.conf.next \"\$target\"
  ln -sf \"\$target\" /etc/nginx/sites-enabled/$HOST
  if nginx -t; then
    systemctl reload nginx
    echo 'nginx reloaded'
  else
    nginx -t
    echo 'nginx config rejected' >&2
    exit 1
  fi"
fi

local_sum="$(shasum -a 256 "$SOURCE" | awk '{print $1}')"
remote_sum="$(remote_exec "sha256sum '$REMOTE_ROOT/index.html'" | awk '{print $1}')"
[[ "$local_sum" == "$remote_sum" ]] || { echo "checksum mismatch after upload" >&2; exit 1; }

curl -fsS "https://$HOST/" >/dev/null
# A header written in a config is not a header a browser received.
headers="$(curl -fsSI "https://$HOST/")"
for required in "content-security-policy" "x-content-type-options"; do
  printf '%s' "$headers" | grep -iq "$required" \
    || { echo "missing response header: $required" >&2; exit 1; }
done
echo "WARDEN landing deployed: https://$HOST/  (CSP + nosniff verified on the wire)"
