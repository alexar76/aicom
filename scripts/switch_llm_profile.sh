#!/usr/bin/env bash
# Fleet LLM profile switch — 4 hosts, all AI assistants.
#
# Profiles:
#   deepseek-all    — DeepSeek API everywhere (restore after outage)
#   hybrid-metis    — DeepSeek fleet + Metis MiniMax on OpenRouter (canonical prod)
#   openrouter-all  — Emergency: OpenRouter MiniMax everywhere + Kimi-K3 in Metis
#
# Usage:
#   ./scripts/switch_llm_profile.sh hybrid-metis
#   ./scripts/switch_llm_profile.sh deepseek-all
#   ./scripts/switch_llm_profile.sh openrouter-all --from-metis-env
#   ./scripts/switch_llm_profile.sh scan
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

SSH_KEY="${FACTORY_SSH_KEY:-$HOME/.ssh/id_ed25519_factory}"
SSH=(ssh -i "$SSH_KEY" -o BatchMode=yes)
SCP=(scp -i "$SSH_KEY" -o BatchMode=yes)

FACTORY="${FACTORY_SSH:-my-vps}"
METIS="${METIS_SSH:-root@skopos.modelmarket.dev}"
ORACLES="${ORACLES_SSH:-admin-vps}"
HUB_LAB="${HUB_LAB_SSH:-competing-lab}"

FROM_METIS_ENV=0
NO_RESTART=0
HOSTS=all

usage() {
  sed -n '2,16p' "$0"
  echo "  scan"
  echo "  deepseek-all | hybrid-metis | openrouter-all"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    scan|deepseek-all|hybrid-metis|openrouter-all) PROFILE="$1"; shift ;;
    --from-metis-env) FROM_METIS_ENV=1; shift ;;
    --no-restart) NO_RESTART=1; shift ;;
    --factory-only) HOSTS=factory; shift ;;
    --metis-only) HOSTS=metis; shift ;;
    --oracles-only) HOSTS=oracles; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown: $1" >&2; usage; exit 2 ;;
  esac
done

PROFILE="${PROFILE:-}"
[[ -n "$PROFILE" ]] || { usage; exit 2; }

if [[ "$PROFILE" == scan ]]; then
  python3 scripts/llm_routing.py scan
  exit 0
fi

resolve_openrouter_key() {
  if [[ -n "${OPENROUTER_API_KEY:-}" ]]; then printf '%s' "$OPENROUTER_API_KEY"; return; fi
  if [[ "$FROM_METIS_ENV" -eq 1 ]]; then
    ssh -o BatchMode=yes "$METIS" "grep -E '^OPENROUTER_API_KEY=' /opt/metis/.env | head -1 | cut -d= -f2-"
    return
  fi
  return 1
}

resolve_deepseek_key() {
  if [[ -n "${DEEPSEEK_API_KEY:-}" ]]; then printf '%s' "$DEEPSEEK_API_KEY"; return; fi
  ssh -o BatchMode=yes "$FACTORY" "grep -E '^DEEPSEEK_API_KEY=' /root/claudecode/aicom/.env | head -1 | cut -d= -f2-" 2>/dev/null || true
}

