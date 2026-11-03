#!/usr/bin/env bash
# build.sh CONTAINER NEW_TAG — overlay FROM the container's running image (terminal-home.html only, from this folder),
# then check inside the image, with no network: the file equals the context, it carries the refresh, and the hub
# resolves its landing page to that file. Prints the EXPECT image for roll.sh.
set -euo pipefail
C="$1"; TAG="$2"; D="$(cd "$(dirname "$0")" && pwd)"
BASE="$(docker inspect -f '{{.Config.Image}}' "$C")"
LIVE="$(docker exec "$C" sha256sum /app/terminal-home.html | cut -c1-16)"
echo "base $BASE ($(docker inspect -f '{{.Image}}' "$C" | cut -c8-19)), live page $LIVE, base expected $(cat "$D/BASE_SHA16") -> $TAG"
[[ "$LIVE" == "$(cat "$D/BASE_SHA16")" ]] || { echo "live page is not the variant this patch was made for — stop"; exit 1; }
docker build -q --build-arg BASE="$BASE" -t "$TAG" "$D" >/dev/null
IMG="$(docker run --rm --network none --entrypoint sha256sum "$TAG" /app/terminal-home.html | cut -c1-16)"
CTX="$(sha256sum "$D/terminal-home.html" | cut -c1-16)"
echo "image $IMG context $CTX"; [[ "$IMG" == "$CTX" ]] || { echo "image file differs — stop"; exit 1; }
docker run --rm --network none --entrypoint grep "$TAG" -c PEERS_TTL_MS /app/terminal-home.html | sed 's/^/PEERS_TTL_MS lines: /'
# Newer hubs resolve the page through ui_assets; older ones join it to hub_root (/app) in hub_routes/pages.py.
docker run --rm --network none -e PYTHONPATH=/app -w /app --entrypoint python "$TAG" -c \
  "import importlib.util as u, pathlib as p
if u.find_spec('aimarket_hub.ui_assets'):
    from aimarket_hub.ui_assets import ui_asset_path; print('served', ui_asset_path('terminal-home.html', '/app'))
else:
    src = p.Path('/app/aimarket_hub/hub_routes/pages.py').read_text()
    print('served /app/terminal-home.html (pages.py joins hub_root)' if 'os.path.join(hub_root, \"terminal-home.html\")' in src else 'UNKNOWN page path')"
echo "EXPECT=$BASE"
