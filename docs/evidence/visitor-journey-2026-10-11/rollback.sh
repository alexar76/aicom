#!/usr/bin/env bash
set -euo pipefail
cd /root/visitor-journey-20261011
cp backup/magic-ai-factory.com /etc/nginx/sites-available/magic-ai-factory.com
cp backup/modeldev.modelmarket.dev /etc/nginx/sites-available/modeldev.modelmarket.dev
ln -sfn "$(cat backup/ecosystem-target)" /var/www/ecosystem.modelmarket.dev
nginx -t
systemctl reload nginx
