#!/usr/bin/env bash
# Run on the existing LOGOS host with landing.tar.gz in this directory.
# Adds only /landing/; the dashboard, APIs, container and data remain in place.
set -euo pipefail
cd /root/logos-landing-20261011
release=/var/www/logos-landing-20261011
vhost=/etc/nginx/sites-available/logos.modelmarket.dev
test ! -e "$release"
cp -a "$vhost" nginx-before.conf
docker inspect logos --format '{{.Id}}' > container-before.txt
mkdir -p "$release/landing"
tar -xzf landing.tar.gz -C "$release/landing"
chmod -R a+rX "$release"
python3 - "$vhost" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1]); s = p.read_text()
anchor = '    # LOGOS OBSERVATORY UI'
assert s.count(anchor) == 1 and 'location ^~ /landing/' not in s
block = '''    # Public introduction, separate from the working dashboard.
    location = /landing { return 301 /landing/; }
    location ^~ /landing/ {
        root /var/www/logos-landing-20261011;
        index index.html;
        try_files $uri $uri/ =404;
        add_header Cache-Control "no-cache";
        add_header X-Content-Type-Options nosniff;
        add_header Referrer-Policy no-referrer always;
        add_header Strict-Transport-Security "max-age=63072000; includeSubDomains" always;
    }

'''
p.write_text(s.replace(anchor, block + anchor))
PY
if ! nginx -t; then cp -a nginx-before.conf "$vhost"; exit 1; fi
systemctl reload nginx
docker inspect logos --format '{{.Id}}' > container-after.txt
cmp container-before.txt container-after.txt
ready=0
for attempt in $(seq 1 10); do
    if curl -fsS --max-time 10 https://logos.modelmarket.dev/landing/ -o published.html && cmp -s published.html "$release/landing/index.html"; then ready=1; break; fi
    sleep 1
done
test "$ready" = 1
curl -fsS --max-time 5 http://127.0.0.1:5199/health
mkdir -p /root/aicom/logos/docs/landing
cp -a "$release/landing/." /root/aicom/logos/docs/landing/
printf '\nLOGOS landing published; backend not restarted.\n'
