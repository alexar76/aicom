#!/usr/bin/env bash
set -euo pipefail
umask 077

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
base=argus-checkout-browser:playwright-1.64.1
image=argus-checkout-browser:hudson-headed-20261114
name=argus-hudson-browser
private="$(pwd)/private/browser-ws"

test "$(docker inspect -f '{{.Config.Image}}' argus-checkout-browser)" = "$base"
docker inspect argus-checkout-browser | python3 -c '
import json, sys
container = json.load(sys.stdin)[0]
security = container["HostConfig"]["SecurityOpt"]
profile, = (entry.split("=", 1)[1] for entry in security if entry.startswith("seccomp="))
json.dump(json.loads(profile), sys.stdout)
' > seccomp.json

install -d -m 0700 private
if [[ ! -f "$private" ]]; then
  printf 'ws://argus-hudson-browser:47871/%s\n' "$(openssl rand -hex 32)" > "$private"
  chown 1000:1000 "$private"
fi
test ! -L "$private"
test "$(stat -c '%u:%g:%a' "$private")" = '1000:1000:600'

docker build --network none --tag "$image" -f Browser.Dockerfile .
if ! docker container inspect "$name" >/dev/null 2>&1; then
  docker run -d --name "$name" --network argus_checkout --init --restart unless-stopped \
    --user 1000:1000 --cap-drop ALL --read-only --pids-limit 256 --memory 1536m --memory-swap 1536m --shm-size 128m \
    --tmpfs /tmp:rw,nosuid,nodev,size=128m,mode=1777 --security-opt no-new-privileges:true \
    --security-opt apparmor=argus-checkout-browser --security-opt "seccomp=$(pwd)/seccomp.json" \
    --mount "type=bind,src=$private,dst=/run/checkout/browser-ws,readonly" \
    --env ARGUS_CHECKOUT_HEADED=1 "$image" >/dev/null
fi
test "$(docker inspect -f '{{.Image}}' "$name")" = "$(docker image inspect -f '{{.Id}}' "$image")"
for _ in {1..15}; do
  if docker logs "$name" 2>&1 | grep -q 'Checkout browser listening'; then
    docker exec -e CHECKOUT_SMOKE_HOST=127.0.0.1 "$name" node /app/smoke.mjs
    exit 0
  fi
  [[ $(docker inspect -f '{{.State.Running}}' "$name") == true ]] || break
  sleep 1
done
exit 1
