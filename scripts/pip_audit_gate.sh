#!/usr/bin/env bash
# KI-5 gate: pip-audit must pass with no accepted vulnerability exceptions.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

python3 -m pip_audit -r requirements.txt --desc on

echo "pip_audit_gate: OK (zero vulnerability exceptions)"
