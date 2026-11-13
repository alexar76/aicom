#!/usr/bin/env bash
set -euo pipefail
umask 077
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
expected=sha256:e09ea5109b7bdc8e0826b07cfdf9ef5309164e630802de670c693117791b80ec
base=aicom-security:argus-itch-providers-20261113
candidate=aicom-security:argus-itch-geoflow-20261113
root=/root/argus
roster="$root/docker-compose.roster.yml"
backup="$roster.pre-itch-geoflow-20261113"
compose=(docker compose --project-directory "$root" -f "$root/docker-compose.yml" -f "$roster")
test "$(docker inspect -f '{{.Image}}' argus)" = "$expected"
test "$(docker image inspect -f '{{.Id}}' "$base")" = "$expected"
test ! -e "$backup"
sha256sum --check --quiet manifest.sha256
docker build --network none --build-arg "BASE=$base" --tag "$candidate" .
docker run --rm --network none --read-only --cap-drop ALL --entrypoint node "$candidate" --input-type=module -e 'const m=await import("./dist/checkout/itch-browser.js"); if(m.ITCH_PRODUCT.maxCents!==500)process.exit(1);'
cp -p "$roster" "$backup"
trap 'cp -p "$backup" "$roster"; "${compose[@]}" up -d --no-deps --no-build argus' ERR
python3 - "$roster" "$base" "$candidate" <<'PY'
from pathlib import Path
import os
import re
import sys

roster = Path(sys.argv[1])
value, count = re.subn(r"(?m)^(    image: )" + re.escape(sys.argv[2]) + r"(?=[ \n])", lambda match: match[1] + sys.argv[3], roster.read_text())
assert count == 1
temp = roster.with_suffix(".geoflow-tmp")
temp.write_text(value)
temp.chmod(roster.stat().st_mode & 0o777)
os.replace(temp, roster)
PY
"${compose[@]}" up -d --no-deps --no-build argus
for _ in {1..23}; do
  [[ "$(docker inspect -f '{{.State.Health.Status}}' argus)" == healthy ]] && break
  sleep 2
done
test "$(docker inspect -f '{{.State.Health.Status}}' argus)" = healthy
test "$(docker inspect -f '{{.Image}}' argus)" = "$(docker image inspect -f '{{.Id}}' "$candidate")"
curl -fsS --max-time 3 http://127.0.0.1:8787/health >/dev/null
trap - ERR
docker inspect -f '{{.Image}} {{.State.Health.Status}}' argus
