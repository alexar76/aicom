#!/usr/bin/env bash
# build.sh CONTAINER NEW_TAG — overlay FROM the container's running image: ard.py, hub_routes/ard.py and the LIVE
# api.py patched by patch_api.py; then the smoke inside the image with no network, and the files in the image
# against the context. Prints the EXPECT image for roll.sh.
set -euo pipefail
C="$1"; TAG="$2"; D="$(cd "$(dirname "$0")" && pwd)"
BASE="$(docker inspect -f '{{.Config.Image}}' "$C")"
echo "base $BASE ($(docker inspect -f '{{.Image}}' "$C" | cut -c8-19)) -> $TAG"
docker cp "$C:/app/aimarket_hub/api.py" "$D/api.live.py"
python3 "$D/patch_api.py" "$D/api.live.py" "$D/api.py"
docker build -q --build-arg BASE="$BASE" -t "$TAG" "$D" >/dev/null
docker run --rm --network none -e PYTHONPATH=/app -w /app -v "$D/smoke.py:/tmp/smoke.py:ro" --entrypoint python "$TAG" /tmp/smoke.py 2>&1 | tail -1
for f in ard.py:ard.py hub_routes_ard.py:hub_routes/ard.py api.py:api.py; do
  ctx="${f%%:*}"; img="${f#*:}"
  a="$(docker run --rm --network none --entrypoint sha256sum "$TAG" "/app/aimarket_hub/$img" | cut -c1-12)"
  b="$(sha256sum "$D/$ctx" | cut -c1-12)"
  echo "$img image $a context $b"; [[ "$a" == "$b" ]] || { echo "image file differs — stop"; exit 1; }
done
echo "EXPECT=$BASE"
