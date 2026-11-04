#!/usr/bin/env bash
# build.sh CONTAINER NEW_TAG — ard.py only, FROM the container's running image (the :ard-20261104 overlay), then the
# smoke (now also checking the full trustManifest subject of a search result) and the file against the context.
set -euo pipefail
C="$1"; TAG="$2"; D="$(cd "$(dirname "$0")" && pwd)"
BASE="$(docker inspect -f '{{.Config.Image}}' "$C")"
[[ "$BASE" == *":ard-20261104" ]] || { echo "$C runs $BASE, not the ard-20261104 overlay — stop"; exit 1; }
echo "base $BASE -> $TAG"
docker build -q --build-arg BASE="$BASE" -t "$TAG" "$D" >/dev/null
docker run --rm --network none -e PYTHONPATH=/app -w /app -v "$D/smoke.py:/tmp/smoke.py:ro" --entrypoint python "$TAG" /tmp/smoke.py 2>&1 | tail -1
a="$(docker run --rm --network none --entrypoint sha256sum "$TAG" /app/aimarket_hub/ard.py | cut -c1-12)"; b="$(sha256sum "$D/ard.py" | cut -c1-12)"
echo "ard.py image $a context $b"; [[ "$a" == "$b" ]] || { echo "image file differs — stop"; exit 1; }
echo "EXPECT=$BASE"
