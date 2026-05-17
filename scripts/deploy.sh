#!/usr/bin/env bash
# =============================================================================
# AI-Factory — compose deploy helper
# =============================================================================
# - Optionally fills missing .env keys (CORS / site URL from --public-url,
#   Fernet key for firewall rules file, sandbox preview network isolation).
# - Builds and starts the stack (default: service ``app``).
#
# Usage:
#   ./scripts/deploy.sh
#   ./scripts/deploy.sh --public-url https://your-host.example.com
#   ./scripts/deploy.sh --no-env-fill --no-build
#   ./scripts/deploy.sh -- --profile dev   # extra args after -- go to docker compose
#
# Env fill never overwrites existing keys; use your editor to change values.
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ENV_FILE="${ENV_FILE:-$ROOT/.env}"
NO_ENV_FILL=0
NO_BUILD=0
PUBLIC_URL=""
COMPOSE_SERVICES=(app)
PASS_THROUGH=()

usage() {
  sed -n '1,25p' "$0" | tail -n +2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --no-env-fill)
      NO_ENV_FILL=1
      shift
      ;;
    --no-build)
      NO_BUILD=1
      shift
      ;;
    --public-url)
      PUBLIC_URL="${2:-}"
      shift 2
      ;;
    --)
      shift
      PASS_THROUGH=("$@")
      break
      ;;
    *)
      echo "unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ ! -f "$ENV_FILE" ]]; then
  echo "error: $ENV_FILE not found. Create it first, e.g.:" >&2
  echo "  cp .env.example .env   # then add API keys" >&2
  exit 2
fi

if [[ "$NO_ENV_FILL" -eq 0 ]]; then
  FILL_ARGS=(--env-file "$ENV_FILE")
  if [[ -n "$PUBLIC_URL" ]]; then
    FILL_ARGS+=(--public-url "$PUBLIC_URL")
  fi
  python3 "$ROOT/scripts/fill_production_env.py" "${FILL_ARGS[@]}"
fi

COMPOSE_FILES=(-f docker-compose.yml)
if [[ -d "$ROOT/data/secrets/llm" ]] && compgen -G "$ROOT/data/secrets/llm/*_api_key" >/dev/null 2>&1; then
  COMPOSE_FILES+=(-f docker-compose.secrets.yml)
fi

if [[ "$NO_BUILD" -eq 0 ]]; then
  docker compose "${PASS_THROUGH[@]}" "${COMPOSE_FILES[@]}" build "${COMPOSE_SERVICES[@]}"
else
  echo "deploy.sh: skipping docker compose build (--no-build)"
fi

docker compose "${PASS_THROUGH[@]}" "${COMPOSE_FILES[@]}" up -d "${COMPOSE_SERVICES[@]}"

echo ""
echo "deploy.sh: done. Default URLs (see AICOM_PORT_* in .env):"
echo "  Frontend  http://localhost:\${AICOM_PORT_FRONTEND:-9080}"
echo "  API       http://localhost:\${AICOM_PORT_API:-9081}/api/health"
