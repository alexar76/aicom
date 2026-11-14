#!/usr/bin/env bash
set -euo pipefail
umask 077

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
root=/root/argus
roster="$root/docker-compose.roster.yml"
base=aicom-security:argus-outlook-incoming-20261113
image=aicom-security:argus-hudson-20261114
backup="$roster.before-hudson-20261114"
compose=(docker compose --project-directory "$root" -f "$root/docker-compose.yml" -f "$roster")
browser_socket=/root/argus-hudson-20261114/private/browser-ws
checkout_enabled=${ARGUS_HUDSON_ENABLE_CHECKOUT:-1}
[[ "$checkout_enabled" == 0 || "$checkout_enabled" == 1 ]]

test "$(docker inspect -f '{{.Image}}' argus)" = "$(docker image inspect -f '{{.Id}}' "$base")"
test "$(docker inspect -f '{{.State.Running}}' argus-hudson-browser)" = true
test "$(stat -c '%u:%g:%a' "$browser_socket")" = '1000:1000:600'
if [[ -e "$backup" ]]; then cmp -s "$roster" "$backup"; fi
sha256sum --check --quiet argus-manifest.sha256
docker build --network none -t "$image" -f Argus.Dockerfile .

docker run --rm --network none --read-only --cap-drop ALL --entrypoint node "$image" --input-type=module -e '
  const checkout = await import("./dist/checkout/hudson-purchase.js");
  const telegram = await import("./dist/telegram/purchase.js");
  if (typeof checkout.configuredHudsonPurchase !== "function" || !telegram.isHudsonPurchaseCommand("/buy_hudson")) process.exit(1);
'

if [[ ! -e "$backup" ]]; then cp -p "$roster" "$backup"; fi
rollback() {
  cp -p "$backup" "$roster"
  rm -f before.json after.json
  "${compose[@]}" up -d --no-deps --no-build argus
}
trap rollback ERR
"${compose[@]}" config --format json > before.json
python3 - "$roster" "$base" "$image" "$browser_socket" "$checkout_enabled" <<'PY'
from pathlib import Path
import os, re, sys

roster = Path(sys.argv[1])
text = roster.read_text()
start, = re.finditer(r'(?m)^  argus:\n', text)
end = re.search(r'(?m)^(?:  [\w-]+:|[^\s])', text[start.end():])
stop = start.end() + end.start() if end else len(text)
service = text[start.end():stop]
old_image, new_image, socket, checkout_enabled = sys.argv[2:]
service, count = re.subn(r'(?m)^(    image: )' + re.escape(old_image) + r'(?=[ \n])', r'\g<1>' + new_image, service)
assert count == 1 and service.count('\n    volumes:\n') == service.count('\n    environment:\n') == 1, 'Unexpected ARGUS roster structure'
service = service.replace('\n    volumes:\n', '\n    volumes:\n' + f'''      - type: bind
        source: {socket}
        target: /run/checkout/hudson-browser-ws
        read_only: true
        bind:
          create_host_path: false
''')
service = service.replace('\n    environment:\n', '\n    environment:\n' + f'''      ARGUS_HUDSON_PURCHASE_ENABLED: "{checkout_enabled}"
      ARGUS_HUDSON_BROWSER_WS_FILE: /run/checkout/hudson-browser-ws
''')
temp = roster.with_suffix('.hudson-tmp')
temp.write_text(text[:start.end()] + service + text[stop:])
temp.chmod(roster.stat().st_mode & 0o777)
os.replace(temp, roster)
PY
"${compose[@]}" config --format json > after.json
python3 - "$checkout_enabled" <<'PY'
import json
from pathlib import Path
import sys

before, after = [json.loads(Path(name).read_text()) for name in ('before.json', 'after.json')]
Path('before.json').unlink()
Path('after.json').unlink()
old, new = [project['services'].pop('argus') for project in (before, after)]
assert before == after
for key in old:
    if key not in ('image', 'environment', 'volumes'):
        assert old[key] == new[key], f'Unexpected Compose service change: {key}'
assert new['image'] == 'aicom-security:argus-hudson-20261114'
assert new['environment'].pop('ARGUS_HUDSON_PURCHASE_ENABLED') == sys.argv[1]
assert new['environment'].pop('ARGUS_HUDSON_BROWSER_WS_FILE') == '/run/checkout/hudson-browser-ws'
assert old['environment'] == new['environment']
mount, = [v for v in new['volumes'] if v['target'] == '/run/checkout/hudson-browser-ws']
assert mount['read_only'] and mount['type'] == 'bind'
assert old['volumes'] == [v for v in new['volumes'] if v != mount]
PY

"${compose[@]}" up -d --no-deps --no-build argus
for _ in {1..24}; do
  [[ "$(docker inspect -f '{{.State.Health.Status}}' argus)" == healthy ]] && break
  sleep 2
done
test "$(docker inspect -f '{{.State.Health.Status}}' argus)" = healthy
test "$(docker inspect -f '{{.Image}}' argus)" = "$(docker image inspect -f '{{.Id}}' "$image")"
curl -fsS --max-time 3 http://127.0.0.1:8787/health >/dev/null
trap - ERR
docker inspect -f '{{.Config.Image}} {{.State.Health.Status}}' argus
