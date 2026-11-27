#!/usr/bin/env bash
# build.sh CONTAINER — image FROM the running one with the quote counter. Refuses when a running file is not
# the version this change was made against (main 32cfdd226), or when the container holds files under /app that
# its image does not (a change another session copied in: rebuilding from the image would drop it).
set -euo pipefail
C="$1"; D="$(cd "$(dirname "$0")" && pwd)"
BASE="$(docker inspect -f '{{.Config.Image}}' "$C")"
h() { docker exec "$C" sha256sum "/app/aimarket_hub/$1" 2>/dev/null | cut -c1-12; }
want() { [[ "$(h "$1")" == "$2" ]] || { echo "unexpected $1 in $C: $(h "$1") (want $2)"; exit 3; }; }
want tutu_esim.py 2a9d9d2b09fc
want hub_routes/catalog.py c6208b25cba3
want hub_routes/invoke_parts/local_delivery.py 77cdc3ae4960
want database.py 5de3afb4ffe6
want migrations.py 4fbf3d226315
copied="$(docker diff "$C" | grep -E '^[AC] /app/' | grep -vE '__pycache__|\.pyc$' | while read -r kind path; do
  docker exec "$C" test -d "$path" || echo "$kind $path"; done || true)"
[[ -z "$copied" ]] || { echo "files in $C that its image does not have:"; echo "$copied"; exit 4; }
NEW="${BASE%-quotecount-20261127}-quotecount-20261127"
docker build -q --build-arg BASE="$BASE" -t "$NEW" "$D" >/dev/null
echo "$NEW"
