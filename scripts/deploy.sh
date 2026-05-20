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

# Refuse deploy from a truncated workspace (same guard as .gitea/workflows/deploy.yml).
require_intact_tree() {
  local f
  for f in \
    README.md docker-compose.yml pipeline_worker.py entrypoint.sh Dockerfile \
    llm/router.py orchestrator/sqlite_manager.py \
    web/frontend/lib/api.ts web/backend/api/products.py \
    ; do
    if [[ ! -f "$ROOT/$f" ]]; then
      echo "FATAL: deploy aborted — missing $f (workspace looks truncated)" >&2
      echo "Run: git restore .   # from repo root, then retry deploy" >&2
      exit 3
    fi
  done
}
require_intact_tree

if [[ "$NO_ENV_FILL" -eq 0 ]]; then
  FILL_ARGS=(--env-file "$ENV_FILE")
  if [[ -n "$PUBLIC_URL" ]]; then
    FILL_ARGS+=(--public-url "$PUBLIC_URL")
  fi
  python3 "$ROOT/scripts/fill_production_env.py" "${FILL_ARGS[@]}"
fi

COMPOSE_FILES=(-f docker-compose.yml)
if [[ "${AIFACTORY_USE_HOST_DOCKER:-}" == "1" ]]; then
  COMPOSE_FILES+=(-f docker-compose.host-docker.yml)
else
  COMPOSE_FILES+=(-f docker-compose.dind.yml)
fi
# Only mount Docker secrets when every file referenced in docker-compose.secrets.yml exists.
_secrets_overlay_ready() {
  local f
  for f in deepseek_api_key anthropic_api_key groq_api_key together_api_key; do
    [[ -f "$ROOT/data/secrets/llm/$f" ]] || return 1
  done
}
if _secrets_overlay_ready; then
  COMPOSE_FILES+=(-f docker-compose.secrets.yml)
fi

if [[ "$NO_BUILD" -eq 0 ]]; then
  docker compose "${PASS_THROUGH[@]}" "${COMPOSE_FILES[@]}" build "${COMPOSE_SERVICES[@]}"
else
  echo "deploy.sh: skipping docker compose build (--no-build)"
fi

docker compose "${PASS_THROUGH[@]}" "${COMPOSE_FILES[@]}" up -d "${COMPOSE_SERVICES[@]}"

if [[ -x "$ROOT/scripts/install-claude-code-deepseek.sh" ]]; then
  "$ROOT/scripts/install-claude-code-deepseek.sh" -q || true
fi

echo ""
echo "deploy.sh: done. Default URLs (see AICOM_PORT_* in .env):"
echo "  Frontend  http://localhost:\${AICOM_PORT_FRONTEND:-9080}"
echo "  API       http://localhost:\${AICOM_PORT_API:-9081}/api/health"
