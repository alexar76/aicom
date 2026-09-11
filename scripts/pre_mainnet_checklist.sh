#!/usr/bin/env bash
# Pet-project pre-mainnet checklist (no external audit required for self-host demo).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

pass=0
fail=0
warn=0

ok() { echo -e "${GREEN}✓${NC} $1"; pass=$((pass + 1)); }
bad() { echo -e "${RED}✗${NC} $1"; fail=$((fail + 1)); }
note() { echo -e "${YELLOW}!${NC} $1"; warn=$((warn + 1)); }

echo "=== AIMarket pet-project checklist ==="
echo ""

# Prod guard smoke
if AIFACTORY_PROD=1 AIFACTORY_DEV_BOOTSTRAP_PASSWORD=demo123 python3 -c \
  "from security.prod_startup_guard import production_startup_issues; import sys; sys.exit(0 if production_startup_issues() else 1)" 2>/dev/null; then
  bad "prod guard should reject demo123 bootstrap password"
else
  ok "prod guard rejects weak bootstrap password"
fi

# pip-audit gate
if bash scripts/pip_audit_gate.sh >/dev/null 2>&1; then
  ok "pip-audit gate (ollama exceptions only)"
else
  bad "pip-audit gate failed — run: bash scripts/pip_audit_gate.sh"
fi

# Slither (optional)
if command -v slither >/dev/null 2>&1; then
  if bash scripts/run_contract_audit.sh >/dev/null 2>&1; then
    ok "slither scan completed (see contracts/audits/)"
  else
    note "slither reported findings — review contracts/audits/slither-summary-*.md"
  fi
else
  note "slither not installed — pip install slither-analyzer"
fi

# Multisig
if [[ -n "${SAFE_ADDR:-}" ]]; then
  ok "SAFE_ADDR set ($SAFE_ADDR) — run scripts/multisig_transfer_runbook.sh"
else
  note "KI-4: set SAFE_ADDR + run scripts/multisig_transfer_runbook.sh for mainnet contracts"
fi

# Oracle quorum
if [[ -n "${AIMARKET_ORACLE_AUTHORITIES:-}" ]]; then
  ok "AIMARKET_ORACLE_AUTHORITIES configured (m-of-n dispute oracle)"
else
  note "O-1: set AIMARKET_ORACLE_AUTHORITIES + AIMARKET_ORACLE_THRESHOLD for dispute quorum"
fi

# Load test script present
if [[ -x scripts/load_test_factory.sh ]]; then
  ok "load test script ready (./scripts/load_test_factory.sh after prod stack up)"
else
  bad "scripts/load_test_factory.sh missing or not executable"
fi

echo ""
echo "Summary: ${pass} passed, ${fail} failed, ${warn} notes"
[[ "$fail" -eq 0 ]]
