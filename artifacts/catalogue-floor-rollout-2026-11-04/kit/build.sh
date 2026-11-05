#!/usr/bin/env bash
# build.sh CONTAINER NEW_TAG [BASE] — overlay the catalogue floor (aicom 28004ff8a) FROM the container's running image.
# The directory holds the Dockerfile, the four patched files, live.sha (the live files the context was patched
# from) and smoke.py. Stops if the live files changed since; then builds, runs the smoke inside the image with no
# network, and checks the files in the image against the context. Prints EXPECT for roll.sh.
set -euo pipefail
C="$1"; TAG="$2"; D="$(cd "$(dirname "$0")" && pwd)"
BASE="${3:-$(docker inspect -f '{{.Config.Image}}' "$C")}"
echo "base $BASE ($(docker image inspect -f '{{.Id}}' "$BASE" | cut -c8-19), container on $(docker inspect -f '{{.Image}}' "$C" | cut -c8-19)) -> $TAG"
[[ "$(docker image inspect -f '{{.Id}}' "$BASE")" == "$(docker inspect -f '{{.Image}}' "$C")" ]] || { echo "base is not the running image — stop"; exit 1; }
while read -r sha f; do
  live="$(docker exec "$C" sha256sum "/app/aimarket_hub/$f" | cut -c1-12)"
  [[ "$live" == "$sha" ]] || { echo "$f live $live, context patched from $sha — stop"; exit 1; }
done < "$D/live.sha"
docker build -q --build-arg BASE="$BASE" -t "$TAG" "$D" >/dev/null
docker run --rm --network none -e PYTHONPATH=/app -w /app -v "$D/smoke.py:/tmp/smoke.py:ro" --entrypoint python "$TAG" /tmp/smoke.py 2>&1 | tail -1
for f in crawler.py database.py migrations.py cli.py; do
  a="$(docker run --rm --network none --entrypoint sha256sum "$TAG" "/app/aimarket_hub/$f" | cut -c1-12)"
  b="$(sha256sum "$D/$f" | cut -c1-12)"
  echo "$f image $a context $b"; [[ "$a" == "$b" ]] || { echo "image file differs — stop"; exit 1; }
done
echo "EXPECT=$(docker inspect -f '{{.Config.Image}}' "$C")"
