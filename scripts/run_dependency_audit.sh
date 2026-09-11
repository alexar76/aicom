#!/usr/bin/env bash
# Dependency and static-security audit (mirrors .github/workflows/security-scan.yml).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PY="${ROOT}/.venv/bin/python"
PIP="${ROOT}/.venv/bin/pip"
if [[ ! -x "$PY" ]]; then
  PY=python3
  PIP=pip3
fi

echo "=== bandit (Python SAST, fail on High) ==="
"$PIP" install -q bandit
"$PY" -m bandit -r web/backend security llm aimarket-hub orchestrator agents \
  -x '*/tests/*' \
  -lll \
  -q

echo "=== pip-audit (Python dependencies) ==="
"$PIP" install -q pip-audit
set +e
"$PY" -m pip_audit -r requirements.txt --format json -o pip-audit-report.json
audit_rc=$?
set -e
if [[ $audit_rc -ne 0 ]]; then
  echo "pip-audit: known CVEs reported — see pip-audit-report.json and docs/audit-remediation.md"
  echo "(CI uploads the report; upgrade path tracked in audit-remediation.md § Dependencies)"
fi

echo "=== npm audit (frontend) ==="
if [[ -f web/frontend/package-lock.json ]]; then
  (
    cd web/frontend
    npm ci --ignore-scripts 2>/dev/null || npm install --ignore-scripts
    npm audit --audit-level=high || {
      echo "npm audit: high/critical findings — see docs/audit-remediation.md § Dependencies"
    }
  )
fi

echo "=== npm audit (aimarket-sdks/typescript) ==="
if [[ -f aimarket-sdks/typescript/package-lock.json ]]; then
  (
    cd aimarket-sdks/typescript
    npm ci --ignore-scripts 2>/dev/null || npm install --ignore-scripts
    npm audit --audit-level=high || true
  )
fi

echo "Done."
