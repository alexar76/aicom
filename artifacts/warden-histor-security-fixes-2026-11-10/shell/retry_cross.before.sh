#!/bin/sh
# Retry on this host, once, the servers of SET whose first pass on another host ended in a harness
# error (timeout). retry/SET.json = {"<tool>": [keys]}. Output goes to raw/SET-retry/<tool>/ only; the
# other host's first-pass raws are not copied here and stay where they are.
#   retry_cross.sh SET CPUS
W=/opt/warden-cmp/20261016; s=$1; cpus=$2
until grep -q "ALL-DONE attested" $W/chain.log; do sleep 60; done
until [ -f $W/retry/$s.json ]; do sleep 60; done
setsid nohup sh $W/hub_watchdog_host2.sh "CROSS-RETRY-DONE $s" > /dev/null 2>&1 < /dev/null &
[ -f $W/cpus.cap ] && cpus=$(cat $W/cpus.cap)
shares=""; [ -f $W/cpu.shares ] && shares="--cpu-shares $(cat $W/cpu.shares)"
AUDIT_W=6; TC_W=8; MS_W=8; SH_W=32; [ -f $W/workers.conf ] && . $W/workers.conf
out=$W/raw/$s-retry; [ -e $out ] && { echo "$(date -u +%FT%TZ) REFUSE cross-retry $s: $out exists"; exit 1; }
mkdir -p $out && chown 1000:1000 $out
python3 - "$W" "$s" <<'PY'
import json, sys
W, s = sys.argv[1:3]
cfg = json.load(open(f'{W}/sets/{s}-config.json'))['mcpServers']
for tool, keys in json.load(open(f'{W}/retry/{s}.json')).items():
    json.dump({'mcpServers': {k: cfg[k] for k in keys}}, open(f'{W}/raw/{s}-retry/{tool}-config.json', 'w'), indent=1)
PY
cmd=""
for t in $(python3 -c "import json;print(' '.join(json.load(open('$W/retry/$s.json'))))"); do
  case $t in mcp-audit) w=$AUDIT_W;; truecopy) w=$TC_W;; mcpsentry) w=$MS_W;; *) w=$SH_W;; esac
  cmd="$cmd python3 /work/harness/run_competitors.py /work/raw/$s-retry/$t-config.json /work/raw/$s-retry --installed --only $t --workers $w;"
done
while docker ps -a --format '{{.Names}}' | grep -q '^warden-cmp-'; do sleep 30; done
echo "$(date -u +%FT%TZ) start cross-retry $s cpus=$cpus $shares"
docker run --rm --runtime=runsc --network none --cpus $cpus $shares --memory 2g --memory-swap 2g --pids-limit 512 --read-only \
  --tmpfs /tmp:size=512m -v $W:/work --name warden-cmp-$s-retry warden-cmp:20261016 sh -c "$cmd" > $out.stdout 2>&1
echo "$(date -u +%FT%TZ) done cross-retry $s exit=$?"
echo "$(date -u +%FT%TZ) CROSS-RETRY-DONE $s"
