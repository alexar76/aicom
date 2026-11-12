#!/usr/bin/env bash
# build.sh BASE_IMAGE NEW_TAG — build the overlay FROM the running image, smoke it with no network, and compare
# every overlay file in the image with the context.
set -euo pipefail
BASE="$1"; TAG="$2"; W="$(cd "$(dirname "$0")" && pwd)"
cd "$W"
docker build --build-arg BASE="$BASE" -t "$TAG" . 2>&1 | tail -3
echo "base $BASE ($(docker image inspect -f '{{.Id}}' "$BASE" | cut -c8-19)) -> $TAG"
docker run --rm --network none --entrypoint python -v "$W/smoke.py:/tmp/smoke.py:ro" "$TAG" /tmp/smoke.py
bad="$(docker run --rm -i --network none --entrypoint sh "$TAG" -c 'cd /app && sha256sum -c -' < overlay.sha256 | grep -v ': OK$' || true)"
[ -z "$bad" ] && echo "all $(wc -l < overlay.sha256) overlay files in the image match the context" || { echo "MISMATCH: $bad"; exit 1; }
