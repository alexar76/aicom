#!/usr/bin/env bash
# build.sh — image FROM the running okx-a2mcp with this change; refuses when the two files it replaces
# are not the versions the change was written against, or when the container holds copied-in files.
set -euo pipefail
C=okx-a2mcp; D="$(cd "$(dirname "$0")" && pwd)"
BASE="$(docker inspect -f '{{.Config.Image}}' "$C")"
h() { docker exec "$C" sha256sum "/app/$1" 2>/dev/null | cut -c1-12; }
[[ "$(h src/mcp/server.js)" == 1e6211448e56 ]] || { echo "unexpected src/mcp/server.js: $(h src/mcp/server.js)"; exit 3; }
[[ "$(h src/mcp/pages.js)" == b494418c9f7e ]] || { echo "unexpected src/mcp/pages.js: $(h src/mcp/pages.js)"; exit 3; }
[[ -z "$(h src/mcp/modern.js)" ]] || { echo "$C already has src/mcp/modern.js"; exit 3; }
copied="$( (docker diff "$C" | grep -E '^[AC] /app/' || true) | while read -r kind path; do
  docker exec "$C" test -d "$path" || echo "$kind $path"; done)"
[[ -z "$copied" ]] || { echo "files in $C that its image does not have:"; echo "$copied"; exit 4; }
NEW="${BASE}-mcp0728-20261126"
docker build -q --build-arg BASE="$BASE" -t "$NEW" "$D" >/dev/null
echo "$NEW"
