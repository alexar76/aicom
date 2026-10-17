#!/usr/bin/env bash
set -euo pipefail
release=/root/alien-oracles-20261014-2230
repo=/root/claudecode/aicom
image=alien-monitor:local-oracles-20261014-2230
mkdir -p "$release"
cd "$release"
for name in alien-monitor-live alien-monitor; do
  docker inspect "$name" --format '{{.Config.Image}}' > "$name.previous-image"
done
base=$(cat alien-monitor-live.previous-image)
test "$base" = "$(cat alien-monitor.previous-image)"
tar -czf frontend-source-before.tar.gz -C "$repo" alien-monitor/frontend/src alien-monitor/frontend/vite.config.ts alien-monitor/frontend/public/fonts alien-monitor/frontend/index.html alien-monitor/frontend/momus-eye.html
cp /tmp/alien-oracles-source.tar.gz /tmp/alien-oracles-dist.tar.gz .
tar -xzf alien-oracles-dist.tar.gz
printf 'FROM %s\nCOPY --chown=10001:10001 dist/ /app/frontend/dist/\n' "$base" > Dockerfile
docker build -t "$image" .
# Keep the exact source alongside the compiled release for subsequent full builds.
tar -xzf alien-oracles-source.tar.gz -C "$repo"
for name in alien-monitor-live alien-monitor; do
  if ! "$repo/scripts/redeploy_alien_monitor_live.sh" "$name" --image "$image"; then
    "$repo/scripts/redeploy_alien_monitor_live.sh" "$name" --image "$(cat "$name.previous-image")"
    exit 1
  fi
done
docker ps --filter name=alien-monitor --format '{{.Names}} {{.Image}} {{.Status}}'
