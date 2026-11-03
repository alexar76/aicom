#!/usr/bin/env bash
# Overlay FROM the apex hub's running image: theme.py only. Then the smoke test inside it, no network.
set -euo pipefail
D=/root/link-fallback-20261031
BASE="$(docker inspect -f '{{.Config.Image}}' modelmarket-hub)"
echo "base $BASE ($(docker inspect -f '{{.Image}}' modelmarket-hub | cut -c8-19))"
docker build -q --build-arg BASE="$BASE" -t modelmarket-hub:link-fallback-20261031 "$D"
docker run --rm --network none -e PYTHONPATH=/app -w /app -v "$D/smoke.py:/tmp/smoke.py:ro" --entrypoint python modelmarket-hub:link-fallback-20261031 /tmp/smoke.py
