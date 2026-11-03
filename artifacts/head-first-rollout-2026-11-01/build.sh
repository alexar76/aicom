#!/usr/bin/env bash
# build.sh CONTAINER NEW_TAG — overlay FROM the container's running image (observed_sellers.py only), the smoke
# inside it with no network, then the file in the image against the context. Prints the EXPECT image for roll.sh.
set -euo pipefail
C="$1"; TAG="$2"; D="$(cd "$(dirname "$0")" && pwd)"
BASE="$(docker inspect -f '{{.Config.Image}}' "$C")"
echo "base $BASE ($(docker inspect -f '{{.Image}}' "$C" | cut -c8-19)) -> $TAG"
docker build -q --build-arg BASE="$BASE" -t "$TAG" "$D" >/dev/null
docker run --rm --network none -e PYTHONPATH=/app -w /app -v "$D/smoke.py:/tmp/smoke.py:ro" --entrypoint python "$TAG" /tmp/smoke.py 2>&1 | tail -2
echo "image $(docker run --rm --network none --entrypoint sha256sum "$TAG" /app/aimarket_hub/observed_sellers.py | cut -c1-12) context $(sha256sum "$D/observed_sellers.py" | cut -c1-12)"
echo "EXPECT=$BASE"
