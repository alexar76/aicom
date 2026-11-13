#!/usr/bin/env bash
set -euo pipefail
umask 077
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

base_image=aicom-security:argus-outlook-vendors-v4-20261113
base_sha=sha256:6a4da6b760a693b12b4fb1794980c3ad1d792f2b5a23251784c7590c2d68b1a2
candidate=aicom-security:argus-itch-providers-20261113
provider_candidate=aicom-security:argus-provider-mail-20261113
root=/root/argus
roster="$root/docker-compose.roster.yml"
backup="$roster.pre-itch-providers-20261113"
compose=(docker compose --project-directory "$root" -f "$root/docker-compose.yml" -f "$roster")

case "${1:?prepare or switch required}" in
  prepare)
    sha256sum --check --quiet manifest.sha256
    live="$(docker inspect -f '{{.Image}}' argus)"
    if [[ "$live" != "$base_sha" ]]; then
      test "$live" = "$(docker image inspect -f '{{.Id}}' "$provider_candidate")"
    fi
    test "$(docker image inspect -f '{{.Id}}' "$base_image")" = "$base_sha"
    docker build --network none --build-arg "BASE=$base_image" --tag "$candidate" .
    docker run --rm -i --network none --read-only --tmpfs /tmp:rw,nosuid,nodev,size=8m --cap-drop ALL \
      --security-opt no-new-privileges --entrypoint node "$candidate" --input-type=module - < smoke.mjs
    docker image inspect -f '{{.Id}}' "$candidate" > candidate.id
    ;;
  switch-providers)
    test "$(docker inspect -f '{{.Image}}' argus)" = "$base_sha"
    test "$(docker image inspect -f '{{.Id}}' "$candidate")" = "$(cat candidate.id)"
    docker tag "$candidate" "$provider_candidate"
    provider_backup="$roster.pre-provider-mail-20261113"
    test ! -e "$provider_backup"
    cp -p "$roster" "$provider_backup"
    trap 'cp -p "$provider_backup" "$roster"; "${compose[@]}" up -d --no-deps --no-build argus' ERR
    python3 - "$roster" "$base_image" "$provider_candidate" <<'PY'
from pathlib import Path
import os
import re
import sys

roster = Path(sys.argv[1])
value, count = re.subn(r"(?m)^(    image: )" + re.escape(sys.argv[2]) + r"(?=[ \n])", lambda match: match[1] + sys.argv[3], roster.read_text())
assert count == 1
temp = roster.with_suffix(".providers-tmp")
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
    test "$(docker inspect -f '{{.Image}}' argus)" = "$(cat candidate.id)"
    curl -fsS --max-time 3 http://127.0.0.1:8787/health >/dev/null
    trap - ERR
    ;;
  switch)
    from="$base_image"
    live="$(docker inspect -f '{{.Image}}' argus)"
    if [[ "$live" != "$base_sha" ]]; then
      from="$provider_candidate"
      test "$live" = "$(docker image inspect -f '{{.Id}}' "$provider_candidate")"
    fi
    test "$(docker image inspect -f '{{.Id}}' "$candidate")" = "$(cat candidate.id)"
    test "$(docker inspect -f '{{.State.Running}}' argus-checkout-browser)" = true
    docker network inspect argus_checkout >/dev/null
    docker exec argus node -e 'const f=require("node:fs"); for (const p of ["itch-receipt-email","itch-laso-session","itch-laso-card-id"]) { const path="/home/node/.argus/"+p; const s=f.lstatSync(path); if (!s.isFile()||s.uid!==1000||s.gid!==1000||(s.mode&0o077)||!s.size) process.exit(1); }'
    test "$(stat -c '%u:%g:%a' /root/argus-checkout-browser/private/browser-ws)" = '1000:1000:600'
    "${compose[@]}" config --format json > compose.before.private
    if [[ -e "$backup" ]]; then cmp -s "$roster" "$backup"; else cp -p "$roster" "$backup"; fi
    trap 'cp -p "$backup" "$roster"; "${compose[@]}" up -d --no-deps --no-build argus; rm -f compose.before.private compose.after.private' ERR
    python3 - "$roster" "$from" "$candidate" <<'PY'
from pathlib import Path
import os
import re
import sys

