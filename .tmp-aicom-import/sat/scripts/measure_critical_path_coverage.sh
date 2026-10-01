#!/usr/bin/env bash
# Measure pytest coverage on critical paths (orchestrator FSM, security, demo guards).
set -euo pipefail
cd "$(dirname "$0")/.."

python3 -m pytest \
  tests/test_state_machine_transitions.py \
  tests/test_state_machine_async_wrappers.py \
  tests/test_prod_startup_guard.py \
  tests/test_public_demo_guard.py \
  tests/test_sandbox_isolation_hardening.py \
  tests/test_product_showcase_base_url.py \
  --cov=orchestrator.state_machine \
  --cov=orchestrator.pipeline_transitions \
  --cov=security.prod_startup_guard \
  --cov=security.docker_sandbox \
  --cov-report=term-missing \
  -q "$@"

echo ""
echo "Tip: full-repo coverage is uneven; extend this script as new critical modules gain tests."
