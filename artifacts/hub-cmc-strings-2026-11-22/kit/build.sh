#!/usr/bin/env bash
# build.sh CONTAINER TAG — the overlay FROM the container's running image, on its host. Refuses unless the running page
# and translations are aicom main's copies before this change (terminal-home.html f85effe3…, hub-ui-i18n.json 90d47378…).
set -euo pipefail
C="$1"; TAG="$2"
D="$(cd "$(dirname "$0")" && pwd)"
for f in /app/terminal-home.html /app/aimarket_hub/static/ui/terminal-home.html; do
  got="$(docker exec "$C" sha256sum "$f" | cut -c1-16)"; [[ "$got" == "f85effe3bc62254a" ]] || { echo "$f differs: $got" >&2; exit 1; }
done
for f in /app/hub-ui-i18n.json /app/aimarket_hub/static/ui/hub-ui-i18n.json; do
  got="$(docker exec "$C" sha256sum "$f" | cut -c1-16)"; [[ "$got" == "90d4737850e9fadf" ]] || { echo "$f differs: $got" >&2; exit 1; }
done
if docker image inspect "$TAG" >/dev/null 2>&1; then echo "tag $TAG already exists" >&2; exit 1; fi
BASE_ID="$(docker inspect -f '{{.Image}}' "$C")"
BASE="nocmcpage-base-$C:20261122"
docker tag "$BASE_ID" "$BASE"
USER_="$(docker inspect -f '{{.Config.User}}' "$C")"; USER_="${USER_:-hub}"
echo "base ${BASE_ID:7:12} ($BASE) user $USER_ -> $TAG"
docker build -q --build-arg BASE="$BASE" --build-arg RUN_USER="$USER_" -t "$TAG" "$D"
docker run --rm --network none --entrypoint sh "$TAG" -c 'grep -ci coinmarketcap /app/terminal-home.html /app/hub-ui-i18n.json || true; grep -c "docs.tavily.com" /app/terminal-home.html'
