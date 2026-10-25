#!/usr/bin/env bash
# Local factory dependency and static-security audit. Never install or rewrite packages.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PY="${AIFACTORY_AUDIT_PYTHON:-${ROOT}/.venv/bin/python}"
if [[ -z "${AIFACTORY_AUDIT_PYTHON:-}" && ! -x "$PY" ]]; then
  PY=python3
fi
if ! command -v "$PY" >/dev/null 2>&1; then
  echo "Audit Python is unavailable: $PY" >&2
  exit 2
fi
audit_failed=0
REPORT_DIR="${AIFACTORY_AUDIT_REPORT_DIR:-${ROOT}/.internal/audit}"
mkdir -p "$REPORT_DIR"
PIP_REPORT="${REPORT_DIR}/pip-audit-report.json"

echo "=== bandit (Python SAST, fail on High) ==="
if ! "$PY" -m bandit -r web/backend security llm core aimarket-hub orchestrator agents \
  -x '*/tests/*,*/.venv*/*,*/venv/*,*/site-packages/*,*/node_modules/*' \
  -lll \
  -q; then
  echo "Bandit failed; review findings or tool errors." >&2
  audit_failed=1
fi

echo "=== pip-audit (Python dependencies) ==="
if ! "$PY" -m pip_audit -r requirements.txt --format json -o "$PIP_REPORT"; then
  echo "pip-audit failed; review $PIP_REPORT or tool/network errors." >&2
  audit_failed=1
fi

echo "=== npm audit (frontend) ==="
if [[ -f web/frontend/package-lock.json ]]; then
  if ! (
    cd web/frontend
    npm audit --package-lock-only --ignore-scripts --include=dev --audit-level=high
  ); then
    echo "Frontend npm audit failed." >&2
    audit_failed=1
  fi
fi

echo "=== npm audit (aimarket-sdks/typescript) ==="
if [[ -f aimarket-sdks/typescript/package-lock.json ]]; then
  if ! (
    cd aimarket-sdks/typescript
    npm audit --package-lock-only --ignore-scripts --include=dev --audit-level=high
  ); then
    echo "TypeScript SDK npm audit failed." >&2
    audit_failed=1
  fi
fi

if [[ $audit_failed -ne 0 ]]; then
  echo "Dependency audit FAILED." >&2
  exit 1
fi
echo "Dependency audit passed."
