#!/usr/bin/env bash
# Run on factory-vps after the local channel regression suites pass.
set -euo pipefail
cd "$(dirname "$0")"
expected='55b05e18ee254429f2168915b9a2a28f11472a83725e4af1b3f714160983f89b'
actual="$(docker exec modelmarket-hub sha256sum /app/aimarket_hub/a2a.py | cut -d' ' -f1)"
[[ "$actual" == "$expected" ]] || { echo 'Live module changed; refuse patch.' >&2; exit 1; }
base_id="$(docker inspect modelmarket-hub --format '{{.Image}}')"
base_tag="$(docker inspect modelmarket-hub --format '{{.Config.Image}}')"
[[ "$(docker image inspect "$base_tag" --format '{{.Id}}')" == "$base_id" ]] || exit 1
printf 'FROM %s\nCOPY a2a.py /app/aimarket_hub/a2a.py\n' "$base_tag" > Dockerfile.hotfix
docker build --network=none -f Dockerfile.hotfix -t modelmarket-hub:a2a-output-20261031 .
docker run --rm --network=none --entrypoint python modelmarket-hub:a2a-output-20261031 -c 'import ast; ast.parse(open("/app/aimarket_hub/a2a.py").read()); print("A2A module syntax OK")'
bash scripts/redeploy_in_place.sh modelmarket-hub --image modelmarket-hub:a2a-output-20261031
docker exec modelmarket-hub sha256sum /app/aimarket_hub/a2a.py
