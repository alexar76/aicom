#!/bin/bash
# Who spends attested's unauthenticated GitHub limit (2026-11-05). For up to MAX_S seconds, reads the limit every
# 5 s (the /rate_limit call is free). When `used` grows, samples every container's and the host's connections to
# GitHub's 140.82.112.0/20 every 0.3 s for 30 s and prints who held them. Counts only, no payloads.
set -u
MAX_S=${MAX_S:-7200}
rl() { curl -4 -sS -m 8 https://api.github.com/rate_limit | python3 -c "import json,sys; print(json.load(sys.stdin)['resources']['core']['used'])" 2>/dev/null || echo -1; }
IPS='140\.82\.(11[2-9]|12[0-7])\.[0-9]+'
declare -A NAME=()
for c in $(docker ps -q); do
  open=0
  for n in $(docker inspect -f '{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}' "$c"); do
    [ "$n" = host ] && open=1
    [ "$(docker network inspect -f '{{.Internal}}' "$n" 2>/dev/null)" = false ] && open=1
  done
  [ $open = 1 ] && NAME[$(docker inspect -f '{{.State.Pid}}' "$c")]=$(docker inspect -f '{{.Name}}' "$c" | tr -d /)
done
echo "containers with internet access: ${#NAME[@]}"
prev=$(rl); echo "$(date -u +%T) used $prev; watching up to ${MAX_S}s"
start=$SECONDS
while [ $((SECONDS - start)) -lt "$MAX_S" ]; do
  sleep 2
  now=$(rl)
  [ "$now" -le "$prev" ] 2>/dev/null && { prev=$now; continue; }
  echo "$(date -u +%T) used $prev -> $now: sampling connections"
  end=$((SECONDS + 45))
  while [ $SECONDS -lt $end ]; do
    for pid in "${!NAME[@]}"; do nsenter -t "$pid" -n ss -tnH 2>/dev/null | grep -E "($IPS):443" | awk -v n="${NAME[$pid]}" '{print n, $5}'; done
    ss -tnpH 2>/dev/null | grep -E "($IPS):443" | awk '{print "HOST", $5, $6}'
    sleep 0.1
  done | sort | uniq -c | sort -rn | head -20
  echo "$(date -u +%T) used now $(rl)"
  exit 0
done
echo "$(date -u +%T) no growth in ${MAX_S}s (used $prev)"
