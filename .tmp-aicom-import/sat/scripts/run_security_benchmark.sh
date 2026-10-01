#!/usr/bin/env bash
# Run the security-focused pytest subset (CI security-benchmark job).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export USE_SQLITE="${USE_SQLITE:-true}"
export JWT_SECRET_KEY="${JWT_SECRET_KEY:-$(python3 -c 'print("0"*48)')}"

PYTEST="${ROOT}/.venv/bin/pytest"
if [ ! -x "$PYTEST" ]; then
  PYTEST=pytest
fi

"$PYTEST" -q \
  tests/test_security.py \
  tests/test_security_hardening.py \
  tests/test_csrf_middleware.py \
  tests/test_firewall_middleware.py \
  tests/test_firewall_encryption.py \
  tests/test_audit_logger_integrity.py \
  tests/test_agent_handoff_audit.py \
  tests/test_sandbox_isolation_hardening.py \
  tests/test_llm_usage_guard.py \
  tests/test_admin_auth.py \
  tests/test_webauthn_admin.py \
  "$@"
