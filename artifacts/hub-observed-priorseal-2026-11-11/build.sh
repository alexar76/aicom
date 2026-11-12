#!/usr/bin/env bash
# Overlay FROM the apex hub's running image: observed_sellers.py from main (7d80bae43, PriorSeal's resources[] items).
# Then the smoke test inside it, no network.
set -euo pipefail
D=/root/os-priorseal-20261111
BASE="$(docker inspect -f '{{.Config.Image}}' modelmarket-hub)"
echo "base $BASE ($(docker inspect -f '{{.Image}}' modelmarket-hub | cut -c8-19))"
docker build -q --build-arg BASE="$BASE" -t modelmarket-hub:os-priorseal-20261111 "$D"
docker run --rm --network none -e PYTHONPATH=/app -w /app \
  -v "$D/smoke.py:/tmp/smoke.py:ro" -v "$D/priorseal-x402.json:/tmp/priorseal-x402.json:ro" \
  -v "$D/oracleinsight-x402.json:/tmp/oracleinsight-x402.json:ro" \
  --entrypoint python modelmarket-hub:os-priorseal-20261111 /tmp/smoke.py
docker image inspect -f '{{.Id}}' modelmarket-hub:os-priorseal-20261111
