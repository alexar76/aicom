#!/usr/bin/env bash
# Verify Groth16 ceremony artifacts before enabling AIMARKET_ZK_BACKEND=groth16.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"
python3 - <<'PY'
from security.zk_artifacts import production_zk_issues
import os
import sys

# Allow checking without AIFACTORY_PROD
os.environ.setdefault("AIMARKET_ZK_BACKEND", "groth16")
issues = production_zk_issues()
if issues:
    print("ZK artifact check FAILED:")
    for i in issues:
        print(f"  - {i}")
    sys.exit(1)
print("ZK artifact check OK")
PY
