#!/usr/bin/env bash
# roll_apex.sh NEW_TAG — modelmarket-hub right after a publisher payout run, with THEMIS as the only borrower.
NEW="$1"; U=modelmarket-publisher-payout.service
prev="$(systemctl show "$U" -p ExecMainExitTimestampMonotonic --value)"
ok=0
for i in $(seq 1 180); do
  cur="$(systemctl show "$U" -p ExecMainExitTimestampMonotonic --value)"
  st="$(systemctl show "$U" -p ActiveState --value)"
  if [ "$cur" != "$prev" ] && [ "$st" = inactive ]; then ok=1; break; fi
  sleep 1
done
[ "$ok" = 1 ] || { echo "no payout run seen in 180 s; not rolling"; exit 5; }
date -u +"payout run finished, seen %FT%TZ"
HID="$(docker inspect -f "{{.Id}}" modelmarket-hub)"
B="$(docker ps -q | xargs docker inspect -f "{{.Name}} {{.HostConfig.NetworkMode}}" | grep -E "container:($HID|modelmarket-hub)$" | cut -d" " -f1 | tr "\n" " ")"
[ "$B" = "/themis " ] || { echo "borrowers are not themis alone: $B; not rolling"; exit 6; }
./roll.sh modelmarket-hub "$NEW" http://127.0.0.1:9083/ai-market/v2/health,http://127.0.0.1:9460/health
