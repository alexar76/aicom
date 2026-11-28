#!/usr/bin/env bash
# build.sh — the candidate image, not the switch. Refuses unless `latest` is the image this was prepared against
# and the six files in it are the ones the change was written on.
set -euo pipefail
D="$(cd "$(dirname "$0")" && pwd)"
BASE_ID=sha256:745fac7bdf3d313b0a425bbeef5fc662f1815d11f799efc61bd652bf0ab47940
LIVE_ID=sha256:feabed44d9420c88a93b9aa89292f438372ebe82f51318a98091d082033574b7
[ "$(docker image inspect -f '{{.Id}}' histor-histor:latest)" = "$BASE_ID" ] || { echo "latest is not $BASE_ID"; exit 3; }
[ "$(docker inspect -f '{{.Image}}' histor-histor-1)" = "$LIVE_ID" ] || { echo "production does not run $LIVE_ID"; exit 3; }
want="check.py 6c1a5ec57160
config.py 4bc09b593948
crawler.py 4166d23f448b
mcpclient.py 928e1982c2d8
migrations.py 98988a92479b
store.py 745616459b70"
have="$(for f in check.py config.py crawler.py mcpclient.py migrations.py store.py; do
  echo "$f $(docker run --rm --network none --entrypoint sha256sum "$BASE_ID" /app/histor/$f | cut -c1-12)"; done)"
[ "$have" = "$want" ] || { echo "unexpected files in latest:"; diff <(echo "$want") <(echo "$have"); exit 3; }
(cd "$D/overlay" && sha256sum -c ../overlay.sha256 >/dev/null)
docker tag "$BASE_ID" histor-histor:pre-other-revision-20261127
# BuildKit does not take a bare image id in FROM: the tag just set to it is used.
docker build -q --build-arg BASE=histor-histor:pre-other-revision-20261127 -t histor-histor:other-revision-20261127 "$D" > "$D/build.log" 2>&1
NEW="$(docker image inspect -f '{{.Id}}' histor-histor:other-revision-20261127)"
echo "$NEW" > "$D/new-image-id"; echo "$BASE_ID" > "$D/base-image-id"; echo "$LIVE_ID" > "$D/old-image-id"
for f in check.py config.py crawler.py mcpclient.py migrations.py store.py; do
  a="$(docker run --rm --network none --entrypoint sha256sum "$NEW" /app/histor/$f | cut -d' ' -f1)"
  b="$(grep " histor/$f\$" "$D/overlay.sha256" | cut -d' ' -f1)"; [ "$a" = "$b" ] || { echo "$f in the image is not the kit's"; exit 4; }
done
docker run --rm --network none -e PYTHONPATH=/app -w /app -v "$D/smoke.py:/tmp/smoke.py:ro" --entrypoint python "$NEW" /tmp/smoke.py 2>&1 | tail -1
echo "built $NEW"
