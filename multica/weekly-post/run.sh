#!/bin/sh
# Download the public hub counters and collect the week's facts for the Multica agent «недельный пост».
# Prints the paths of week.json and facts.md. curl goes through the agent's egress proxy.
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
STATE_DIR="${WEEKLY_POST_STATE:-$HOME/.local/state/weekly-post}"
RUN="$STATE_DIR/runs/$(date -u +%Y%m%dT%H%M%SZ)"
umask 077
mkdir -p "$RUN/stats"
for host in modelmarket.dev hub.attestedmemory.net; do
  curl -fsS --max-time 60 -A 'aicom-weekly-post/1 (+https://modelmarket.dev)' -o "$RUN/stats/$host.json" "https://$host/ai-market/v2/stats/live"
done
node "$HERE/collect.mjs" --stats-dir "$RUN/stats" --state "$STATE_DIR/snapshots.json" --out "$RUN/week.json" --md "$RUN/facts.md"
echo "facts: $RUN/facts.md"
echo "data: $RUN/week.json"
ls -1d "$STATE_DIR"/runs/*/ 2>/dev/null | sort | head -n -12 | while read -r old; do rm -rf "$old"; done
