#!/usr/bin/env bash
# Reset UNI Anvil state, rebuild Alien Monitor (fresh contracts/evm), bootstrap, wire Hub.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE="$ROOT/alien-monitor/docker-compose.prod.yml"
UNIVERSE_DIR="$ROOT/data/alien-monitor/universe"
ENV_FILE="$ROOT/.env"

echo "=== UNI contract redeploy ==="

if [[ ! -d "$UNIVERSE_DIR" ]]; then
  mkdir -p "$UNIVERSE_DIR/anvil-state"
fi

echo "1/6 Stop alien-monitor (Anvil inside container)…"
docker compose -f "$COMPOSE" stop alien-monitor 2>/dev/null || true
sleep 2

echo "2/6 Reset persisted chain state (live UNI only, not code-backup)…"
rm -f "$UNIVERSE_DIR/universe_config.json"
if [[ -d "$UNIVERSE_DIR/anvil-state" ]]; then
  find "$UNIVERSE_DIR/anvil-state" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
fi

echo "2b/6 Prebuild Solana lottery .so (host cargo-build-sbf)…"
if command -v cargo-build-sbf >/dev/null 2>&1; then
  (cd "$ROOT/contracts/solana" && CARGO_TARGET_DIR="$ROOT/contracts/solana/target" \
    cargo-build-sbf --manifest-path programs/aimarket-lottery/Cargo.toml) || echo "WARN: Solana lottery build skipped"
fi

echo "3/6 Rebuild alien-monitor image (contracts/evm from monorepo)…"
docker compose -f "$COMPOSE" build alien-monitor

echo "4/6 Start alien-monitor + wait for bootstrap…"
docker compose -f "$COMPOSE" up -d alien-monitor

READY=0
for i in $(seq 1 90); do
  if HEALTH="$(curl -sf "http://127.0.0.1:9100/api/health" 2>/dev/null || true)"; then
    OK="$(echo "$HEALTH" | python3 -c "import sys,json; d=json.load(sys.stdin); c=d.get('contracts',{}); print(c.get('evm_escrow') and c.get('evm_lottery'))" 2>/dev/null || true)"
    if [[ -n "$OK" && "$OK" != "False" && "$OK" != "0" ]]; then
      echo "$HEALTH" | python3 -m json.tool
      READY=1
      break
    fi
  fi
  sleep 2
done

if [[ "$READY" != "1" ]]; then
  echo "ERROR: bootstrap did not finish in time" >&2
  docker compose -f "$COMPOSE" logs --tail=80 alien-monitor
  exit 1
fi

SNIPPET="$UNIVERSE_DIR/hub.env.snippet"
if [[ ! -f "$SNIPPET" ]]; then
  echo "WARNING: $SNIPPET missing — skip .env merge"
else
  echo "5/6 Merge hub.env.snippet → .env"
  python3 - "$ENV_FILE" "$SNIPPET" <<'PY'
import re
import sys
from pathlib import Path

env_path = Path(sys.argv[1])
snippet_path = Path(sys.argv[2])
updates: dict[str, str] = {}
for line in snippet_path.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    if "=" in line:
        k, v = line.split("=", 1)
        updates[k.strip()] = v.strip()

text = env_path.read_text(encoding="utf-8") if env_path.is_file() else ""
for key, val in updates.items():
    pat = re.compile(rf"^{re.escape(key)}=.*$", re.MULTILINE)
    repl = f"{key}={val}"
    if pat.search(text):
        text = pat.sub(repl, text)
    else:
        text = text.rstrip() + "\n" + repl + "\n"
env_path.write_text(text, encoding="utf-8")
print("Updated keys:", ", ".join(sorted(updates)))
PY
fi

if docker ps --format '{{.Names}}' | grep -qx 'modelmarket-hub'; then
  echo "6/6 Recreate modelmarket-hub with updated .env (lottery binding)…"
  bash "$ROOT/scripts/deploy_hub.sh"
else
  echo "6/6 modelmarket-hub not running — run deploy_hub.sh after merging .env"
fi

echo ""
echo "=== Disk cleanup ==="
bash "$ROOT/scripts/disk_cleanup.sh"

echo ""
echo "Done. UNI contracts redeployed."
echo "  universe_config: $UNIVERSE_DIR/universe_config.json"
echo "  hub snippet:       $SNIPPET"
