#!/usr/bin/env bash
# Resume the prepared release after the initial 30-second readiness gate rolled back.
set -euo pipefail
cd /root/logos-nexus-route-20261011
vhost=/etc/nginx/sites-available/logos.modelmarket.dev
expected=289cbc9066863a330953111c3485c76ae22619081aa8170ec6aa14852d3c16f3
test "$(docker exec logos sha256sum /app/logos/logos/app.py | cut -d' ' -f1)" = "$expected"
test "$(sha256sum /root/aicom/logos/logos/app.py | cut -d' ' -f1)" = "$expected"
cmp nginx-before.conf "$vhost"
docker image inspect logos-nexus-route:20261011 >/dev/null
test -s /var/www/logos-nexus-route-20261011/index.html
docker cp app.py logos:/app/logos/logos/app.py
docker cp dist/. logos:/usr/share/nginx/html/
docker restart logos >/dev/null
healthy=0
for i in $(seq 1 120); do
  if curl -fs --max-time 2 http://127.0.0.1:5199/health > health-after.json; then healthy=1; break; fi
  sleep 1
done
if [ "$healthy" != 1 ]; then bash rollback.sh; exit 1; fi
printf 'LOGOS readiness passed on attempt %s.\n' "$i"
docker tag logos-nexus-route:20261011 logos-logos
cp app.py /root/aicom/logos/logos/app.py
tar -xzf frontend-source.tar.gz -C /root/aicom
python3 - "$vhost" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1]); s = p.read_text()
assert s.count('/var/www/logos-observatory-20261011') == 5
p.write_text(s.replace('/var/www/logos-observatory-20261011', '/var/www/logos-nexus-route-20261011'))
PY
if ! nginx -t; then bash rollback.sh; exit 1; fi
systemctl reload nginx
docker inspect logos --format '{{.Id}}' > container-after.txt
cmp container-before.txt container-after.txt
docker exec logos sha256sum /app/logos/logos/app.py
printf 'NEXUS route fix deployed; existing container identity and data volumes retained.\n'
