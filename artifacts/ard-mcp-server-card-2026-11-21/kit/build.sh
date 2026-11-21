#!/usr/bin/env bash
# build.sh CONTAINER TAG — the overlay FROM the container's running image, on its host. Refuses unless the
# image's ard.py and hub_routes/ard.py are the files the overlay copies were made from (aicom main ad4065b30).
set -euo pipefail
C="$1"; TAG="$2"
D="$(cd "$(dirname "$0")" && pwd)"
want_ard=5d81b5440800c84f; want_routes=155009bc66291a44
got_ard="$(docker exec "$C" sha256sum /app/aimarket_hub/ard.py | cut -c1-16)"
got_routes="$(docker exec "$C" sha256sum /app/aimarket_hub/hub_routes/ard.py | cut -c1-16)"
[[ "$got_ard" == "$want_ard" && "$got_routes" == "$want_routes" ]] || { echo "running files differ: ard $got_ard routes $got_routes" >&2; exit 1; }
BASE_ID="$(docker inspect -f '{{.Image}}' "$C")"
BASE="ardcard-base-$C:20261121"
docker tag "$BASE_ID" "$BASE"
USER_="$(docker inspect -f '{{.Config.User}}' "$C")"; USER_="${USER_:-hub}"
echo "base ${BASE_ID:7:12} ($BASE) user $USER_ -> $TAG"
docker build -q --build-arg BASE="$BASE" --build-arg RUN_USER="$USER_" -t "$TAG" "$D"
docker run --rm --network none --entrypoint python -w /app "$TAG" -c \
  'import aimarket_hub, aimarket_hub.ard as a; print("image", aimarket_hub.__version__, "mcp card", a.MCP_SERVER_CARD_PATH)'
echo "EXPECT=$BASE_ID"
