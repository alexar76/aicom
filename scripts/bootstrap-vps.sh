#!/usr/bin/env bash
# VPS bootstrap — deps, .env template, satellite clone hint.
#
# Usage:
#   ./scripts/bootstrap-vps.sh
#   ./scripts/bootstrap-vps.sh --write-env
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WRITE_ENV=0
[[ "${1:-}" == "--write-env" ]] && WRITE_ENV=1

echo "=== AI-Factory VPS bootstrap ==="

if [[ "$WRITE_ENV" -eq 0 && ! -f "$ROOT/.env" ]]; then
  if [[ -f "$ROOT/.env.vps.example" ]]; then
    cp "$ROOT/.env.vps.example" "$ROOT/.env"
    chmod 600 "$ROOT/.env"
    echo "Created .env from .env.vps.example — fill secrets before deploy"
  else
    "$ROOT/scripts/generate_trimmed_env_example.sh" --write
    cp "$ROOT/.env.vps.example" "$ROOT/.env"
    chmod 600 "$ROOT/.env"
    echo "Generated .env.vps.example and copied to .env"
  fi
fi

# Host tools are optional — SDK tests run inside Hub/ARGUS containers on minimal VPS images.
if command -v apt-get >/dev/null 2>&1; then
  MISSING=()
  command -v python3 >/dev/null || MISSING+=(python3)
  command -v docker >/dev/null || MISSING+=(docker.io)
  command -v curl >/dev/null || MISSING+=(curl)
  if [[ ${#MISSING[@]} -gt 0 ]]; then
    echo "Installing host packages: ${MISSING[*]}"
    sudo apt-get update -qq
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
      python3 python3-venv curl docker.io docker-compose-plugin nginx git openssl \
      || sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3 curl docker.io git openssl
  fi
  if ! command -v pip3 >/dev/null 2>&1 && ! python3 -m pip --version >/dev/null 2>&1; then
    echo "NOTE: python3-pip not installed — OK if you test SDKs inside Docker (Hub, ARGUS)."
    echo "      pip install -e plugins/… only works on host after: apt install python3-pip python3-venv"
  fi
  if ! command -v node >/dev/null 2>&1; then
    echo "NOTE: nodejs not on host — test @aimarket/agent inside a Node container or after apt install nodejs npm."
  fi
else
  echo "Non-apt host — ensure docker, curl, python3, git are available."
fi

if [[ -x "$ROOT/scripts/ensure_deploy_satellites.sh" ]]; then
  echo "--- Satellite dirs (acex, aimarket-hub, plugins) ---"
  "$ROOT/scripts/ensure_deploy_satellites.sh"
fi

echo ""
echo "Next:"
echo "  1. Edit .env (ALIEN_API_TOKEN, AIMARKET_ADMIN_TOKEN, MESH_* tokens, ARGUS_WALLET_KEY for economy)"
echo "  2. ./scripts/deploy_ecosystem.sh --public-url https://your-domain"
echo "  3. sudo ./scripts/install_nginx_proxy.sh"
echo "  4. ./scripts/verify_ecosystem_full.sh"
echo "  5. ./scripts/sdk_e2e_hello.sh   # optional Hub SDK smoke"
