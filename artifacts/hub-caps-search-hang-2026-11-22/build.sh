#!/usr/bin/env bash
# build.sh CONTAINER VARIANT NEW_TAG — overlay FROM the container's running image with the patched page of VARIANT
# (variant-<sha4>/terminal-home.patched.html), on the hub's host. Refuses unless the live page is that variant, then
# checks inside the image (no network) that the file is the patched one and that the hub serves it from /app.
set -euo pipefail
C="$1"; V="$2"; TAG="$3"; D="$(cd "$(dirname "$0")" && pwd)"
BASE="$(docker inspect -f '{{.Config.Image}}' "$C")"
# A container started from a bare image id: BuildKit cannot take an id in FROM, so give that image a local tag.
if [[ "$BASE" == sha256:* ]]; then ID="$BASE"; BASE="${TAG%:*}:capsfix-base-$(date -u +%Y%m%d)"; docker tag "$ID" "$BASE"; echo "tagged ${ID:7:12} as $BASE"; fi
LIVE="$(docker exec "$C" sha256sum /app/terminal-home.html | cut -c1-16)"
WANT="$(sha256sum "$D/$V/terminal-home.html" | cut -c1-16)"
echo "base $BASE, live page $LIVE, variant $V ($WANT) -> $TAG"
[[ "$LIVE" == "$WANT" ]] || { echo "live page is not the variant this patch was made for: stop"; exit 1; }
CTX="$(mktemp -d)"; cp "$D/Dockerfile" "$CTX/"; cp "$D/$V/terminal-home.patched.html" "$CTX/terminal-home.html"
docker build -q --build-arg BASE="$BASE" -t "$TAG" "$CTX" >/dev/null; rm -rf "$CTX"
IMG="$(docker run --rm --network none --entrypoint sha256sum "$TAG" /app/terminal-home.html | cut -c1-16)"
PAT="$(sha256sum "$D/$V/terminal-home.patched.html" | cut -c1-16)"
echo "image page $IMG patched $PAT"; [[ "$IMG" == "$PAT" ]] || { echo "image file differs: stop"; exit 1; }
docker run --rm --network none --entrypoint grep "$TAG" -c capsPageRequest /app/terminal-home.html | sed 's/^/capsPageRequest lines: /'
docker run --rm --network none -e PYTHONPATH=/app -w /app --entrypoint python "$TAG" -c \
  "from aimarket_hub.ui_assets import ui_asset_path; print('served', ui_asset_path('terminal-home.html', '/app'))"
echo "BASE=$BASE"