patch_env_remote() {
  local ssh_host="$1" env_file="$2" profile="$3" or_key="$4"
  "${SSH[@]}" "$ssh_host" "bash -s" "$env_file" "$profile" "$or_key" <<'REMOTE'
set -euo pipefail
ENV_FILE="$1"
PROFILE="$2"
OR_KEY="$3"
MARKER="# --- llm_profile_switch (auto) ---"
python3 - "$ENV_FILE" "$PROFILE" "$OR_KEY" "$MARKER" <<'PY'
import sys
from pathlib import Path

env_path = Path(sys.argv[1])
profile = sys.argv[2]
or_key = sys.argv[3]
marker = sys.argv[4]

DEEPSEEK = {
    "ATLAS_LLM_PROVIDER": "deepseek_api",
    "ATLAS_LLM_BASE_URL": "https://api.deepseek.com/v1",
    "ATLAS_LLM_MODEL": "deepseek-v4-pro",
    "ATLAS_LLM_MODEL_LIGHT": "deepseek-v4-flash",
    "MOMUS_LLM_PROVIDER": "deepseek",
    "MOMUS_LLM_MODEL": "deepseek-v4-pro",
    "HELIOS_LLM_PROVIDER": "deepseek",
    "HELIOS_LLM_MODEL": "deepseek-v4-pro",
    "DIOSCURI_LLM_PROVIDER": "deepseek",
    "DIOSCURI_LLM_MODEL": "deepseek-v4-pro",
    "TREASURY_LLM_PROVIDER": "deepseek",
}
OPENROUTER = {
    "ATLAS_LLM_PROVIDER": "openrouter_api",
    "ATLAS_LLM_BASE_URL": "https://openrouter.ai/api/v1",
    "ATLAS_LLM_MODEL": "minimax/minimax-m3",
    "ATLAS_LLM_MODEL_LIGHT": "minimax/minimax-m3",
    "MOMUS_LLM_PROVIDER": "openai",
    "MOMUS_LLM_BASE_URL": "https://openrouter.ai/api/v1",
    "MOMUS_LLM_MODEL": "minimax/minimax-m3",
    "MOMUS_LLM_API_KEY": or_key,
    "HELIOS_LLM_PROVIDER": "openai-compatible",
    "HELIOS_LLM_BASE_URL": "https://openrouter.ai/api/v1",
    "HELIOS_LLM_MODEL": "minimax/minimax-m3",
    "DIOSCURI_LLM_PROVIDER": "openai-compatible",
    "DIOSCURI_LLM_BASE_URL": "https://openrouter.ai/api/v1",
    "DIOSCURI_LLM_MODEL": "minimax/minimax-m3",
    "TREASURY_LLM_PROVIDER": "openai",
    "OPENROUTER_API_KEY": or_key,
}
updates = DEEPSEEK if profile in ("deepseek-all", "hybrid-metis") else OPENROUTER
if profile == "hybrid-metis" and or_key:
    updates = {**updates, "OPENROUTER_API_KEY": or_key}

lines = []
if env_path.is_file():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.strip() == marker:
            break
        k = line.split("=", 1)[0].strip() if "=" in line and not line.strip().startswith("#") else ""
        if k in updates:
            continue
        lines.append(line)
lines.append(marker)
for k, v in updates.items():
    lines.append(f"{k}={v}")
env_path.parent.mkdir(parents=True, exist_ok=True)
env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY
REMOTE
}

apply_metis() {
  echo "== Metis ($METIS) profile=$PROFILE =="
  "${SCP[@]}" scripts/llm_routing.py "${METIS}:/tmp/llm_routing.py"
  local MODE=hybrid
  case "$PROFILE" in
    deepseek-all) MODE=deepseek_all ;;
    hybrid-metis) MODE=hybrid ;;
    openrouter-all) MODE=openrouter_all ;;
  esac
  "${SSH[@]}" "$METIS" "python3 /tmp/llm_routing.py" 2>/dev/null || true
  "${SSH[@]}" "$METIS" "METIS_MODE=$MODE python3 - <<'PY'
import os, yaml
from pathlib import Path
import importlib.util
spec = importlib.util.spec_from_file_location('lr', '/tmp/llm_routing.py')
lr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lr)
mode = os.environ['METIS_MODE']
prod = Path('/opt/metis/deploy/prod.yaml')
data = yaml.safe_load(prod.read_text(encoding='utf-8')) or {}
bak = prod.with_suffix(prod.suffix + '.bak-profile')
bak.write_bytes(prod.read_bytes())
patched = lr.METIS_PATCHERS[mode](data)
tmp = Path('/tmp/metis-profile.yaml')
tmp.write_text(yaml.safe_dump(patched, sort_keys=False, allow_unicode=True))
tmp.replace(prod)
print('base_model', patched.get('base_model'))
ipb = patched.get('modules', {}).get('intent_parser_b', {})
print('intent_parser_b', ipb.get('model'), ipb.get('api_key_env'))
PY"
  if [[ $NO_RESTART -eq 0 ]]; then
    "${SSH[@]}" "$METIS" "docker restart metis metis-skopos 2>/dev/null || docker restart metis"
  fi
}

