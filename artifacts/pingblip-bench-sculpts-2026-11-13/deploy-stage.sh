#!/usr/bin/env bash
set -euo pipefail
release=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
app=/opt/pingblip
cd "$app"
exec 9>/opt/pingblip-releases/.deploy.lock
flock -n 9

service=pingblip
reference=aicom-seo:pingblip-pingblip-5aa4bce94
expected_old=sha256:7b9154c2058c4e7c772f32fefaf1eceb425228719110f572e0f2c779b375b5c9
candidate=pingblip-pingblip:sculpts-20261113-89ed03abf
rollback_tag=pingblip-pingblip:before-sculpts-20261113-89ed03abf
container=$(docker compose ps -q "$service")
test "$(docker inspect -f '{{.Config.Image}}' "$container")" = "$reference"
test "$(docker inspect -f '{{.Image}}' "$container")" = "$expected_old"
test "$(docker image inspect -f '{{.Id}}' "$reference")" = "$expected_old"
docker compose config --quiet
sha256sum docker-compose.yml .env > "$release/config-before.sha256"
sha256sum -c --quiet "$release/source.sha256"
docker tag "$expected_old" "$rollback_tag"
printf 'old %s %s %s\n' "$reference" "$expected_old" "$container" > "$release/deployment.txt"

stage=pingblip-sculpt-build-20261113
stage_id=""
cleanup_stage() {
    if [ -n "$stage_id" ]; then
        docker rm -f "$stage_id" >/dev/null
    fi
}
trap cleanup_stage EXIT
stage_id=$(docker create --name "$stage" --network none "$expected_old")
docker cp "$stage_id:/pingblip/web/docker/entrypoint.sh" "$release/entrypoint-original.sh"
original_hash=$(sha256sum "$release/entrypoint-original.sh" | cut -d' ' -f1)
stage_mode=$(stat -c '%a' "$release/entrypoint-original.sh")
printf '#!/bin/sh\nexec sleep infinity\n' > "$release/entrypoint-build.sh"
chmod "$stage_mode" "$release/entrypoint-build.sh"
docker cp "$release/entrypoint-build.sh" "$stage_id:/pingblip/web/docker/entrypoint.sh"
docker start "$stage_id" >/dev/null
for attempt in $(seq 1 20); do
    if docker exec "$stage_id" sh -c 'test "$(cat /proc/1/comm)" = sleep'; then
        break
    fi
    sleep 1
done
docker exec "$stage_id" sh -c 'test "$(cat /proc/1/comm)" = sleep'
docker cp "$release/entrypoint-original.sh" "$stage_id:/pingblip/web/docker/entrypoint.sh"
docker exec -u 0 "$stage_id" chown node:node /pingblip/web/docker/entrypoint.sh
actual_hash=$(docker exec "$stage_id" sha256sum /pingblip/web/docker/entrypoint.sh | cut -d' ' -f1)
test "$actual_hash" = "$original_hash"
docker cp "$release/payload/public/models/." "$stage_id:/pingblip/web/public/models/"
docker cp "$release/payload/public/dex/." "$stage_id:/pingblip/web/public/dex/"
docker exec -i "$stage_id" sha256sum -c - < "$release/image.sha256" > "$release/candidate-assets.txt"
docker exec "$stage_id" rm -rf .next
docker exec -e NEXT_TELEMETRY_DISABLED=1 -e CIRCLE_NODE_TOTAL=3 -e NODE_OPTIONS=--max-old-space-size=2600 "$stage_id" sh -ec '
    npm run prebuild
    ./node_modules/.bin/next build
' 2>&1 | tee "$release/build-stage.log"
docker exec -i "$stage_id" node -e '
const fs = require("node:fs");
const assert = require("node:assert/strict");
const versions = require("./src/data/model-versions.json");
const expected = fs.readFileSync(0, "utf8").trim().split("\n")
  .map(line => line.match(/^([a-f0-9]{64})  public\/models\/([a-z0-9-]+)\.glb$/))
  .filter(Boolean);
assert.equal(expected.length, 19);
const chunks = fs.readdirSync(".next/static/chunks").filter(name => name.endsWith(".js"))
  .map(name => fs.readFileSync(".next/static/chunks/" + name, "utf8"));
for (const [, checksum, name] of expected) {
  assert.equal(versions[name], checksum.slice(0, 10));
  assert(chunks.some(chunk => chunk.includes(checksum.slice(0, 10))), name);
}
' < "$release/image.sha256"
docker commit "$stage_id" "$candidate"
new=$(docker image inspect -f '{{.Id}}' "$candidate")
test "$new" != "$expected_old"
docker image inspect "$expected_old" "$new" | python3 -c '
import json, sys
old, new = json.load(sys.stdin)
for key in ("User", "WorkingDir", "Env", "Entrypoint", "Cmd", "Healthcheck", "ExposedPorts", "Volumes", "Labels"):
    assert old["Config"].get(key) == new["Config"].get(key), key
'
cleanup_stage
stage_id=""
sha256sum -c --quiet "$release/config-before.sha256"
test "$(docker inspect -f '{{.Image}}' "$(docker compose ps -q "$service")")" = "$expected_old"

rollback() {
    local status=$?
    trap - ERR
    printf 'Switch failed. Restoring %s\n' "$rollback_tag" >&2
    docker tag "$rollback_tag" "$reference"
    docker compose up -d --no-deps --no-build --pull never --wait --wait-timeout 120 "$service"
    exit "$status"
}
trap rollback ERR
docker tag "$candidate" "$reference"
docker compose up -d --no-deps --no-build --pull never --wait --wait-timeout 120 "$service"
ready=false
for attempt in $(seq 1 35); do
    if curl -fsS --max-time 5 http://127.0.0.1:3080/bench -o /dev/null; then
        ready=true
        break
    fi
    sleep 2
done
test "$ready" = true
container=$(docker compose ps -q "$service")
test "$(docker inspect -f '{{.Image}}' "$container")" = "$new"
expected=$(sed -n 's/  public\/models\/glaze-donut\.glb$//p' "$release/image.sha256")
actual=$(curl -fsS --max-time 10 'http://127.0.0.1:3080/models/glaze-donut.glb?v=5bc90e809b' | sha256sum | cut -d' ' -f1)
test "$actual" = "$expected"
sha256sum -c --quiet "$release/config-before.sha256"
printf 'new %s %s %s\n' "$reference" "$new" "$container" >> "$release/deployment.txt"
date -u +%FT%TZ >> "$release/deployment.txt"
trap - ERR
cat "$release/deployment.txt"
docker compose ps
printf 'DEPLOY_OK\n'
