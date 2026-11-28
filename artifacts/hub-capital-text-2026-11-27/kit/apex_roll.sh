#!/usr/bin/env bash
# apex_roll.sh NEW_TAG — modelmarket-hub on factory-vps: wait until a publisher payout run has just finished, check that
# only themis shares the hub's network namespace, then roll at once (the payout one-shot must never be re-created).
D="$(cd "$(dirname "$0")" && pwd)"; NEW="$1"; U=modelmarket-publisher-payout.service
last="$(systemctl show "$U" -p ExecMainExitTimestampMonotonic --value)"
for i in $(seq 1 180); do
  now="$(systemctl show "$U" -p ExecMainExitTimestampMonotonic --value)"; st="$(systemctl is-active "$U")"
  if [[ "$now" != "$last" && "$st" == "inactive" ]]; then break; fi
  sleep 1
done
[[ "$now" != "$last" ]] || { echo "no payout run finished in 180 s; not rolling"; exit 4; }
HUB="$(docker inspect -f '{{.Id}}' modelmarket-hub)"
B="$(docker ps -q | xargs docker inspect -f '{{.Name}} {{.HostConfig.NetworkMode}}' | awk -v h="container:$HUB" '$2==h{print $1}' | tr '\n' ' ')"
echo "payout run finished; namespace borrowers: $B"
[[ "$B" == "/themis " ]] || { echo "unexpected borrowers; not rolling"; exit 5; }
bash "$D/roll.sh" modelmarket-hub "$NEW" http://127.0.0.1:9083/ai-market/v2/health,http://127.0.0.1:9460/health
