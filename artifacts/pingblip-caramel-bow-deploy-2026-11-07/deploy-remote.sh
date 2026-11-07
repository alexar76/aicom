#!/usr/bin/env bash
set -euo pipefail

release=/opt/pingblip-releases/caramel-bow-20261107-fbd11eee9e
app=/opt/pingblip
services=(pingblip forge world)
files=(
  memeforge/public/models/caramel-bust.glb
  memeforge/public/dex/caramel-bust.webp
  memeforge/public/dex/rendered-from.json
  memeforge/scripts/blender/generate_chrome_sugar.py
  memeforge/scripts/check-seated.mjs
  memeforge/src/data/model-versions.json
  web/src/data/model-versions.json
  world/public/dex/caramel-bust.webp
  world/public/dex/og/caramel-bust.jpg
)

cd "$app"
mkdir -p "$release"
exec 9>/opt/pingblip-releases/.deploy.lock
flock -n 9

rollback() {
  tar -xzf "$release/source-before.tar.gz" -C "$app"
  while read -r service image reference; do
    docker tag "$image" "$reference"
  done < "$release/images-before.tsv"
  docker compose up -d --no-deps --no-build --wait --wait-timeout 120 "${services[@]}"
}

case "${1:-}" in
  prepare)
    docker compose config --quiet
    test ! -e "$release/source-before.tar.gz"
    tar -czf "$release/source-before.tar.gz" "${files[@]}"
    for service in "${services[@]}"; do
      container="$(docker compose ps -q "$service")"
      test -n "$container"
      image="$(docker inspect -f '{{.Image}}' "$container")"
      reference="$(docker inspect -f '{{.Config.Image}}' "$container")"
      docker tag "$image" "pingblip-${service}:prev"
      printf '%s %s %s\n' "$service" "$image" "$reference" >> "$release/images-before.tsv"
    done
    sha256sum docker-compose.yml .env > "$release/config-before.sha256"
    printf 'Prepared rollback for all three applications\n'
    ;;
  apply)
    test -f "$release/source-before.tar.gz"
    python3 -c 'import json,sys; gate=json.load(open(sys.argv[1])); assert gate["passed"] and gate["packages"] > 0' "$release/dependency-scan-clean.json"
    while read -r service image reference; do
      container="$(docker compose ps -q "$service")"
      test "$(docker inspect -f '{{.Image}}' "$container")" = "$image"
    done < "$release/images-before.tsv"
    for file in "${files[@]}"; do
      expected="$(tar -xOf "$release/source-before.tar.gz" "$file" | sha256sum | cut -d ' ' -f 1)"
      test "$(sha256sum "$file" | cut -d ' ' -f 1)" = "$expected"
    done
    sha256sum -c "$release/config-before.sha256"
    trap 'status=$?; trap - ERR; rollback; exit "$status"' ERR
    tar -xzf "$release/payload.tar.gz" -C "$app"
    sha256sum -c "$release/payload.sha256"
    sha256sum -c "$release/config-before.sha256"
    docker compose config --quiet
    docker compose --parallel 1 build "${services[@]}" 2>&1 | tee "$release/build.log"
    docker compose up -d --no-deps --no-build --wait --wait-timeout 120 "${services[@]}"
    for port in 3080 3081 3082; do
      ready=false
      for attempt in $(seq 1 30); do
        if curl -fsS --max-time 5 "http://127.0.0.1:$port/" -o /dev/null; then
          ready=true
          break
        fi
        sleep 2
      done
      test "$ready" = true
    done
    sha256sum -c "$release/config-before.sha256"
    docker compose ps
    date -u +%FT%TZ > "$release/deployed-at.txt"
    printf 'DEPLOY_OK\n'
    ;;
  rollback)
    rollback
    ;;
  *)
    printf 'Usage: %s prepare|apply|rollback\n' "$0" >&2
    exit 2
    ;;
esac
