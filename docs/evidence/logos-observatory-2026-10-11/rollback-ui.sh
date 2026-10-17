#!/usr/bin/env bash
set -euo pipefail
cp -a /root/logos-observatory-20261011/nginx-before.conf /etc/nginx/sites-available/logos.modelmarket.dev
nginx -t
systemctl reload nginx
curl -fsS http://127.0.0.1:5199/health
