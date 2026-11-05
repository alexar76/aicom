#!/usr/bin/env bash
# build.sh SERVICE CONTAINER NEW_TAG — SERVICE is hub | memory-market | provenance-ledger. Builds FROM the container's
# RUNNING image with only the files in SERVICE/ swapped, runs SERVICE/smoke.py inside it with no network, and checks
# each copied file in the image against the context. Prints EXPECT=<running image> for roll.
set -euo pipefail
SVC="$1"; C="$2"; TAG="$3"; D="$(cd "$(dirname "$0")" && pwd)/$SVC"
BASE="$(docker inspect -f '{{.Config.Image}}' "$C")"
echo "base $BASE -> $TAG"
docker build -q --build-arg BASE="$BASE" -t "$TAG" "$D" >/dev/null
case "$SVC" in
  hub) files="provider_buyer_ref.py:/app/aimarket_hub/provider_buyer_ref.py invoke.py:/app/aimarket_hub/hub_routes/invoke.py"; env=(-e PYTHONPATH=/app -w /app) ;;
  memory-market) files="app.py:/usr/local/lib/python3.12/site-packages/memory_market/app.py"; env=() ;;
  provenance-ledger) files="app.py:/usr/local/lib/python3.12/site-packages/provenance_ledger/app.py"; env=() ;;
  *) echo "unknown service $SVC"; exit 2 ;;
esac
docker run --rm --network none "${env[@]}" -v "$D/smoke.py:/tmp/smoke.py:ro" --entrypoint python "$TAG" /tmp/smoke.py 2>&1 | tail -1
for pair in $files; do
  src="${pair%%:*}"; dst="${pair#*:}"
  a="$(docker run --rm --network none --entrypoint sha256sum "$TAG" "$dst" | cut -c1-12)"; b="$(sha256sum "$D/$src" | cut -c1-12)"
  echo "$src image $a context $b"; [[ "$a" == "$b" ]] || { echo "image file differs — stop"; exit 1; }
done
echo "EXPECT=$BASE"