apply_factory() {
  echo "== Factory ($FACTORY) profile=$PROFILE =="
  OR_KEY="$(resolve_openrouter_key 2>/dev/null || true)"
  DS_KEY="$(resolve_deepseek_key 2>/dev/null || true)"
  patch_env_remote "$FACTORY" "/root/claudecode/aicom/.env" "$PROFILE" "${OR_KEY:-}"
  "${SCP[@]}" llm/persist_openrouter.py llm/persist_deepseek.py llm/startup_provider_sync.py \
    "${FACTORY}:/root/claudecode/aicom/llm/"
  "${SCP[@]}" entrypoint.sh pipeline_worker.py \
    "${FACTORY}:/root/claudecode/aicom/"
  "${SCP[@]}" web/backend/main.py \
    "${FACTORY}:/root/claudecode/aicom/web/backend/main.py"
  if [[ "$PROFILE" == openrouter-all && -n "$OR_KEY" ]]; then
    printf '%s' "$OR_KEY" | "${SSH[@]}" "$FACTORY" 'cat > /root/claudecode/aicom/data/secrets/llm/openrouter_api_key; chown 10001:10001 /root/claudecode/aicom/data/secrets/llm/openrouter_api_key; chmod 600 /root/claudecode/aicom/data/secrets/llm/openrouter_api_key'
    "${SSH[@]}" "$FACTORY" "docker cp /root/claudecode/aicom/llm/persist_openrouter.py aicom-app-1:/app/llm/persist_openrouter.py && docker cp /root/claudecode/aicom/llm/startup_provider_sync.py aicom-app-1:/app/llm/startup_provider_sync.py && docker cp /root/claudecode/aicom/entrypoint.sh aicom-app-1:/app/entrypoint.sh 2>/dev/null || true && docker cp /root/claudecode/aicom/pipeline_worker.py aicom-app-1:/app/pipeline_worker.py 2>/dev/null || true && docker cp /root/claudecode/aicom/web/backend/main.py aicom-app-1:/app/web/backend/main.py 2>/dev/null || true && docker exec aicom-app-1 python3 -c \"
import sys; from pathlib import Path; sys.path.insert(0,'/app')
from core.config_overlay import patch_primary_overlay
from llm.persist_openrouter import sync_openrouter_provider_config
k=Path('/app/data/secrets/llm/openrouter_api_key').read_text().strip()
patch_primary_overlay({'general.factory_on_hold': True})
print(sync_openrouter_provider_config(api_key=k))
\""
  else
    "${SSH[@]}" "$FACTORY" "docker cp /root/claudecode/aicom/llm/persist_deepseek.py aicom-app-1:/app/llm/persist_deepseek.py && docker exec aicom-app-1 python3 -c \"
import sys; sys.path.insert(0,'/app')
from core.config_overlay import patch_primary_overlay
from llm.persist_deepseek import sync_deepseek_provider_config
patch_primary_overlay({'general.factory_on_hold': False})
print(sync_deepseek_provider_config())
\""
  fi
  if [[ $NO_RESTART -eq 0 ]]; then
    "${SSH[@]}" "$FACTORY" "docker restart aicom-app-1 alien-monitor; (cd /root/claudecode/aicom/atlas && docker compose --env-file ../.env up -d --force-recreate)"
  fi
}

apply_oracles() {
  echo "== Oracles ($ORACLES) profile=$PROFILE =="
  OR_KEY="$(resolve_openrouter_key 2>/dev/null || true)"
  for envf in /root/momus-deploy/.env /root/helios/.env /root/dioscuri/.env /root/aicom/.env; do
    patch_env_remote "$ORACLES" "$envf" "$PROFILE" "${OR_KEY:-}"
  done
  if [[ $NO_RESTART -eq 0 ]]; then
    "${SSH[@]}" "$ORACLES" "cd /root/momus-deploy && docker compose -f docker-compose.prod.yml up -d --force-recreate momus-backend momus-treasury 2>/dev/null || docker restart momus-backend momus-treasury"
    "${SSH[@]}" "$ORACLES" "cd /root/helios && docker compose up -d --force-recreate 2>/dev/null || docker restart helios helios-worker"
    "${SSH[@]}" "$ORACLES" "cd /root/dioscuri && docker compose up -d --force-recreate 2>/dev/null || docker restart dioscuri"
    "${SSH[@]}" "$ORACLES" "docker restart argus alien-monitor platon-platon-backend logos 2>/dev/null || true"
  fi
}

apply_hub_lab() {
  echo "== Hub lab ($HUB_LAB) — no direct LLM routers; hub uses remote Metis verify =="
}

case "$HOSTS" in
  all)
    apply_metis
    apply_factory
    apply_oracles
    apply_hub_lab
    ;;
  factory) apply_factory ;;
  metis) apply_metis ;;
  oracles) apply_oracles ;;
  hub_lab) apply_hub_lab ;;
esac

echo "Done — profile=$PROFILE. Docs: docs/llm-routing-profiles.md"
