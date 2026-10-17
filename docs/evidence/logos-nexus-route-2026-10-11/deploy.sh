#!/usr/bin/env bash
set -euo pipefail
work=/root/logos-nexus-route-20261011
release=/var/www/logos-nexus-route-20261011
vhost=/etc/nginx/sites-available/logos.modelmarket.dev
cd "$work"
test ! -e "$release"
expected=289cbc9066863a330953111c3485c76ae22619081aa8170ec6aa14852d3c16f3
test "$(docker exec logos sha256sum /app/logos/logos/app.py | cut -d' ' -f1)" = "$expected"
test "$(sha256sum /root/aicom/logos/logos/app.py | cut -d' ' -f1)" = "$expected"
docker inspect logos --format '{{.Image}}' > old-image.txt
docker inspect logos --format '{{.Id}}' > container-before.txt
docker cp logos:/app/logos/logos/app.py app-before.py
cp -a "$vhost" nginx-before.conf
mkdir old-container-ui
docker cp logos:/usr/share/nginx/html/. old-container-ui/
tar -czf source-before.tar.gz -C /root/aicom logos/logos/app.py logos/frontend/src logos/frontend/public logos/frontend/index.html
mkdir dist
tar -xzf dist.tar.gz -C dist
mkdir -p "$release"
cp -a /var/www/logos-observatory-20261011/. "$release/"
cp -a dist/. "$release/"
chmod -R a+rX "$release"
base=$(cat old-image.txt)
printf 'FROM %s\nCOPY app.py /app/logos/logos/app.py\nCOPY dist/ /usr/share/nginx/html/\n' "$base" > Dockerfile
docker build -t logos-nexus-route:20261011 .
# Same running container/configuration/volumes; only its application files change.
docker cp app.py logos:/app/logos/logos/app.py
docker cp dist/. logos:/usr/share/nginx/html/
docker restart logos >/dev/null
healthy=0
for i in $(seq 1 120); do
  if curl -fsS --max-time 2 http://127.0.0.1:5199/health > health-after.json; then healthy=1; break; fi
  sleep 1
done
if [ "$healthy" != 1 ]; then bash rollback.sh; exit 1; fi
# Pin the updated image for future recreations; keep the server build sources current.
docker tag logos-nexus-route:20261011 logos-logos
cp app.py /root/aicom/logos/logos/app.py
tar -xzf frontend-source.tar.gz -C /root/aicom
python3 - "$vhost" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1]);s=p.read_text()
assert s.count('/var/www/logos-observatory-20261011')==5
p.write_text(s.replace('/var/www/logos-observatory-20261011','/var/www/logos-nexus-route-20261011'))
PY
if ! nginx -t; then bash rollback.sh; exit 1; fi
systemctl reload nginx
docker inspect logos --format '{{.Id}}' > container-after.txt
cmp container-before.txt container-after.txt
docker exec logos sha256sum /app/logos/logos/app.py
printf 'NEXUS route fix deployed; existing container identity and data volumes retained.\n'
