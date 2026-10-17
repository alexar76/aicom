#!/usr/bin/env bash
set -euo pipefail
cd /root/logos-landing-20261011
cp -a nginx-before.conf /etc/nginx/sites-available/logos.modelmarket.dev
nginx -t
systemctl reload nginx
