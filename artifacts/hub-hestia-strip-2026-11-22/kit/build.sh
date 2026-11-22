#!/usr/bin/env bash
# build.sh BASE_TAG NEW_TAG — the overlay FROM the live image. Refuses unless that image's two UI files are main's
# copies before this change (terminal-home.html 42e621f1…, hub-ui-i18n.json fcbe69e8…).
set -euo pipefail
BASE="$1"; TAG="$2"
D="$(cd "$(dirname "$0")" && pwd)"
got="$(docker run --rm --network none --entrypoint sh "$BASE" -c 'sha256sum /app/terminal-home.html /app/hub-ui-i18n.json' | cut -c1-16 | tr '\n' ' ')"
[[ "$got" == "42e621f171b1c1cd fcbe69e859b53da4 " ]] || { echo "base UI files differ: $got" >&2; exit 1; }
USER_="$(docker image inspect -f '{{.Config.User}}' "$BASE")"; USER_="${USER_:-hub}"
echo "base $(docker image inspect -f '{{.Id}}' "$BASE" | cut -c8-19) ($BASE) user $USER_ -> $TAG"
docker build -q --build-arg BASE="$BASE" --build-arg RUN_USER="$USER_" -t "$TAG" "$D"
docker run --rm --network none --entrypoint sh "$TAG" -c 'sha256sum /app/terminal-home.html /app/hub-ui-i18n.json /app/aimarket_hub/static/ui/terminal-home.html' | cut -c1-16
