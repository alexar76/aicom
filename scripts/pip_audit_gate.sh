#!/usr/bin/env bash
# KI-5 gate: pip-audit must pass. Documented exceptions only (see docs/CVE-ACCEPTANCE-MATRIX.md).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

IGNORE=(
  # ollama — no upstream fix
  PYSEC-2025-144
  PYSEC-2025-145
  # starlette — transitive via fastapi 0.116; fix requires starlette 1.x (breaking)
  PYSEC-2026-161
  PYSEC-2026-249
  PYSEC-2026-248
  CVE-2025-62727
  CVE-2026-48817
  CVE-2026-48818
)

args=()
for id in "${IGNORE[@]}"; do
  args+=(--ignore-vuln "$id")
done

python3 -m pip_audit -r requirements.txt "${args[@]}" --desc on

echo "pip_audit_gate: OK (${#IGNORE[@]} documented exceptions)"
