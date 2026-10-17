#!/usr/bin/env bash
# Run as root on the existing LOGOS host, beside dist.tar.gz. UI only.
set -euo pipefail
release=/var/www/logos-observatory-20261011
vhost=/etc/nginx/sites-available/logos.modelmarket.dev
backup=/root/logos-observatory-20261011
mkdir -p "$backup"
test ! -e "$release" # Never overwrite a release serving visitors.
curl -fsS http://127.0.0.1:5199/health > "$backup/health-before.json"
docker inspect logos --format '{{.Id}}' > "$backup/container-before.txt"
cp -a "$vhost" "$backup/nginx-before.conf"
mkdir -p "$release"
# Keep old hashed chunks for visitors who opened the previous UI.
docker cp logos:/usr/share/nginx/html/. "$release/"
tar -xzf "$backup/dist.tar.gz" -C "$release"
chmod -R a+rX "$release"
python3 - "$vhost" "$release" <<'PY'
import sys
from pathlib import Path
p=Path(sys.argv[1]);s=p.read_text();root=sys.argv[2]
assert '# LOGOS OBSERVATORY UI' not in s
marker='    # The React dashboard (SPA fallback handled inside the container).'
assert s.count(marker)==1
block='''    # LOGOS OBSERVATORY UI — static release; backend/discovery routes unchanged.
    location = / {
        root ROOT;
        try_files /index.html =404;
        add_header Cache-Control "no-cache";
        add_header X-Content-Type-Options nosniff;
        add_header X-Frame-Options DENY;
        add_header Referrer-Policy no-referrer always;
        add_header Strict-Transport-Security "max-age=63072000; includeSubDomains" always;
    }
    location = /index.html {
        root ROOT;
        add_header Cache-Control "no-cache";
        add_header X-Content-Type-Options nosniff;
        add_header X-Frame-Options DENY;
        add_header Referrer-Policy no-referrer always;
        add_header Strict-Transport-Security "max-age=63072000; includeSubDomains" always;
    }
    location ^~ /assets/ {
        root ROOT;
        try_files $uri =404;
        expires 1y;
    }
    location ^~ /fonts/ {
        root ROOT;
        try_files $uri =404;
        expires 1h;
    }
    location = /logos.svg {
        root ROOT;
        expires 1h;
    }

'''.replace('ROOT',root)
p.write_text(s.replace(marker,block+marker))
PY
if ! nginx -t; then
  cp -a "$backup/nginx-before.conf" "$vhost"
  exit 1
fi
systemctl reload nginx
curl -fsS http://127.0.0.1:5199/health > "$backup/health-after.json"
docker inspect logos --format '{{.Id}}' > "$backup/container-after.txt"
cmp "$backup/container-before.txt" "$backup/container-after.txt"
echo 'Static UI published; LOGOS container and data unchanged.'
