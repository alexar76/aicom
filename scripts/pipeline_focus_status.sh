#!/usr/bin/env bash
# Pipeline focus status — use this instead of curl | python3 <<'PY' (heredoc steals stdin → JSONDecodeError).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

API_URL="${AICOM_API_URL:-}"
TOKEN="${AICOM_ADMIN_TOKEN:-}"

if [[ -z "$TOKEN" ]] && docker ps --format '{{.Names}}' 2>/dev/null | grep -qx 'aicom-app-1'; then
  TOKEN="$(docker exec aicom-app-1 python3 -c \
    "from web.backend.core.security import SecurityManager; print(SecurityManager().create_access_token('admin', role='admin'))" 2>/dev/null || true)"
fi

if [[ -n "${1:-}" && "${1}" != --* ]]; then
  API_URL="$1"
  shift
fi
API_URL="${API_URL:-http://127.0.0.1:9081}"

ARGS=(--api-url "$API_URL" --human "$@")
if [[ -n "$TOKEN" ]]; then
  ARGS=(--api-url "$API_URL" --token "$TOKEN" --human "$@")
fi

exec python3 "$ROOT/scripts/pipeline_focus_status.py" "${ARGS[@]}"
