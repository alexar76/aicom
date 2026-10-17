#!/bin/bash
# Prune anvil's unbounded dump cache. Runs every 15 minutes on the oracle host.
#
# Anvil writes a FULL state dump into ~/.foundry/anvil/tmp/anvil-state-* on every
# dump and never removes any of them. The in-process sweeper in alien-monitor
# covers that container; this script is the same pass for ailottery-chain-1
# (and a belt around the monitor if the in-process pass is down).
#
# Keep the newest dump directory and a handful of files inside it. Drop the rest.
# If the disk is already tight, keep only the current file.

KEEP_DIRS=1
KEEP_FILES=3
CONTAINERS="ailottery-chain-1 alien-monitor"
LOG=/var/log/prune-anvil-state.log

USE=$(df --output=pcent / | tail -1 | tr -dc '0-9')
[ "${USE:-0}" -ge 85 ] && KEEP_DIRS=1 && KEEP_FILES=1

for C in $CONTAINERS; do
  docker inspect -f '{{.State.Running}}' "$C" 2>/dev/null | grep -q true || continue
  # The cache is under the HOME of the user the container runs as: /root for the lottery
  # chain, /home/monitor for alien-monitor since it runs as uid 10001. Pruning /root only
  # missed the monitor's ~11 GB directories, and on 2026-10-13 they filled admin-vps.
  freed=$(docker exec "$C" sh -c "
    total=0
    for TMP in /root/.foundry/anvil/tmp \"\${HOME:-/root}/.foundry/anvil/tmp\"; do
    [ -d \"\$TMP\" ] || continue
    [ \"\$TMP\" = \"\${seen:-}\" ] && continue
    seen=\$TMP
    before=\$(du -sm \"\$TMP\" 2>/dev/null | cut -f1)
    # Newest dump dir first.
    dirs=\$(ls -1dt \"\$TMP\"/anvil-state-* 2>/dev/null)
    [ -z \"\$dirs\" ] && continue
    n=0
    echo \"\$dirs\" | while IFS= read -r d; do
      [ -n \"\$d\" ] || continue
      n=\$((n + 1))
      if [ \$n -le $KEEP_DIRS ]; then
        [ -d \"\$d\" ] || continue
        ls -1t \"\$d\"/* 2>/dev/null | tail -n +\$(( $KEEP_FILES + 1 )) | xargs -r rm -f
      else
        rm -rf \"\$d\"
      fi
    done
    after=\$(du -sm \"\$TMP\" 2>/dev/null | cut -f1)
    total=\$(( total + \${before:-0} - \${after:-0} ))
    done
    echo \$total
  " 2>/dev/null || echo 0)
  [ "${freed:-0}" -gt 0 ] && echo "$(date -Is) $C freed ${freed}MB (keep_dirs=$KEEP_DIRS keep_files=$KEEP_FILES, disk=${USE}%)" >> "$LOG"
done

[ -f "$LOG" ] && tail -n 500 "$LOG" > "$LOG.t" && mv "$LOG.t" "$LOG"
