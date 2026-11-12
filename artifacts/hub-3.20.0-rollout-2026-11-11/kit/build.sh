#!/usr/bin/env bash
# build.sh CONTAINER TAG [KEEP_UI] [WEB_PINS] — hub 3.20.0 FROM the container's running image, on its host.
# Run from the kit directory copied to the host. Prints the activation result and EXPECT (the base image id)
# for rollout_container.py's check.
set -euo pipefail
C="$1"; TAG="$2"; KEEP_UI="${3:-0}"; WEB_PINS="${4:-}"
D="$(cd "$(dirname "$0")" && pwd)"
BASE_ID="$(docker inspect -f '{{.Image}}' "$C")"
# BuildKit cannot build FROM a bare image id: name the running image for the build.
BASE="hub320-base-$C:20261111"
docker tag "$BASE_ID" "$BASE"
USER_="$(docker inspect -f '{{.Config.User}}' "$C")"; USER_="${USER_:-hub}"
echo "base ${BASE_ID:7:12} ($BASE) user $USER_ keep_ui $KEEP_UI web_pins '${WEB_PINS}' -> $TAG"
docker build --build-arg BASE="$BASE" --build-arg RUN_USER="$USER_" --build-arg KEEP_UI="$KEEP_UI" \
  --build-arg WEB_PINS="$WEB_PINS" -t "$TAG" "$D" 2>&1 | grep -E '"version": "3.20.0"|pip check|No broken|has requirement|ERROR|error' || true
docker image inspect "$TAG" >/dev/null
docker run --rm --network none --entrypoint python -w /app "$TAG" -c \
  'import aimarket_hub, importlib.metadata as m; print("image", aimarket_hub.__file__, aimarket_hub.__version__, "fastapi", m.version("fastapi"))'
echo "EXPECT=$BASE_ID"
