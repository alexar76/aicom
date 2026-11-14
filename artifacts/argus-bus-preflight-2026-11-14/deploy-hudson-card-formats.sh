#!/usr/bin/env bash
set -euo pipefail
umask 077

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
root=/root/argus
roster="$root/docker-compose.roster.yml"
base=${HUDSON_CHECKOUT_BASE_IMAGE:-aicom-security:argus-hudson-20261114}
image=${HUDSON_CHECKOUT_TARGET_IMAGE:-aicom-security:argus-hudson-card-formats-20261114}
[[ "$base" =~ ^aicom-security:argus-hudson-[a-z0-9-]+$ ]]
[[ "$image" =~ ^aicom-security:argus-hudson-[a-z0-9-]+$ && "$base" != "$image" ]]
backup="$roster.before-${image#*:}"
compose=(docker compose --project-directory "$root" -f "$root/docker-compose.yml" -f "$roster")

test "$(docker inspect -f '{{.Image}}' argus)" = "$(docker image inspect -f '{{.Id}}' "$base")"
test "$(docker inspect -f '{{.State.Running}}' argus-hudson-browser)" = true
sha256sum --check --quiet overlay.sha256
docker build --network none -f - -t "$image" --build-arg "ARGUS_BASE_IMAGE=$base" . <<'DOCKERFILE'
ARG ARGUS_BASE_IMAGE=aicom-security:argus-hudson-20261114
FROM ${ARGUS_BASE_IMAGE}
COPY overlay/ /app/dist/
DOCKERFILE
docker run --rm --network none --read-only --cap-drop ALL --entrypoint node "$image" --input-type=module -e '
  const { openHudsonCheckout } = await import("./dist/checkout/hudson-browser.js");
  const { configuredHudsonPurchase } = await import("./dist/checkout/hudson-purchase.js");
  const { LasoCheckoutAuthError } = await import("./dist/checkout/laso-card.js");
  if (!openHudsonCheckout || !configuredHudsonPurchase || !LasoCheckoutAuthError) process.exit(1);
'

docker exec -i -w /app argus node --input-type=module - <<'NODE'
import { existsSync } from "node:fs";
import { join } from "node:path";
import { loadConfig } from "./dist/config.js";
if (existsSync(join(loadConfig().config.stateDir, "hudson-link-purchase.json"))) {
  throw new Error("Purchase journal is present. Reconcile before replacing a running checkout.");
}
NODE

test ! -e "$backup"
cp -p -- "$roster" "$backup"
rollback() {
  cp -p -- "$backup" "$roster"
  "${compose[@]}" up -d --no-deps --no-build argus
}
trap rollback ERR
python3 - "$roster" "$base" "$image" <<'PY'
import os
import re
import sys
from pathlib import Path

roster = Path(sys.argv[1])
text = roster.read_text()
prefix, service = text.split("\n  argus:\n", 1)
end = re.search(r"(?m)^(?:  [\w-]+:|[^\s])", service)
offset = end.start() if end else len(service)
argus, count = re.subn(
    r"(?m)^(    image: )" + re.escape(sys.argv[2]) + r"(?=[ \n])",
    lambda match: match[1] + sys.argv[3],
    service[:offset],
)
assert count == 1, "Unexpected ARGUS image configuration"
temp = roster.with_suffix(".card-formats-tmp")
temp.write_text(prefix + "\n  argus:\n" + argus + service[offset:])
temp.chmod(roster.stat().st_mode & 0o777)
os.replace(temp, roster)
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
