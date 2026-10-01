#!/usr/bin/env bash
# Publish ecosystem-landing/ → https://modeldev.modelmarket.dev (static nginx).
#
#   ./scripts/deploy_ecosystem_landing.sh
#
# Called automatically from deploy_ecosystem.sh. Safe to run alone after editing
# ecosystem-landing/. Skips quietly when /var/www is absent (not the modeldev host).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOMAIN="modeldev.modelmarket.dev"
WEB_ROOT="/var/www/${DOMAIN}"
SRC="${ROOT}/ecosystem-landing"
NGINX_SITE="${ROOT}/deploy/nginx/${DOMAIN}.conf"
# The site conf includes this (same-origin hub bridge for /school/ demos);
# its rate-limit zone must be declared once at http level (conf.d).
NGINX_SNIPPET="${ROOT}/deploy/nginx/snippets/school-hub-bridge.conf"
NGINX_ZONE="${ROOT}/deploy/nginx/snippets/school-hub-zone.conf"

if [[ ! -d "$SRC" ]]; then
  echo "ERROR: $SRC not found" >&2
  exit 1
fi

# Rebuild SEO landings (learn · oracles · guides · encyclopedia · sitemap).
export SEO_BASE_URL="${SEO_BASE_URL:-https://${DOMAIN}}"
echo "Building SEO landings for ${SEO_BASE_URL} ..."
"${ROOT}/scripts/build_ecosystem_landing.sh"

_deploy_landing() {
  echo "Deploying ${SRC} → ${WEB_ROOT} ..."
  mkdir -p "${WEB_ROOT}"
  rsync -a --delete "${SRC}/" "${WEB_ROOT}/"
  if getent passwd www-data >/dev/null 2>&1; then
    chown -R www-data:www-data "${WEB_ROOT}"
  fi
  if [[ -f "${NGINX_SITE}" ]] && [[ -d /etc/nginx/sites-available ]]; then
    if [[ -f "${NGINX_SNIPPET}" ]]; then
      mkdir -p /etc/nginx/snippets /etc/nginx/conf.d
      cp "${NGINX_SNIPPET}" /etc/nginx/snippets/school-hub-bridge.conf
      [[ -f "${NGINX_ZONE}" ]] && cp "${NGINX_ZONE}" /etc/nginx/conf.d/school-hub-zone.conf
    fi
    cp "${NGINX_SITE}" "/etc/nginx/sites-available/${DOMAIN}"
    ln -sf "/etc/nginx/sites-available/${DOMAIN}" "/etc/nginx/sites-enabled/${DOMAIN}"
    # Template is HTTP-only; re-attach Let's Encrypt 443 block if cert already exists.
    # Without this, HTTPS falls through to Gitea default_server and shows the wrong site.
    if [[ -f "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" ]] && command -v certbot >/dev/null 2>&1; then
      certbot install --cert-name "${DOMAIN}" --nginx --reinstall --non-interactive \
        || certbot --nginx -d "${DOMAIN}" --non-interactive --redirect --reinstall \
        || echo "WARN: certbot reinstall for ${DOMAIN} failed — check HTTPS vhost" >&2
    fi
  fi
  if command -v nginx >/dev/null 2>&1; then
    nginx -t
    systemctl reload nginx
  fi
  if curl -sf --max-time 12 "https://${DOMAIN}/" | grep -q 'AICOM'; then
    echo "OK: https://${DOMAIN}/"
  elif curl -sf --max-time 8 -H "Host: ${DOMAIN}" "http://127.0.0.1/" | grep -q 'AICOM'; then
    echo "OK: https://${DOMAIN}/ (HTTP local only; check TLS vhost)"
  else
    echo "WARN: deploy rsync done but AICOM body not found — check nginx vhost (Gitea default_server?)" >&2
    exit 1
  fi
}

if [[ ! -d /var/www ]] && [[ ! -d /etc/nginx/sites-available ]]; then
  echo "SKIP: ecosystem landing — no /var/www or nginx sites (not the modeldev host)"
  exit 0
fi

if [[ "$(id -u)" -eq 0 ]]; then
  _deploy_landing
else
  exec sudo bash "$0"
fi
