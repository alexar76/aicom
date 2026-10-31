#!/usr/bin/env bash
set -euo pipefail
cd /opt/pingblip
expected=3de27d79b4e84618a5a96009136679f85c8632d73e7c7813007b5e7063b6804f
# Run only after docker compose build pingblip forge exits successfully.
docker compose up -d --no-deps --no-build pingblip forge
for spec in 'pingblip https://pingblip.com /pingblip/memeforge/src/components/three/SculptedModel.tsx' 'forge https://forge.pingblip.com /app/src/components/three/SculptedModel.tsx'; do
  read -r service origin source <<< "$spec"
  actual=$(docker compose exec -T "$service" sha256sum "$source" < /dev/null | cut -d ' ' -f 1)
  test "$actual" = "$expected"
  chunk=$(docker compose exec -T "$service" sh -c 'grep -rlF "#c99b48" .next/static/chunks | head -1' < /dev/null)
  test -n "$chunk"
  asset="$origin/_next${chunk#.next}"
  dest="/opt/pingblip-release-backups/liq-ticket-20261030/$service.live.js"
  curl -fsS --retry 12 --retry-delay 2 --retry-all-errors --max-time 15 "$asset" -o "$dest"
  grep -qF '#c99b48' "$dest"
  printf '%s source=%s live_chunk=%s\n' "$service" "$actual" "$asset"
  curl -fsS --retry 6 --retry-delay 2 --retry-all-errors --max-time 15 -o /dev/null -w "$service home HTTP %{http_code}\n" "$origin/"
done
curl -fsS --max-time 15 -o /dev/null -w 'bench HTTP %{http_code}\n' https://pingblip.com/bench
curl -fsS --max-time 15 -o /dev/null -w 'Liq Snake GLB HTTP %{http_code}\n' https://pingblip.com/models/liq-snake.glb
docker compose ps
printf 'DEPLOY_VERIFIED\n'
