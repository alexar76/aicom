#!/usr/bin/env bash
# Publish the ARGUS curl installer to nginx static root on magic-ai-factory.com.
#
#   curl -fsSL https://magic-ai-factory.com/install | bash
#
# Run on the production host (as root):
#   sudo ./scripts/setup-argus-install.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="${ROOT}/ecosystem-landing/install"
WEB_ROOT="/var/www/aicom-install"
NGINX_SNIPPET="${ROOT}/deploy/nginx/snippets/argus-install.conf"
SITE="${NGINX_SITE:-/etc/nginx/sites-enabled/magic-ai-factory.com}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo $0" >&2
  exit 1
fi

if [[ ! -f "$SRC" ]]; then
  echo "ERROR: missing $SRC — run: cp scripts/install_argus.sh ecosystem-landing/install" >&2
  exit 1
fi

mkdir -p "$WEB_ROOT"
install -m 0644 "$SRC" "${WEB_ROOT}/install"
chown -R www-data:www-data "$WEB_ROOT"
echo "Installed ${WEB_ROOT}/install"

SNIPPET_DEST="/etc/nginx/snippets/argus-install.conf"
install -m 0644 "$NGINX_SNIPPET" "$SNIPPET_DEST"
echo "Installed ${SNIPPET_DEST}"

if [[ -f "$SITE" ]] && ! grep -q 'argus-install.conf' "$SITE"; then
  echo "WARN: include deploy/nginx/snippets/argus-install.conf inside the HTTPS server { } block of ${SITE}"
  echo "      Then: sudo nginx -t && sudo systemctl reload nginx"
else
  nginx -t
  systemctl reload nginx
  echo "nginx reloaded"
fi

echo ""
echo "OK: curl -fsSL https://magic-ai-factory.com/install | bash"
