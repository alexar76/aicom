#!/usr/bin/env bash
# Run backend pytest suite and frontend unit tests (Vitest).
# Usage: ./scripts/run_all_tests.sh [extra pytest args…]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Writable data root (avoids PermissionError when repo ``data/`` is owned by another uid).
TEST_DATA="${AIFACTORY_DATA_ROOT:-${ROOT}/.pytest-data}"
mkdir -p "${TEST_DATA}/"{state,logs,secrets,store}
export AIFACTORY_DATA_ROOT="${TEST_DATA}"
export USE_SQLITE="${USE_SQLITE:-true}"

PY="${ROOT}/.test-venv/bin/python"
if [[ ! -x "$PY" ]]; then
  PY="${ROOT}/.venv/bin/python"
fi
if [[ ! -x "$PY" ]]; then
  PY="python3"
fi

echo "==> Backend: pytest tests/ (AIFACTORY_DATA_ROOT=${AIFACTORY_DATA_ROOT})"
"$PY" -m pytest tests/ -q "$@"

if [[ -f "${ROOT}/web/frontend/package.json" ]]; then
  echo "==> Frontend: vitest (unit)"
  (
    cd "${ROOT}/web/frontend"
    if [[ ! -d node_modules ]]; then
      npm ci
    fi
    npm run test:unit
  )
fi

echo "==> All test suites finished OK"