roster = Path(sys.argv[1])
value = roster.read_text()
value, count = re.subn(r"(?m)^(    image: )" + re.escape(sys.argv[2]) + r"(?=[ \n])", lambda match: match[1] + sys.argv[3], value)
assert count == 1
assert value.count("\n    environment:\n") == 1 and "\nnetworks:" not in value
override = """
    networks:
      default: {}
      argus_checkout: {}
    volumes:
      - type: bind
        source: /root/argus-checkout-browser/private/browser-ws
        target: /run/checkout/browser-ws
        read_only: true
        bind:
          create_host_path: false
    environment:
      ARGUS_ITCH_PURCHASE_ENABLED: "1"
      ARGUS_ITCH_BROWSER_WS_FILE: /run/checkout/browser-ws
      ARGUS_ITCH_LASO_SESSION_FILE: /home/node/.argus/itch-laso-session
      ARGUS_ITCH_LASO_CARD_ID_FILE: /home/node/.argus/itch-laso-card-id
      ARGUS_ITCH_RECEIPT_EMAIL_FILE: /home/node/.argus/itch-receipt-email
      ALIEN_PROVIDER_EVENTS_URL: https://monitor.modelmarket.dev
"""
value = value.replace("\n    environment:\n", override)
value += "\nnetworks:\n  argus_checkout:\n    name: argus_checkout\n    external: true\n"
temp = roster.with_suffix(".checkout-tmp")
temp.write_text(value)
temp.chmod(roster.stat().st_mode & 0o777)
os.replace(temp, roster)
PY
    "${compose[@]}" config --format json > compose.after.private
    python3 - <<'PY'
import json
with open("compose.before.private") as f:
    before = json.load(f)
with open("compose.after.private") as f:
    after = json.load(f)
old = before["services"]
new = after["services"]
assert old.keys() == new.keys() and old["argus-uni"] == new["argus-uni"]
old, new = old["argus"], new["argus"]
assert set(old.keys()) == set(new.keys())
assert all(old[k] == new[k] for k in old.keys() - {"image", "environment", "networks", "volumes"})
assert {k: v for k, v in new["environment"].items() if not k.startswith("ARGUS_ITCH_") and k != "ALIEN_PROVIDER_EVENTS_URL"} == old["environment"]
assert set(new["networks"]) - set(old["networks"]) == {"argus_checkout"}
assert all((new["networks"][key] or {}) == (value or {}) for key, value in old["networks"].items())
assert [row for row in new["volumes"] if row["target"] != "/run/checkout/browser-ws"] == old["volumes"]
assert any(row["target"] == "/run/checkout/browser-ws" and row["read_only"] for row in new["volumes"])
print("Compose service delta verified without printing private values")
PY
    rm -f compose.before.private compose.after.private
    "${compose[@]}" up -d --no-deps --no-build argus
    for _ in {1..23}; do
      [[ "$(docker inspect -f '{{.State.Health.Status}}' argus)" == healthy ]] && break
      sleep 2
    done
    test "$(docker inspect -f '{{.State.Health.Status}}' argus)" = healthy
    test "$(docker inspect -f '{{.Image}}' argus)" = "$(cat candidate.id)"
    curl -fsS --max-time 3 http://127.0.0.1:8787/health >/dev/null
    docker exec argus node --input-type=module -e '
        import { loadConfig } from "./dist/config.js";
        import { configuredItchPurchase } from "./dist/checkout/itch-purchase.js";
        import { isCheckoutBrowserEndpoint } from "./dist/checkout/itch-browser.js";
        import { readFileSync } from "node:fs";
        const {config} = loadConfig();
        const ws = readFileSync(process.env.ARGUS_ITCH_BROWSER_WS_FILE,"utf8").trim();
        if (config.mode !== "live" || !isCheckoutBrowserEndpoint(ws)
          || typeof configuredItchPurchase(config.stateDir, config.mode) !== "function"
          || !process.env.ARGUS_TELEGRAM_OWNER_ID?.trim() && !config.telegram.ownerId) process.exit(1);
        console.log("ARGUS live checkout and private Telegram owner configuration verified");
      '
    trap - ERR
    ;;
  *)
    exit 2
    ;;
esac
