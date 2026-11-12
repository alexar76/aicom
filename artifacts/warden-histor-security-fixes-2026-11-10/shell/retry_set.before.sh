#!/bin/sh
# Rerun, once, the servers whose first pass ended in a harness error (a timeout), in a fresh container.
#   retry_set.sh SET CPUS      reads retry/SET.json = {"<tool>": ["<key>", ...]} (written from the normalized first pass)
# The first-pass raw files are moved to raw-firstpass/SET/<tool>/ (kept, never merged back);
# run_competitors.py then runs only the keys whose raw file is missing.
W=/opt/warden-cmp/20261016; s=$1; cpus=$2
[ -f $W/cpus.cap ] && cpus=$(cat $W/cpus.cap)
shares=""; [ -f $W/cpu.shares ] && shares="--cpu-shares $(cat $W/cpu.shares)"
FLAGS="--rm --runtime=runsc --network none --cpus $cpus $shares --memory 2g --memory-swap 2g --pids-limit 512 --read-only --tmpfs /tmp:size=512m -v $W:/work"
[ -d $W/raw-firstpass/$s ] && { echo "$(date -u +%FT%TZ) REFUSE retry $s: already retried"; exit 1; }
python3 - "$W" "$s" <<'PY'
import json, os, shutil, sys
W, s = sys.argv[1:3]
for tool, keys in json.load(open(f'{W}/retry/{s}.json')).items():
    os.makedirs(f'{W}/raw-firstpass/{s}/{tool}', exist_ok=True)
    for k in keys:
        for ext in ('.txt', '.json'):
            p = f'{W}/raw/{s}/{tool}/{k}{ext}'
            if os.path.exists(p): shutil.move(p, f'{W}/raw-firstpass/{s}/{tool}/{k}{ext}')
PY
echo "$(date -u +%FT%TZ) start retry $s cpus=$cpus $shares"
tools=$(python3 -c "import json;print(' '.join(json.load(open('$W/retry/$s.json'))))")
cmd=""; for t in $tools; do cmd="$cmd python3 /work/harness/run_competitors.py /work/sets/$s-config.json /work/raw/$s --installed --only $t --workers 4;"; done
docker run $FLAGS --name warden-cmp-$s-retry warden-cmp:20261016 sh -c "$cmd" > $W/raw/$s-retry.stdout 2>&1
echo "$(date -u +%FT%TZ) done retry $s exit=$?"
