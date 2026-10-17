#!/usr/bin/env bash
set -euo pipefail
cd /root/logos-nexus-route-20261011
docker cp app-before.py logos:/app/logos/logos/app.py
docker cp old-container-ui/. logos:/usr/share/nginx/html/
docker tag "$(cat old-image.txt)" logos-logos
tar -xzf source-before.tar.gz -C /root/aicom
cp -a nginx-before.conf /etc/nginx/sites-available/logos.modelmarket.dev
nginx -t
systemctl reload nginx
docker restart logos >/dev/null
