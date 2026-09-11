#!/usr/bin/env bash
# Restart a watched container that Docker has marked unhealthy.
#
# Why: signal-hunt-hub-1 hung with its health check timing out and STAYED that way —
# "Up 2 hours (unhealthy)" — because an unhealthy container is not a restarted one.
# hunt.modelmarket.dev served nothing for the duration. Docker has no restart-on-unhealthy,
# so this is it.
#
# Named containers only, never "everything unhealthy on the host": a blanket restarter
# eventually bounces a database mid-write because something upstream of it was sick.
set -uo pipefail

# Overridable so the restart path can be tested against a disposable container.
read -r -a WATCHED <<< "${AICOM_AUTOHEAL_WATCH:-signal-hunt-hub-1}"
STATE_DIR=/var/lib/aicom-autoheal
mkdir -p "$STATE_DIR"

# Two consecutive unhealthy observations before acting. A single one is also what a
# container looks like a second after it starts, and restarting a starting container is
# how a boot loop is built.
for name in "${WATCHED[@]}"; do
  status="$(docker inspect "$name" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' 2>/dev/null || echo missing)"
  marker="$STATE_DIR/$name.unhealthy"
  if [ "$status" != "unhealthy" ]; then
    rm -f "$marker"
    continue
  fi
  if [ ! -f "$marker" ]; then
    : > "$marker"
    echo "$name unhealthy (first observation, not acting yet)"
    continue
  fi
  # Do not fight a container that is already being restarted repeatedly: back off after
  # three restarts in an hour and leave it for a human, so a broken image is not hidden
  # behind a restart every two minutes.
  log="$STATE_DIR/$name.restarts"
  now=$(date -u +%s)
  recent=0
  if [ -f "$log" ]; then
    recent=$(awk -v c="$now" '($1 > c - 3600)' "$log" | wc -l | tr -d ' ')
  fi
  if [ "$recent" -ge 3 ]; then
    echo "$name unhealthy but already restarted $recent times this hour — leaving it alone"
    continue
  fi
  echo "$name unhealthy twice — restarting"
  if docker restart "$name" >/dev/null 2>&1; then
    echo "$now" >> "$log"
    rm -f "$marker"
    echo "$name restarted"
  else
    echo "$name restart FAILED"
  fi
done
