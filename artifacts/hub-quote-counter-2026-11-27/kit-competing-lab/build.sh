#!/usr/bin/env bash
# build.sh CONTAINER — image FROM the running one with the quote counter. Refuses when a running file is not the one
# the patch was made against (running/ in this kit), or when the container holds files under /app that its image
# does not.
set -euo pipefail
C="$1"; D="$(cd "$(dirname "$0")" && pwd)"
BASE="$(docker inspect -f '{{.Config.Image}}' "$C")"
h() { docker exec "$C" sha256sum "/app/aimarket_hub/$1" 2>/dev/null | cut -c1-12; }
want() { [[ "$(h "$1")" == "$2" ]] || { echo "unexpected $1 in $C: $(h "$1") (want $2)"; exit 3; }; }
want tutu_esim.py 3b8d0de6e251
want hub_routes/catalog.py c3131f71d02f
want database.py 75811950fe2a
want migrations.py 1d6a794dd4f6
copied="$(docker diff "$C" | grep -E '^[AC] /app/' | grep -vE '__pycache__|\.pyc$' | while read -r kind path; do
  docker exec "$C" test -d "$path" || echo "$kind $path"; done || true)"
[[ -z "$copied" ]] || { echo "files in $C that its image does not have:"; echo "$copied"; exit 4; }
NEW="${BASE%-quotecount-20261127}-quotecount-20261127"
docker build -q --build-arg BASE="$BASE" -t "$NEW" "$D" >/dev/null
echo "$NEW"
