#!/usr/bin/env bash
# build.sh BASE_IMAGE NEW_TAG — build ARGUS from ctx.tar (git archive 624e03e43 argus) over BASE_IMAGE.
set -euo pipefail
B="$1"; TAG="$2"; D="$(cd "$(dirname "$0")" && pwd)"
rm -rf "$D/ctx" && mkdir -p "$D/ctx" && tar -xmf "$D/ctx.tar" -C "$D/ctx" --strip-components=1
docker build -q --build-arg BASE="$B" -f "$D/argus.Dockerfile" -t "$TAG" "$D/ctx" >/dev/null
docker run --rm --network none --entrypoint node "$TAG" -e "const p=require('/app/package.json');console.log(p.name,p.version)"
docker run --rm --network none --entrypoint sh "$TAG" -c "grep -c 'serverStates' /app/dist/mcp/host.js; grep -c 'notifyOwnerWhenReady' /app/dist/runtime.js; node --version"
echo "built $TAG over $B"
