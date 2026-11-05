#!/bin/bash
# On attested: bash build.sh  -> aicom-security:helios-worker-tts-20261105, smoke inside it.
set -euo pipefail
cd "$(dirname "$0")"
TAG=aicom-security:helios-worker-tts-20261105
docker build --progress=plain -t "$TAG" . 2>&1 | grep -E "^#[0-9]+ [0-9.]+ (--- packages|[<>] )|ERROR|naming to" || true
docker image inspect "$TAG" --format "built {{.Id}} user={{.Config.User}} cmd={{json .Config.Cmd}}" | cut -c1-160
docker run --rm --entrypoint python --cpus 1 --memory 512m -v "$PWD/smoke.py:/tmp/smoke.py:ro" "$TAG" /tmp/smoke.py
