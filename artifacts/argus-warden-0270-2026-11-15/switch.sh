#!/usr/bin/env bash
# Switch the live ARGUS (attested) to the WARDEN 0.27.0 overlay; roll back to the previous roster on any error.
set -euo pipefail
umask 077
root=/root/argus
roster="$root/docker-compose.roster.yml"
base=aicom-security:argus-hudson-auto-receipt-20261114
image=aicom-security:argus-warden-0270-20261115
backup="$roster.before-${image#*:}"
compose=(docker compose --project-directory "$root" -f "$root/docker-compose.yml" -f "$roster")

test "$(docker inspect -f '{{.Image}}' argus)" = "$(docker image inspect -f '{{.Id}}' "$base")"
docker image inspect "$image" >/dev/null
# Never restart in the middle of a purchase.
docker exec -i -w /app argus node --input-type=module - <<'NODE'
import { join } from "node:path";
import { loadConfig } from "./dist/config.js";
import { readPrivateCheckoutFile } from "./dist/checkout/itch-purchase.js";
try {
  const row = JSON.parse(readPrivateCheckoutFile(join(loadConfig().config.stateDir, "hudson-link-purchase.json"), 4096));
  if (row.v !== 1 || row.stage !== "delivered") throw new Error("Hudson Link purchase in progress; not switching.");
} catch (error) { if (error.code !== "ENOENT") throw error; }
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
tmp = roster.with_suffix(".warden-tmp")
tmp.write_text(new.replace("# 2026-11-13 Outlook.com OAuth and Microsoft Graph", "# 2026-11-15 WARDEN 0.27.0 overlay on argus-hudson-auto-receipt-20261114", 1))
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
test "$(docker exec argus node -p 'require("/app/node_modules/@aimarket/warden/package.json").version')" = 0.27.0
trap - ERR
echo "switched: $image (rollback: cp -p $backup $roster && docker compose --project-directory $root -f $root/docker-compose.yml -f $roster up -d --no-deps --no-build argus)"
