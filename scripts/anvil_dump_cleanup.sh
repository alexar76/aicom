#!/bin/sh
# Remove leaked Foundry Anvil on-disk state caches from alien-monitor.
#
# Anvil keeps a disk cache of recent chain states in
# $HOME/.foundry/anvil/tmp/anvil-state-<utc>-<random>/ (one JSON per cached
# state, about 3600 files, ~11 GB). Since the monitor runs as uid 10001,
# that home is /home/monitor, inside the container writable layer — not the
# bind-mounted universe. Each time the monitor recycles anvil, the old
# directory is left behind. The live chain is /app/data/universe/anvil-state
# and is never touched here.
#
# Keeps the newest anvil-state-* directory when it was modified in the last
# 24h (the cache the running anvil is still filling). Deletes every other
# anvil-state-* directory. Does not restart alien-monitor.
set -eu

LOG=/var/log/anvil-dump-cleanup.log

if ! docker inspect -f '{{.State.Running}}' alien-monitor 2>/dev/null | grep -qx true; then
  exit 0
fi

note=$(docker exec alien-monitor sh -c '
set -eu
TMP=/home/monitor/.foundry/anvil/tmp
[ -d "$TMP" ] || exit 0
cd "$TMP"
found=0
newest=
newest_m=0
for d in anvil-state-*; do
  [ -d "$d" ] || continue
  found=1
  m=$(stat -c %Y "$d")
  if [ "$m" -ge "$newest_m" ]; then
    newest=$d
    newest_m=$m
  fi
done
[ "$found" -eq 1 ] || exit 0
now=$(date +%s)
for d in anvil-state-*; do
  [ -d "$d" ] || continue
  m=$(stat -c %Y "$d")
  age=$((now - m))
  if [ "$d" = "$newest" ] && [ "$age" -lt 86400 ]; then
    continue
  fi
  rm -rf "$d"
  printf "removed %s age_s=%s\n" "$d" "$age"
done
')

if [ -n "$note" ]; then
  printf '%s %s\n' "$(date -Is)" "$note" >> "$LOG"
fi
