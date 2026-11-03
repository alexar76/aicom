#!/usr/bin/env bash
# Publish just the standalone guide at the HISTOR nginx edge.
set -euo pipefail
stage="${1:?Pass staging directory}"
site=/etc/nginx/sites-available/histor.modelmarket.dev
web=/var/www/histor-mongodb-guide
base=https://histor.modelmarket.dev
guide=/mongodb-mcp-read-only-tools.html
sitemap=/sitemap-mongodb-guide.xml
backup="$(mktemp -d /root/histor-backups/mongodb-static.XXXXXXXX)"
cp -p "$site" "$backup/nginx.conf"
[[ ! -e "$web" ]] || { echo 'Guide directory already exists' >&2; exit 1; }
changed=0
success=0
rollback() {
    if (( success )); then return; fi
    if (( changed )); then
        cp -p "$backup/nginx.conf" "$site"
        nginx -t && systemctl reload nginx
    fi
    if [[ -d "$web" ]]; then rm -r -- "$web"; fi
}
trap rollback EXIT
install -d -m 0755 "$web/assets"
install -m 0644 "$stage/${guide#/}" "$web/"
install -m 0644 "$stage/assets/compare-tool-names.js" "$stage/assets/tool-comparison.css" "$web/assets/"
curl -fsS --max-time 8 http://127.0.0.1:9490/robots.txt > "$backup/upstream-robots.txt"
grep -Fx "Sitemap: $base/sitemap.xml" "$backup/upstream-robots.txt" >/dev/null
{
    cat "$backup/upstream-robots.txt"
    printf 'Sitemap: %s%s\n' "$base" "$sitemap"
} > "$web/robots.txt"
printf '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>%s%s</loc></url></urlset>\n' \
    "$base" "$guide" > "$web/${sitemap#/}"
python3 - "$site" "$backup/nginx.candidate" <<'PY'
from pathlib import Path
import sys

site, candidate = map(Path, sys.argv[1:])
config = site.read_text()
marker = "    location ^~ /api/v1/admin/ {"
if config.count(marker) != 1 or "/mongodb-mcp-read-only-tools.html" in config:
    raise SystemExit("Unexpected HISTOR nginx configuration")
locations = {
    "/mongodb-mcp-read-only-tools.html": "text/html",
    "/assets/compare-tool-names.js": "application/javascript",
    "/assets/tool-comparison.css": "text/css",
    "/robots.txt": "text/plain",
    "/sitemap-mongodb-guide.xml": "application/xml",
}
blocks = "".join(
    f"    location = {url} {{\n"
    f"        alias /var/www/histor-mongodb-guide{url};\n"
    f"        default_type {media};\n"
    "        charset utf-8;\n"
    "    }\n\n"
    for url, media in locations.items()
)
candidate.write_text(config.replace(marker, "    # Standalone MongoDB MCP checker and its search sitemap.\n" + blocks + marker, 1))
PY
changed=1
install -m 0644 "$backup/nginx.candidate" "$site"
nginx -t
systemctl reload nginx

for path in "$guide" /assets/compare-tool-names.js /assets/tool-comparison.css /robots.txt "$sitemap"; do
    for attempt in 1 2 3 4 5; do
        curl -fsS --max-time 8 "$base$path" > "$backup/response" && cmp -s "$backup/response" "$web$path" && break
        sleep 1
    done
    cmp -s "$backup/response" "$web$path"
    printf 'Verified public %s\n' "$path"
done
curl -fsS --max-time 8 "$base/health" | python3 -c 'import json,sys; h=json.load(sys.stdin); assert h["ok"] and h["store"] == "postgresql"'
success=1
printf 'Static page deployed. Prior nginx configuration: %s/nginx.conf\n' "$backup"
