#!/usr/bin/env bash
# Switch the live ARGUS (attested) to ARGUS 0.6.1 on WARDEN 0.33.0; roll back to the previous roster on any error.
# The image is the running 0.6.0 release image with WARDEN replaced by the npm 0.33.0 package (sha256 31de2475…),
# /app/dist built from aicom 7ee40693a (the version constant and the ecosystem knowledge list differ) and that
# commit's package files. Config, state and the checkout browser sockets stay mounted. Owner 2026-11-20: move ARGUS
# to WARDEN 0.33.
set -euo pipefail
umask 077
root=/root/argus
roster="$root/docker-compose.roster.yml"
base=aicom-security:argus-0.6.0-20261118
image=aicom-security:argus-0.6.1-20261120
backup="$roster.before-${image#*:}"
compose=(docker compose --project-directory "$root" -f "$root/docker-compose.yml" -f "$roster")

test "$(docker inspect -f '{{.Image}}' argus)" = "$(docker image inspect -f '{{.Id}}' "$base")"
docker image inspect "$image" >/dev/null
# Never restart in the middle of a purchase: Hudson Link and itch.io journals must be absent or finished.
docker exec -i -w /app argus node --input-type=module - <<'NODE'
import { join } from "node:path";
import { loadConfig } from "./dist/config.js";
import { readPrivateCheckoutFile } from "./dist/checkout/itch-purchase.js";
const dir = loadConfig().config.stateDir;
const finished = { "hudson-link-purchase.json": ["delivered"], "itch-icon-purchase.json": ["delivered", "manual_delivered"] };
for (const [file, done] of Object.entries(finished)) {
  try {
    const row = JSON.parse(readPrivateCheckoutFile(join(dir, file), 4096));
    if (row.v !== 1 || !done.includes(row.stage)) throw new Error(`${file}: purchase in progress (${row.stage}); not switching.`);
  } catch (error) { if (error.code !== "ENOENT") throw error; }
}
NODE

test ! -e "$backup"
cp -p -- "$roster" "$backup"
rollback() {
  echo "switch failed; restoring $backup" >&2
  cp -p -- "$backup" "$roster"
  "${compose[@]}" up -d --no-deps --no-build argus
}
trap rollback ERR
python3 - "$roster" "$base" "$image" <<'PY'
import os, re, sys
from pathlib import Path
roster, base, image = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
text = roster.read_text()
new, count = re.subn(r"(?m)^(    image: )" + re.escape(base) + r"(?=[ \n])", lambda m: m[1] + image, text)
assert count == 1, "Unexpected ARGUS image configuration"
new = re.sub(r"(?m)^(    image: " + re.escape(image) + r")  # .*$",
             r"\1  # 2026-11-20 ARGUS 0.6.1 (main 7ee40693a; 0.6.0 image + WARDEN 0.33.0 from npm + dist)", new, count=1)
tmp = roster.with_suffix(".argus061-tmp")
tmp.write_text(new)
tmp.chmod(roster.stat().st_mode & 0o777)
os.replace(tmp, roster)
PY
"${compose[@]}" up -d --no-deps --no-build argus
for _ in $(seq 1 36); do
  state="$(docker inspect -f '{{.State.Health.Status}}' argus 2>/dev/null || true)"
  [ "$state" = healthy ] && break
  [ "$state" = unhealthy ] && false
  sleep 5
done
test "$(docker inspect -f '{{.State.Health.Status}}' argus)" = healthy
test "$(docker inspect -f '{{.Image}}' argus)" = "$(docker image inspect -f '{{.Id}}' "$image")"
test "$(docker exec argus node -p 'require("/app/package.json").version')" = 0.6.1
test "$(docker exec argus node -p 'require("/app/node_modules/@aimarket/warden/package.json").version')" = 0.33.0
test "$(docker exec argus node -p 'require("/app/node_modules/playwright-core/package.json").version')" = 1.64.1
trap - ERR
echo "switched: $image (rollback: cp -p $backup $roster && docker compose --project-directory $root -f $root/docker-compose.yml -f $roster up -d --no-deps --no-build argus)"
