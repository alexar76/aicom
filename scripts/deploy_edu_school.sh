#!/usr/bin/env bash
# edu.modelmarket.dev — AIMarket School portal (static) + Let's Encrypt.
#
#   sudo ./scripts/deploy_edu_school.sh
#   CERTBOT_EMAIL=you@example.com sudo ./scripts/deploy_edu_school.sh
#
# Or from a laptop (rsync + remote nginx/certbot):
#   ./scripts/deploy_edu_school.sh --remote my-vps
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DOMAIN="edu.modelmarket.dev"
WEB_ROOT="/var/www/${DOMAIN}"
SRC="${ROOT}/edu-landing"
NGINX_SRC="${ROOT}/deploy/nginx/${DOMAIN}.conf"
# Same-origin hub bridge — the site conf includes it, so it must ship too.
SNIPPET_SRC="${ROOT}/deploy/nginx/snippets/school-hub-bridge.conf"
# Its rate-limit zone lives at http level (conf.d), declared exactly once.
ZONE_SRC="${ROOT}/deploy/nginx/snippets/school-hub-zone.conf"
REMOTE=""

if [[ "${1:-}" == "--remote" ]]; then
  REMOTE="${2:-my-vps}"
fi

build_site() {
  echo "Building School for https://${DOMAIN}/ ..."
  SEO_BASE_URL="https://${DOMAIN}" \
  SCHOOL_MOUNT="" \
  SCHOOL_OUT="edu-landing" \
  LEARN_BASE="https://modeldev.modelmarket.dev" \
    python3 "${ROOT}/school/build.py"
}

install_local() {
  if [[ "$(id -u)" -ne 0 ]]; then
    echo "Run as root: sudo $0" >&2
    exit 1
  fi
  build_site
  mkdir -p "${WEB_ROOT}"
  rsync -a --delete "${SRC}/" "${WEB_ROOT}/"
  if getent passwd www-data >/dev/null 2>&1; then
    chown -R www-data:www-data "${WEB_ROOT}"
  fi
  mkdir -p /etc/nginx/snippets /etc/nginx/conf.d
  cp "${SNIPPET_SRC}" /etc/nginx/snippets/school-hub-bridge.conf
  cp "${ZONE_SRC}" /etc/nginx/conf.d/school-hub-zone.conf
  cp "${NGINX_SRC}" "/etc/nginx/sites-available/${DOMAIN}"
  ln -sf "/etc/nginx/sites-available/${DOMAIN}" "/etc/nginx/sites-enabled/${DOMAIN}"
  nginx -t
  systemctl reload nginx

  if [[ -f "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" ]]; then
    certbot install --cert-name "${DOMAIN}" --nginx --reinstall --non-interactive \
      || certbot --nginx -d "${DOMAIN}" --non-interactive --redirect --reinstall \
      || true
  else
    CERTBOT_ARGS=(--nginx --non-interactive --agree-tos --redirect -d "${DOMAIN}")
    if [[ -n "${CERTBOT_EMAIL:-}" ]]; then
      CERTBOT_ARGS+=(-m "${CERTBOT_EMAIL}")
    else
      CERTBOT_ARGS+=(--register-unsafely-without-email)
    fi
    certbot "${CERTBOT_ARGS[@]}"
  fi
  nginx -t && systemctl reload nginx
  echo "OK: https://${DOMAIN}/"
  curl -sf "https://${DOMAIN}/" | head -c 180 || true
  echo
}

install_remote() {
  build_site
  echo "Rsync → ${REMOTE}:${WEB_ROOT}/ ..."
  ssh "${REMOTE}" "mkdir -p '${WEB_ROOT}'"
  rsync -az --delete "${SRC}/" "${REMOTE}:${WEB_ROOT}/"
  scp "${NGINX_SRC}" "${REMOTE}:/tmp/${DOMAIN}.conf"
  scp "${SNIPPET_SRC}" "${REMOTE}:/tmp/school-hub-bridge.conf"
  scp "${ZONE_SRC}" "${REMOTE}:/tmp/school-hub-zone.conf"
  ssh "${REMOTE}" bash -s <<EOF
set -euo pipefail
mkdir -p /etc/nginx/snippets /etc/nginx/conf.d
cp /tmp/school-hub-bridge.conf /etc/nginx/snippets/school-hub-bridge.conf
cp /tmp/school-hub-zone.conf /etc/nginx/conf.d/school-hub-zone.conf
# Overwrite the full TLS vhost — do NOT re-run certbot --nginx here; it strips
# the /hub bridge include (that is what broke Try-it demos).
cp /tmp/${DOMAIN}.conf /etc/nginx/sites-available/${DOMAIN}
ln -sf /etc/nginx/sites-available/${DOMAIN} /etc/nginx/sites-enabled/${DOMAIN}
chown -R www-data:www-data '${WEB_ROOT}'
test -f /etc/letsencrypt/live/${DOMAIN}/fullchain.pem
nginx -t
systemctl reload nginx
curl -sf -o /dev/null -w 'https://${DOMAIN}/ → %{http_code}\\n' https://${DOMAIN}/ || true
code=\$(curl -s -o /tmp/hub-search.json -w '%{http_code}' "https://${DOMAIN}/hub/ai-market/v2/search?intent=oracle&limit=1" || true)
echo "https://${DOMAIN}/hub/…/search → \${code}"
head -c 120 /tmp/hub-search.json; echo
curl -sf https://${DOMAIN}/ | grep -o 'AIMarket' | head -1 || true
EOF
  echo "OK remote: https://${DOMAIN}/"
}

if [[ -n "${REMOTE}" ]]; then
  install_remote
elif [[ -d /var/www ]] && [[ -d /etc/nginx/sites-available ]]; then
  install_local
else
  echo "Not the web host — use: $0 --remote my-vps" >&2
  exit 1
fi
