#!/bin/bash
# ailottery-chain-1 on admin-vps: --preserve-historical-states → bare --prune-history (2026-11-02).
# Anvil kept every historical state: 3.4 GB RSS, ~2.2 GB of anvil-state-* dumps in its tmp per 15 min
# (pruned by cron), a 0.3–2.5 GB state file rewritten every minute. Tested on a copy first (README.md).
#
# Rollback: cp $W/docker-compose.override.yml.pre-prune /root/lottery/docker-compose.override.yml
#           docker stop -t 300 ailottery-chain-1
#           cp $W/live-final-full.json /var/lib/aicom/anvil/ailottery-chain-1/anvil-state.json
#           cd /root/lottery && docker compose -p ailottery -f docker-compose.yml -f docker-compose.override.yml up -d --no-deps chain
set -euo pipefail
W=/root/lotchain-test-20261102
L=/root/lottery
S=/var/lib/aicom/anvil/ailottery-chain-1/anvil-state.json
A=0x5fbdb2315678afecb367f032d93f642f64180aa3
DC=(docker compose -p ailottery -f docker-compose.yml -f docker-compose.override.yml)
rpc() { docker exec ailottery-chain-1 cast "$@" --rpc-url http://localhost:8545; }
log() { echo "$(date -u +%H:%M:%S) $*"; }

cd "$L"
grep -c -- '"--preserve-historical-states"' docker-compose.override.yml | grep -qx 1
cp -p docker-compose.override.yml "$W/docker-compose.override.yml.pre-prune"
docker rm -f lotchain-test-20261102 >/dev/null 2>&1 || true
rm -rf "$W/state" "$W/s2"                      # the test copies; the final dump below replaces them

stopped=0
back() {                                       # any failure after the stop: old flags, full dump, start
  [ "$stopped" = 1 ] || return 0
  log "FAILED, rolling back"
  cp -p "$W/docker-compose.override.yml.pre-prune" "$L/docker-compose.override.yml"
  [ -s "$W/live-final-full.json" ] && cp -p "$W/live-final-full.json" "$S"
  (cd "$L" && "${DC[@]}" up -d --no-deps chain)
  log "rolled back"
}
trap back ERR

b0=$(rpc block-number); h0=$(rpc codehash "$A")
log "live block $b0 codehash $h0 rss $(docker stats --no-stream --format '{{.MemUsage}}' ailottery-chain-1)"

sed -i 's/"--preserve-historical-states"/"--prune-history"/' docker-compose.override.yml
"${DC[@]}" config chain | grep -q -- '- --prune-history'
if "${DC[@]}" config chain | grep -q -- 'preserve-historical-states'; then exit 3; fi
log "override: --prune-history"

t=$(date +%s)
stopped=1
docker stop -t 300 ailottery-chain-1 >/dev/null
log "stopped in $(( $(date +%s) - t ))s; final dump $(stat -c %s "$S") bytes"
cp -p "$S" "$W/live-final-full.json"

off=$(LC_ALL=C grep -boa '"historical_states":' "$S" | head -2 | cut -d: -f1 | tr '\n' ' ')
set -- $off
if [ $# -ne 1 ]; then log "expected one historical_states key, got: $off"; false; fi
if [ "$(dd if="$S" bs=1 skip=$(( $1 - 1 )) count=1 2>/dev/null)" != "," ]; then false; fi
head -c $(( $1 - 1 )) "$S" > "$S.new"
printf '}' >> "$S.new"
chmod 600 "$S.new"
mv "$S.new" "$S"
log "stripped historical states: $(stat -c %s "$S") bytes"

"${DC[@]}" up -d --no-deps chain
for i in $(seq 1 60); do b1=$(rpc block-number 2>/dev/null) && break; sleep 2; done
h1=$(rpc codehash "$A")
log "up: block ${b1:-none} codehash $h1"
if [ -z "${b1:-}" ] || [ "$b1" -lt "$b0" ] || [ "$h1" != "$h0" ]; then false; fi
docker inspect ailottery-chain-1 --format '{{json .Config.Cmd}}'
log DONE
