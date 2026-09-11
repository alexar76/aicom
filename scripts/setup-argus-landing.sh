#!/usr/bin/env bash
# Publish ecosystem-landing/argus/ → /var/www/argus-landing on magic-ai-factory.com.
# Serves the static promo landing at https://magic-ai-factory.com/argus/
# (live Arena UI stays at /arena/ and /argus/arena/).
#
# Run on the production host (as root):
#   sudo ./scripts/setup-argus-landing.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="${ROOT}/ecosystem-landing/argus"
WEB_ROOT="/var/www/argus-landing"
NGINX_SNIPPET="${ROOT}/deploy/nginx/snippets/argus-landing.conf"
SITE="${NGINX_SITE:-/etc/nginx/sites-enabled/magic-ai-factory.com}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo $0" >&2
  exit 1
fi

if [[ ! -f "${SRC}/index.html" ]]; then
  echo "ERROR: missing ${SRC}/index.html" >&2
  exit 1
fi

mkdir -p "$WEB_ROOT"
rsync -a --delete "${SRC}/" "${WEB_ROOT}/"
chown -R www-data:www-data "$WEB_ROOT"
echo "Installed ${WEB_ROOT}/ (ARGUS promo landing)"

SNIPPET_DEST="/etc/nginx/snippets/argus-landing.conf"
install -m 0644 "$NGINX_SNIPPET" "$SNIPPET_DEST"
echo "Installed ${SNIPPET_DEST}"

if [[ -f "$SITE" ]]; then
  python3 - "$SITE" <<'PY'
import re
import sys
from pathlib import Path

site = Path(sys.argv[1])
text = site.read_text(encoding="utf-8")
changed = False

# Remove legacy redirect that sent /argus/ → /argus/arena (Agent Arena UI).
old_redirect = re.compile(
    r"\n\s*location = /argus/ \{\s*\n\s*return 302 /argus/arena;\s*\n\s*\}\s*\n",
    re.MULTILINE,
)
if old_redirect.search(text):
    text = old_redirect.sub("\n", text, count=1)
    changed = True
    print("Removed legacy /argus/ → /argus/arena redirect")

if "argus-landing.conf" not in text:
    anchor = "    location ^~ /argus/ {"
    if anchor in text:
        text = text.replace(
            anchor,
            "    include /etc/nginx/snippets/argus-landing.conf;\n\n" + anchor,
            1,
        )
        changed = True
        print(f"Patched {site} (include argus-landing.conf)")
    else:
        print(f"WARN: no {anchor.strip()!r} in {site} — add include manually", file=sys.stderr)

if changed:
    site.write_text(text, encoding="utf-8")
PY
fi

nginx -t
systemctl reload nginx
echo ""
echo "OK: https://magic-ai-factory.com/argus/ (promo landing)"
echo "Arena: https://magic-ai-factory.com/arena/"
