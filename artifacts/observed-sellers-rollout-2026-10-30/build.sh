#!/usr/bin/env bash
# build.sh VARIANT CONTAINER NEWTAG — overlay FROM the container's running image, then smoke inside it (no network).
set -euo pipefail
V="$1"; C="$2"; TAG="$3"
BASE="$(docker inspect -f '{{.Config.Image}}' "$C")"
echo "base $BASE -> $TAG ($V)"
docker build -q --build-arg BASE="$BASE" -t "$TAG" "/root/os-20261030/$V"
docker run --rm --network none -v "/root/os-20261030/$V/smoke.py:/tmp/smoke.py:ro" --entrypoint python "$TAG" /tmp/smoke.py 2>&1 | tail -2
docker run --rm --network none --entrypoint sh "$TAG" -c 'cd /app/aimarket_hub && sha256sum observed_sellers.py api.py migrations.py database.py mcp_gateway.py outbound_http.py hub_routes/federation.py hub_routes/catalog.py hub_routes/wellknown.py' | cut -c1-12 | tr '\n' ' '; echo
cd "/root/os-20261030/$V" && sha256sum observed_sellers.py api.py migrations.py database.py mcp_gateway.py outbound_http.py hub_routes/federation.py hub_routes/catalog.py hub_routes/wellknown.py | cut -c1-12 | tr '\n' ' '; echo
