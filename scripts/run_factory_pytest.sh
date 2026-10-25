#!/usr/bin/env bash
# Factory CI pytest entrypoint — full suite minus heavy browser E2E (see ci.yml).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export USE_SQLITE="${USE_SQLITE:-true}"
export AIFACTORY_DATA_ROOT="${AIFACTORY_DATA_ROOT:-/tmp/aicom-data}"
mkdir -p "$AIFACTORY_DATA_ROOT/logs"

PYTEST="${ROOT}/.venv/bin/pytest"
PYTHON="${ROOT}/.venv/bin/python"
if [ ! -x "$PYTEST" ]; then
  PYTEST=pytest
fi
if [ ! -x "$PYTHON" ]; then
  PYTHON=python3
fi

# A timeout is an incomplete run, even when coverage has already been saved.
if [[ "${GITHUB_ACTIONS:-}" == "true" ]]; then
  exec "$PYTHON" scripts/run_factory_pytest_ci.py "$@"
fi

# Local dev: plain pytest + pytest-cov.
PYTEST_TIMEOUT_ARGS=(--timeout=45)
if [[ "$(uname -s)" == "Darwin" ]]; then
  PYTEST_TIMEOUT_ARGS+=(--timeout-method=thread)
fi

"$PYTEST" -q "${PYTEST_TIMEOUT_ARGS[@]}" \
  --ignore=tests/test_marketplace_e2e.py \
  --ignore=tests/test_visual_regression.py \
  --ignore=tests/test_browser_fastapi_login_integration.py \
  --ignore=tests/test_visual_standards_playwright.py \
  --ignore=tests/test_diagram_golden_visual.py \
  -k "not test_full_software_browser_e2e" \
  --cov \
  --cov-report=term-missing:skip-covered \
  --cov-report=json:coverage.json \
  "$@"

"$PYTHON" scripts/check_payment_coverage.py coverage.json
