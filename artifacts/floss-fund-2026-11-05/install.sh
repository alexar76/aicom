#!/bin/bash
# FLOSS/fund manifest hosting (owner step; the classifier refuses remote writes from Claude).
#   bash artifacts/floss-fund-2026-11-05/install.sh
# 1. factory-vps: nginx `location = /funding.json` on modelmarket.dev → /var/www/funding/funding.json
# 2. admin-vps:   nginx `location = /.well-known/funding-manifest-urls` on histor.modelmarket.dev
# 3. uploads the filled manifest from PromoMaterials (refuses while placeholders remain) and checks both URLs.
# Each host: config backup in /root/nginx-backups/*-before-funding-json, `nginx -t`, restore on failure.
# Rollback: cp the backup over /etc/nginx/sites-available/<site> && systemctl reload nginx; rm -rf /var/www/funding.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
MANIFEST="${MANIFEST:-$HERE/../../../PromoMaterials/outreach/funding-2026-11/funding.json}"
[ -f "$MANIFEST" ] || MANIFEST="/Users/alex/Desktop/ai_tests/aicompany/PromoMaterials/outreach/funding-2026-11/funding.json"
if grep -q '\[[A-Z ]*\]' "$MANIFEST"; then echo "funding.json still has [PLACEHOLDERS]; fill it first" >&2; exit 1; fi
python3 -c 'import json,sys; json.load(open(sys.argv[1]))' "$MANIFEST"

patch_site() {  # host site anchor block-file
  local host="$1" site="$2"
  ssh -o ConnectTimeout=15 "$host" "bash -s" "$site" <<'REMOTE'
set -euo pipefail
SITE="$1"; REAL=$(readlink -f "/etc/nginx/sites-enabled/$SITE")
mkdir -p /root/nginx-backups /var/www/funding
BAK="/root/nginx-backups/$SITE.$(date -u +%Y%m%d-%H%M%S)-before-funding-json"
cp -a "$REAL" "$BAK"
python3 - "$REAL" "$SITE" <<'PY'
import sys
p, site = sys.argv[1], sys.argv[2]
t = open(p).read()
if site == "modelmarket.dev":
    key = "location = /funding.json"
    anchor = "    location /.well-known/ {\n        proxy_pass http://127.0.0.1:9083;"
    block = ("    # FLOSS/fund funding manifest (https://fundingjson.org).\n"
             "    location = /funding.json {\n        alias /var/www/funding/funding.json;\n"
             "        default_type application/json;\n        add_header Access-Control-Allow-Origin \"*\" always;\n"
             "        add_header Cache-Control \"no-cache\" always;\n    }\n\n")
else:
    key = "location = /.well-known/funding-manifest-urls"
    anchor = "    location ^~ /.well-known/erc-8004/feedback/ {"
    block = ("    # FLOSS/fund: this host's projects are listed in https://modelmarket.dev/funding.json.\n"
             "    location = /.well-known/funding-manifest-urls {\n        alias /var/www/funding/funding-manifest-urls;\n"
             "        default_type text/plain;\n        add_header Access-Control-Allow-Origin \"*\" always;\n    }\n\n")
if key in t:
    print(site, "already has", key); sys.exit(0)
assert t.count(anchor) == 1, (site, t.count(anchor))
open(p, "w").write(t.replace(anchor, block + anchor, 1))
print(site, "inserted", key)
PY
if nginx -t; then systemctl reload nginx; echo "$SITE reloaded; backup $BAK"; else cp -a "$BAK" "$REAL"; echo "$SITE: nginx -t failed, restored" >&2; exit 1; fi
REMOTE
}

patch_site factory-vps modelmarket.dev
scp -q "$MANIFEST" factory-vps:/var/www/funding/funding.json
ssh factory-vps 'chmod 644 /var/www/funding/funding.json'
patch_site admin-vps histor.modelmarket.dev
printf 'https://modelmarket.dev/funding.json\n' | ssh admin-vps 'cat > /var/www/funding/funding-manifest-urls && chmod 644 /var/www/funding/funding-manifest-urls'

echo "--- check"
curl -fsS https://modelmarket.dev/funding.json | python3 -c 'import json,sys; d=json.load(sys.stdin); print("funding.json OK:", d["entity"]["name"])'
curl -fsS https://histor.modelmarket.dev/.well-known/funding-manifest-urls
echo DONE
