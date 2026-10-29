#!/usr/bin/env bash
# Whole-repo Python bug gate: syntax errors, invalid comparisons, misplaced statements and
# undefined names (ruff E9, F63, F7, F82) in every tracked .py file at a ref.
#
# The style/type gates in CI cover the critical modules only (see the scope note in
# pyproject.toml). This one covers everything, satellites and legacy code included, with
# the rules that are bugs rather than style, so a green run says something about the whole
# tree. It reads the committed files at REF, not the working tree, so a push is judged by
# what it pushes.
#
# Usage: scripts/python_bug_gate.sh [REF]      (default HEAD)
# Exit: 0 clean, 1 findings, 2 ruff not available.
set -euo pipefail

REF="${1:-HEAD}"
ROOT="$(git rev-parse --show-toplevel)"

RUFF=()
if command -v ruff >/dev/null 2>&1; then
  RUFF=(ruff)
elif python3 -m ruff --version >/dev/null 2>&1; then
  RUFF=(python3 -m ruff)
else
  common="$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)"
  for cand in "$ROOT/.venv/bin/ruff" "${common%/.git}/.venv/bin/ruff"; do
    if [[ -x "$cand" ]]; then
      RUFF=("$cand")
      break
    fi
  done
fi
if [[ ${#RUFF[@]} -eq 0 ]]; then
  echo "python bug gate: ruff not found (pip install ruff)" >&2
  exit 2
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
git -C "$ROOT" archive "$REF" -- '*.py' | tar -x -C "$TMP"

# Project templates hold placeholders (__METIS_PYTHON__) that are filled in at generation time.
# docs/evidence holds archived scripts of past runs, hashed in their manifests: some ran inside a
# harness that exec'd its setup into globals(), so their names are undefined on their own, and
# editing them would break the record. They are not code anything imports.
cd "$TMP"
"${RUFF[@]}" check . --isolated --no-cache \
  --select E9,F63,F7,F82 \
  --extend-exclude "create-aimarket-agent/src/create_aimarket_agent/templates" \
  --extend-exclude "docs/evidence" \
  --output-format concise
