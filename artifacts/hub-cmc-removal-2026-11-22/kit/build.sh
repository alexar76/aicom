#!/usr/bin/env bash
# build.sh CONTAINER TAG — the overlay FROM the container's running image, on its host. Refuses unless the
# running external_services.py is aicom main's copy before this change (sha256 f786c49a043c32d8…).
set -euo pipefail
C="$1"; TAG="$2"
D="$(cd "$(dirname "$0")" && pwd)"
got="$(docker exec "$C" sha256sum /app/aimarket_hub/external_services.py | cut -c1-16)"
[[ "$got" == "f786c49a043c32d8" ]] || { echo "running external_services.py differs: $got" >&2; exit 1; }
BASE_ID="$(docker inspect -f '{{.Image}}' "$C")"
BASE="nocmc2-base-$C:20261122"
docker tag "$BASE_ID" "$BASE"
USER_="$(docker inspect -f '{{.Config.User}}' "$C")"; USER_="${USER_:-hub}"
echo "base ${BASE_ID:7:12} ($BASE) user $USER_ -> $TAG"
docker build -q --build-arg BASE="$BASE" --build-arg RUN_USER="$USER_" -t "$TAG" "$D"
docker run --rm --network none --entrypoint python -w /app "$TAG" -c \
  'import aimarket_hub, aimarket_hub.external_services as e; print("image", aimarket_hub.__version__, "external", [s["id"] for s,_ in e._SERVICES])'
