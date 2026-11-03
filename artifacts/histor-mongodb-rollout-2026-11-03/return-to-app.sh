#!/usr/bin/env bash
# Run only after the HISTOR image serves the checker on loopback.
set -euo pipefail

site=/etc/nginx/sites-available/histor.modelmarket.dev
base=https://histor.modelmarket.dev
upstream=http://127.0.0.1:9490
guide=/mongodb-mcp-read-only-tools.html
backup="$(mktemp -d /root/histor-backups/mongodb-app-edge.XXXXXXXX)"
cp -p "$site" "$backup/nginx.conf"
for path in "$guide" /assets/compare-tool-names.js /assets/tool-comparison.css /robots.txt; do
  curl -fsS --max-time 8 "$upstream$path" > "$backup/${path##*/}"
done
curl -fsS --max-time 8 "$upstream/sitemap-site.xml" > "$backup/sitemap-site.xml"
grep -Fq "<loc>$base$guide</loc>" "$backup/sitemap-site.xml"

python3 - "$site" "$backup/nginx.candidate" <<'PY'
from pathlib import Path
import sys

site, candidate = map(Path, sys.argv[1:])
config = site.read_text()
marker = "    # Standalone MongoDB MCP checker and its search sitemap.\n"
if config.count(marker) != 1:
    raise SystemExit("Unexpected MongoDB edge marker")
config = config.replace(marker, "    # Historical sitemap URL for the MongoDB MCP checker.\n", 1)
for url, media in (
    ("/mongodb-mcp-read-only-tools.html", "text/html"),
    ("/assets/compare-tool-names.js", "application/javascript"),
    ("/assets/tool-comparison.css", "text/css"),
    ("/robots.txt", "text/plain"),
):
    block = (
        f"    location = {url} {{\n"
        f"        alias /var/www/histor-mongodb-guide{url};\n"
        f"        default_type {media};\n"
        "        charset utf-8;\n"
        "    }\n\n"
    )
    if config.count(block) != 1:
        raise SystemExit(f"Unexpected edge location for {url}")
    config = config.replace(block, "", 1)
candidate.write_text(config)
PY

restore() {
  cp -p "$backup/nginx.conf" "$site"
  nginx -t && systemctl reload nginx
}
trap restore EXIT
install -m 0644 "$backup/nginx.candidate" "$site"
nginx -t
systemctl reload nginx

for path in "$guide" /assets/compare-tool-names.js /assets/tool-comparison.css /robots.txt /sitemap-site.xml; do
  for attempt in 1 2 3 4 5; do
    curl -fsS --max-time 8 "$base$path" > "$backup/public-response" &&
      cmp -s "$backup/public-response" "$backup/${path##*/}" && break
    sleep 1
  done
  cmp -s "$backup/public-response" "$backup/${path##*/}"
done
curl -fsS --max-time 8 "$base/" > "$backup/public-home"
grep -Fq 'href="mongodb-mcp-read-only-tools.html"' "$backup/public-home"
curl -fsS --max-time 8 "$base/sitemap-mongodb-guide.xml" >/dev/null
trap - EXIT
printf 'Checker served by HISTOR app. Previous nginx config: %s/nginx.conf\n' "$backup"
