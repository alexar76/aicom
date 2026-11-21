#!/usr/bin/env bash
# build.sh BASE_TAG NEW_TAG — the overlay FROM the 3.22.0 release image. Refuses unless that image's two UI files
# are main's copies before this change (terminal-home.html a915a3af…, hub-ui-i18n.json 1f4ca846…).
set -euo pipefail
BASE="$1"; TAG="$2"
D="$(cd "$(dirname "$0")" && pwd)"
got="$(docker run --rm --network none --entrypoint sh "$BASE" -c 'sha256sum /app/terminal-home.html /app/hub-ui-i18n.json' | cut -c1-16 | tr '\n' ' ')"
[[ "$got" == "a915a3afa17504f6 1f4ca8460375da30 " ]] || { echo "base UI files differ: $got" >&2; exit 1; }
USER_="$(docker image inspect -f '{{.Config.User}}' "$BASE")"; USER_="${USER_:-hub}"
echo "base $(docker image inspect -f '{{.Id}}' "$BASE" | cut -c8-19) ($BASE) user $USER_ -> $TAG"
docker build -q --build-arg BASE="$BASE" --build-arg RUN_USER="$USER_" -t "$TAG" "$D"
docker run --rm --network none --entrypoint python -w /app "$TAG" -c \
  'import aimarket_hub, aimarket_hub.external_services as e; print("image", aimarket_hub.__version__, "external", [s["id"] for s,_ in e._SERVICES])'
