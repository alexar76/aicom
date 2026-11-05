#!/usr/bin/env bash
# build.sh CONTAINER NEW_TAG — overlay catalog.py FROM the container's running image (pattern of cf-20261104).
# Stops if the live catalog.py changed since live.sha; builds; runs smoke.py in the image with no network; checks
# the file in the image against the context. Prints EXPECT for roll.sh.
set -euo pipefail
C="$1"; TAG="$2"; D="$(cd "$(dirname "$0")" && pwd)"
BASE="$(docker inspect -f '{{.Config.Image}}' "$C")"
echo "base $BASE -> $TAG"
[[ "$(docker image inspect -f '{{.Id}}' "$BASE")" == "$(docker inspect -f '{{.Image}}' "$C")" ]] || { echo "base is not the running image — stop"; exit 1; }
while read -r sha f; do
  live="$(docker exec "$C" sha256sum "/app/aimarket_hub/$f" | cut -c1-12)"
  [[ "$live" == "$sha" ]] || { echo "$f live $live, context patched from $sha — stop"; exit 1; }
done < "$D/live.sha"
docker build -q --build-arg BASE="$BASE" -t "$TAG" "$D" >/dev/null
docker run --rm --network none -e PYTHONPATH=/app -w /app -v "$D/smoke.py:/tmp/smoke.py:ro" --entrypoint python "$TAG" /tmp/smoke.py 2>&1 | tail -1
a="$(docker run --rm --network none --entrypoint sha256sum "$TAG" /app/aimarket_hub/hub_routes/catalog.py | cut -c1-12)"
b="$(sha256sum "$D/catalog.py" | cut -c1-12)"
echo "catalog.py image $a context $b"; [[ "$a" == "$b" ]] || { echo "image file differs — stop"; exit 1; }
echo "EXPECT=$BASE"
