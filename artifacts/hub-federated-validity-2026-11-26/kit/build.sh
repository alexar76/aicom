#!/usr/bin/env bash
# build.sh CONTAINER — image FROM the container's running image, with the four files of the change, tagged
# <repo>:<running tag>-fedvalid-20261126. Refuses when the container's four files are not the expected ones.
set -euo pipefail
C="$1"; D="$(cd "$(dirname "$0")" && pwd)"
BASE="$(docker inspect -f '{{.Config.Image}}' "$C")"
want="e2f0eec359c0 config.py
51757ad16355 crawler.py
cf228b3f01a9 database.py
6ff2fc43d197 realm.py"
have="$(for f in config crawler database realm; do echo "$(docker exec "$C" sha256sum /app/aimarket_hub/$f.py | cut -c1-12) $f.py"; done)"
[[ "$have" == "$want" ]] || { echo "unexpected running files in $C:"; echo "$have"; exit 3; }
NEW="${BASE%%:*}:${BASE##*:}-fedvalid-20261126"
docker build -q --build-arg BASE="$BASE" -t "$NEW" "$D" >/dev/null
echo "$NEW"
