#!/usr/bin/env bash
# build.sh CONTAINER — image FROM the running one with mmq. Refuses unless the running files are the quote-counter
# versions this change was made against, or when the container holds files under /app its image does not.
set -euo pipefail
C="$1"; D="$(cd "$(dirname "$0")" && pwd)"
BASE="$(docker inspect -f '{{.Config.Image}}' "$C")"
h() { docker exec "$C" sha256sum "/app/aimarket_hub/$1" 2>/dev/null | cut -c1-12; }
want() { [[ "$(h "$1")" == "$2" ]] || { echo "unexpected $1 in $C: $(h "$1") (want $2)"; exit 3; }; }
want tutu_esim.py 01395888a888
want database.py dd24827449e9
want migrations.py 4e8f95187cdb
copied="$(docker diff "$C" | grep -E '^[AC] /app/' | grep -vE '__pycache__|\.pyc$' | while read -r kind path; do
  docker exec "$C" test -d "$path" || echo "$kind $path"; done || true)"
[[ -z "$copied" ]] || { echo "files in $C that its image does not have:"; echo "$copied"; exit 4; }
NEW="${BASE%-quotemmq-20261127}-quotemmq-20261127"
docker build -q --build-arg BASE="$BASE" -t "$NEW" "$D" >/dev/null
echo "$NEW"
