#!/usr/bin/env bash
# build.sh CONTAINER NEW_TAG LIVE_SHA12 — overlay mcp_gateway.py (aicom 624e03e43) FROM the container's running image.
# Stops unless the live gateway still has LIVE_SHA12 (the file the context was made from). Builds, runs smoke.py in the
# image with no network, checks the file in the image against the context. Prints EXPECT for roll.sh.
set -euo pipefail
C="$1"; TAG="$2"; LIVE="$3"; D="$(cd "$(dirname "$0")" && pwd)"
BASE="$(docker inspect -f '{{.Config.Image}}' "$C")"
[[ "$(docker image inspect -f '{{.Id}}' "$BASE")" == "$(docker inspect -f '{{.Image}}' "$C")" ]] || { echo "base tag no longer is the running image — stop"; exit 1; }
now="$(docker cp "$C:/app/aimarket_hub/mcp_gateway.py" - | tar -xO | sha256sum | cut -c1-12)"
[[ "$now" == "$LIVE" ]] || { echo "live mcp_gateway.py $now, context made from $LIVE — stop"; exit 1; }
echo "base $BASE -> $TAG (live gateway $now)"
docker build -q --build-arg BASE="$BASE" -t "$TAG" "$D" >/dev/null
docker run --rm --network none -e PYTHONPATH=/app -w /app -v "$D/smoke.py:/tmp/smoke.py:ro" --entrypoint python "$TAG" /tmp/smoke.py 2>&1 | tail -1
a="$(docker run --rm --network none --entrypoint sha256sum "$TAG" /app/aimarket_hub/mcp_gateway.py | cut -c1-12)"
b="$(sha256sum "$D/mcp_gateway.py" | cut -c1-12)"
echo "mcp_gateway.py image $a context $b"; [[ "$a" == "$b" ]] || { echo "image file differs — stop"; exit 1; }
echo "EXPECT=$BASE"
