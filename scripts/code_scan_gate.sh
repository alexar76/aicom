#!/usr/bin/env bash
# Code scan gate: findings that REF brings in compared with BASE. Two layers:
#
#   1. scripts/vulnetix_class_scan.py: our rules for the bug classes Vulnetix found here in October 2026
#      (open without a key, check-then-connect SSRF, forwarding-header trust, ssh without host keys). Stdlib.
#   2. Semgrep with the public registry rule sets p/python, p/javascript, p/typescript, p/owasp-top-ten, in
#      --baseline-commit mode (only results in what changed since BASE), severities ERROR and WARNING.
#      Pinned version; rules are fetched from the registry at run time, metrics off.
#
# Old findings never block: the gate judges the change, not the backlog. A finding is accepted in code with
# `# vx-ok: <reason>` (layer 1) or `# nosemgrep: <rule-id>` with a reason next to it (layer 2).
#
# Usage: scripts/code_scan_gate.sh [REF] [BASE]       (default HEAD, and BASE = REF's first parent)
# Env:   CODE_SCAN_SEMGREP=0 skips layer 2.  SEMGREP_VERSION overrides the pin.
# Exit:  0 clean, 1 new findings, 2 a layer could not run (tool missing, BASE unknown).
set -euo pipefail

REF="${1:-HEAD}"
BASE="${2:-}"
ROOT="$(git rev-parse --show-toplevel)"
SEMGREP_VERSION="${SEMGREP_VERSION:-1.185.0}"
cd "$ROOT"

REF_SHA="$(git rev-parse --verify "${REF}^{commit}")"
if [[ -z "$BASE" || "$BASE" =~ ^0+$ ]] || ! git cat-file -e "${BASE}^{commit}" 2>/dev/null; then
  BASE="$(git rev-parse --verify "${REF_SHA}^" 2>/dev/null || true)"
fi
if [[ -z "$BASE" ]]; then
  echo "code scan gate: no base commit to compare with" >&2
  exit 2
fi
BASE_SHA="$(git rev-parse --verify "${BASE}^{commit}")"
echo "code scan gate: ${BASE_SHA:0:10}..${REF_SHA:0:10}"

rc=0
skipped=0

# --- layer 1 -----------------------------------------------------------------------------------------------------
if python3 "$ROOT/scripts/vulnetix_class_scan.py" --ref "$REF_SHA" --base "$BASE_SHA"; then
  echo "  ✓ vulnetix-class rules: nothing new"
else
  rc=1
fi

# --- layer 2 -----------------------------------------------------------------------------------------------------
if [[ "${CODE_SCAN_SEMGREP:-1}" == "0" ]]; then
  echo "  ⚠️  CODE_SCAN_SEMGREP=0 — Semgrep registry rules not run"
else
  SEMGREP=()
  if command -v semgrep >/dev/null 2>&1 && semgrep --version 2>/dev/null | grep -qx "$SEMGREP_VERSION"; then
    SEMGREP=(semgrep)
  elif command -v uv >/dev/null 2>&1; then
    SEMGREP=(uv run --quiet --no-project --with "semgrep==${SEMGREP_VERSION}" semgrep)
  elif python3 -m pip --version >/dev/null 2>&1; then
    python3 -m pip install --quiet "semgrep==${SEMGREP_VERSION}" >/dev/null 2>&1 && SEMGREP=(semgrep) || true
  fi
  CHANGED=()
  if [[ ${#SEMGREP[@]} -eq 0 ]]; then
    echo "  ⚠️  Semgrep not available (pip install semgrep==${SEMGREP_VERSION})" >&2
    skipped=1
  else
    while IFS= read -r f; do CHANGED+=("$f"); done < <(git diff --name-only --no-renames --diff-filter=ACMR \
      "$BASE_SHA" "$REF_SHA" -- '*.py' '*.js' '*.mjs' '*.cjs' '*.ts' '*.tsx' '*.jsx' \
      | grep -Ev '(^|/)(artifacts|docs|node_modules|tests?|dist|build|vendor|\.venv)/|(^|/)test_[^/]*\.py$|\.min\.js$' || true)
  fi
  if [[ ${#SEMGREP[@]} -gt 0 && ${#CHANGED[@]:-0} -eq 0 ]]; then
    echo "  ✓ Semgrep: no changed Python/JS/TS source to scan"
  elif [[ ${#SEMGREP[@]} -gt 0 ]]; then
    # Scan REF in its own checkout so the gate judges what is pushed, not the working tree.
    TMP="$(mktemp -d)"
    trap 'git -C "$ROOT" worktree remove --force "$TMP/tree" >/dev/null 2>&1 || true; rm -rf "$TMP"' EXIT
    # Sparse: only the changed files are checked out, the index stays consistent for --baseline-commit.
    git worktree add --quiet --no-checkout --detach "$TMP/tree" "$REF_SHA"
    printf '%s\n' "${CHANGED[@]}" | git -C "$TMP/tree" sparse-checkout set --no-cone --stdin
    git -C "$TMP/tree" checkout --quiet "$REF_SHA"
    set +e
    ( cd "$TMP/tree" && "${SEMGREP[@]}" scan --metrics=off --disable-version-check --error \
        --config p/python --config p/javascript --config p/typescript --config p/owasp-top-ten \
        --severity ERROR --severity WARNING --baseline-commit "$BASE_SHA" --timeout 20 --max-target-bytes 1000000 \
        --exclude 'artifacts/**' --exclude 'docs/**' --exclude '**/node_modules/**' --exclude '**/tests/**' \
        --exclude '**/test_*.py' --exclude '**/*.min.js' --exclude '**/dist/**' --exclude '**/build/**' \
        --exclude '**/vendor/**' --exclude '**/.venv/**' --quiet --text "${CHANGED[@]}" ) >"$TMP/semgrep.txt" 2>"$TMP/semgrep.err"
    src=$?
    set -e
    if [[ "$src" -eq 0 ]]; then
      echo "  ✓ Semgrep ${SEMGREP_VERSION} (python, javascript, typescript, owasp-top-ten): nothing new"
    elif [[ "$src" -eq 1 ]]; then
      cat "$TMP/semgrep.txt"
      echo "  ✗ Semgrep: new findings above" >&2
      rc=1
    else
      echo "  ⚠️  Semgrep could not run (exit ${src}): $(tail -3 "$TMP/semgrep.err" | tr '\n' ' ')" >&2
      skipped=1
    fi
  fi
fi

if [[ "$rc" -ne 0 ]]; then
  exit 1
fi
[[ "$skipped" -eq 1 ]] && exit 2
exit 0
