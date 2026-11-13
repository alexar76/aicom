#!/usr/bin/env bash
set -euo pipefail
release=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
cd /opt/pingblip
exec 9>/opt/pingblip-releases/.deploy.lock
flock -n 9

service=pingblip
reference=aicom-seo:pingblip-pingblip-5aa4bce94
old=sha256:d0bded0cfc1d8243c727d588f4c1490bf3ad4fc68076808bd8cae2d8d01bdd8f
candidate=pingblip-pingblip:banana-20261113-898f3a19
rollback_tag=pingblip-pingblip:before-banana-20261113-898f3a19
renderer=/pingblip/memeforge/src/components/three/SculptedModel.tsx
old_source=3de27d79b4e84618a5a96009136679f85c8632d73e7c7813007b5e7063b6804f
new_source=898f3a1955b7066340365be7a32c0ced18f2bb4d56e2322565780dc888fd3ac8
model=e23d6f0f63898e23751e875b092ebafda0b98a15924a70da5d4cd746cf7e777f
entrypoint=/pingblip/web/docker/entrypoint.sh

live_image() { docker inspect -f '{{.Image}}' "$(docker compose ps -q "$service")"; }
image_id() { docker image inspect -f '{{.Id}}' "$1"; }
check_source() { test "$(docker exec "$1" sha256sum "$renderer" | cut -d' ' -f1)" = "$2"; }
check_old() {
    test "$(live_image)" = "$old"
    test "$(image_id "$reference")" = "$old"
    test "$(docker inspect -f '{{.Config.Image}}' "$(docker compose ps -q "$service")")" = "$reference"
}

stage_image() {
    check_old
    docker compose config --quiet
    check_source "$(docker compose ps -q "$service")" "$old_source"
    test "$(sha256sum "$release/SculptedModel.tsx" | cut -d' ' -f1)" = "$new_source"
    sha256sum docker-compose.yml .env > "$release/config-before.sha256"
    for s in forge world postgres; do docker compose ps -q "$s"; done > "$release/neighbors-before.txt"
    docker tag "$old" "$rollback_tag"

    stage_id=$(docker create --name pingblip-banana-build-20261113-898f3a19 --network none \
        --memory 5g --cpus 2 "$old")
    trap 'docker rm -f "$stage_id" >/dev/null' EXIT
    docker cp "$stage_id:$entrypoint" "$release/entrypoint-original.sh"
    printf '#!/bin/sh\nexec sleep infinity\n' > "$release/entrypoint-build.sh"
    chmod --reference="$release/entrypoint-original.sh" "$release/entrypoint-build.sh"
    docker cp "$release/entrypoint-build.sh" "$stage_id:$entrypoint"
    docker start "$stage_id" >/dev/null
    for _ in $(seq 1 20); do
        if docker exec "$stage_id" sh -c 'test "$(cat /proc/1/comm)" = sleep'; then break; fi
        sleep 1
    done
    docker exec "$stage_id" sh -c 'test "$(cat /proc/1/comm)" = sleep'
    docker cp "$release/entrypoint-original.sh" "$stage_id:$entrypoint"
    docker cp "$release/SculptedModel.tsx" "$stage_id:$renderer"
    docker exec -u 0 "$stage_id" chown node:node "$entrypoint" "$renderer"
    test "$(docker exec "$stage_id" sha256sum "$entrypoint" | cut -d' ' -f1)" = \
        "$(sha256sum "$release/entrypoint-original.sh" | cut -d' ' -f1)"
    check_source "$stage_id" "$new_source"
    local old_build new_build chunk new
    old_build=$(docker exec "$stage_id" cat .next/BUILD_ID)
    docker exec -e NEXT_TELEMETRY_DISABLED=1 -e CIRCLE_NODE_TOTAL=3 \
        -e NODE_OPTIONS=--max-old-space-size=2600 "$stage_id" sh -ec '
            npm run prebuild
            ./node_modules/.bin/next build
        '
    new_build=$(docker exec "$stage_id" cat .next/BUILD_ID)
    test "$new_build" != "$old_build"
    chunk=$(docker exec "$stage_id" sh -ec 'grep -rlF "totalEmissiveRadiance *= diffuseColor.rgb;" .next/static/chunks | head -n 1')
    test -n "$chunk"
    docker commit "$stage_id" "$candidate" >/dev/null
    new=$(image_id "$candidate")
    test "$new" != "$old"
    docker image inspect "$old" "$new" | python3 -c '
import json, sys
old, new = json.load(sys.stdin)
for key in ("User", "WorkingDir", "Env", "Entrypoint", "Cmd", "Healthcheck", "ExposedPorts", "Volumes", "Labels"):
    assert old["Config"].get(key) == new["Config"].get(key), key
'
    printf '%s\n' "$new" "$new_build" "${chunk#.next/}" > "$release/candidate.txt"
    printf 'CANDIDATE_OK %s %s %s\n' "$new" "$new_build" "$chunk"
}

switch_game() {
    check_old
    sha256sum -c --quiet "$release/config-before.sha256"
    local new chunk cid
    new=$(sed -n '1p' "$release/candidate.txt")
    chunk=$(sed -n '3p' "$release/candidate.txt")
    test "$(image_id "$candidate")" = "$new"
    test "$(image_id "$rollback_tag")" = "$old"
    printf 'old %s %s\n' "$reference" "$old" > "$release/deployment.txt"
    trap 'status=$?; if (( BASH_SUBSHELL == 0 )); then rollback "$status"; fi' ERR
    docker tag "$candidate" "$reference"
    docker compose up -d --no-deps --no-build --pull never --wait --wait-timeout 120 "$service"
    local ready=false deadline=$((SECONDS + 240))
    while (( SECONDS < deadline )); do
        if curl -fs --max-time 20 http://127.0.0.1:3080/bench -o /dev/null; then ready=true; break; fi
        sleep 3
    done
    test "$ready" = true
    cid=$(docker compose ps -q "$service")
    test "$(live_image)" = "$new"
    check_source "$cid" "$new_source"
    test "$(curl -fsS --max-time 30 "http://127.0.0.1:3080/models/bruised-banana.glb?v=${model:0:10}" | sha256sum | cut -d' ' -f1)" = "$model"
    curl -fsS --max-time 30 "http://127.0.0.1:3080/_next/$chunk" | grep -F 'totalEmissiveRadiance *= diffuseColor.rgb;' >/dev/null
    sha256sum -c --quiet "$release/config-before.sha256"
    for s in forge world postgres; do docker compose ps -q "$s"; done | diff - "$release/neighbors-before.txt"
    trap - ERR
    printf 'new %s %s %s\n' "$reference" "$new" "$cid" >> "$release/deployment.txt"
    date -u +%FT%TZ >> "$release/deployment.txt"
    cat "$release/deployment.txt"
    printf 'DEPLOY_OK\n'
}

rollback() {
    trap - ERR
    printf 'Switch failed; restoring %s\n' "$rollback_tag" >&2
    docker tag "$rollback_tag" "$reference"
    docker compose up -d --no-deps --no-build --pull never --wait --wait-timeout 120 "$service"
    exit "$1"
}

case "${1:-}" in
    stage) stage_image ;;
    switch) set -E; switch_game ;;
    *) exit 2 ;;
esac
