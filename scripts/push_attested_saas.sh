#!/usr/bin/env bash
# push_attested_saas.sh — test the Attested SaaS tree, then push the MONOREPO to Gitea.
#
# There are no standalone repos for these products, and there should not be: the
# whole `attested/` tree ships inside the monorepo, which is what Gitea#2 holds.
# This wrapper exists for the two things `push_gitea_monorepo.sh` cannot know:
#
#   1. the three product test suites pass;
#   2. `github_published` is still false for the attested tree — publishing this
#      family to GitHub is a deliberate decision, never a side effect.
#
# Usage:
#   ./scripts/push_attested_saas.sh              # tests, guard, push
#   ./scripts/push_attested_saas.sh --dry-run    # tests and guard only
#   ./scripts/push_attested_saas.sh --skip-tests # not recommended
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

DRY_RUN=0
SKIP_TESTS=0
PRODUCTS=(attested/attested-deal attested/attested-meter attested/attested-prove)

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)    DRY_RUN=1; shift ;;
    --skip-tests) SKIP_TESTS=1; shift ;;
    -h|--help)    sed -n '2,15p' "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 1 ;;
  esac
done

# ── GitHub guard ─────────────────────────────────────────────────────────────
python3 - <<'PY'
import sys, yaml, pathlib
m = yaml.safe_load(pathlib.Path("scripts/satellite-map.yaml").read_text(encoding="utf-8"))
entry = {s["id"]: s for s in m.get("satellites", [])}.get("attested")
if entry is None:
    sys.exit("ERROR: satellite 'attested' is missing from satellite-map.yaml")
if entry.get("github_published", True) is not False:
    sys.exit("ERROR: 'attested' is no longer github_published:false — refusing to push. "
             "Publishing this family to GitHub is a deliberate decision, not a side effect.")
print("  github_published:false confirmed for the attested tree")
PY

# ── tests ────────────────────────────────────────────────────────────────────
if [[ "$SKIP_TESTS" -eq 0 ]]; then
  VENV="${ATTESTED_TEST_PYTHON:-$ROOT/attested/attested-saas-gateway/.venv/bin/python}"
  if [[ ! -x "$VENV" ]]; then
    echo "warning: no interpreter at $VENV; set ATTESTED_TEST_PYTHON or pass --skip-tests" >&2
    exit 1
  fi
  for product in "${PRODUCTS[@]}" expert-memory-market; do
    echo "→ pytest $product"
    ( cd "$product" && "$VENV" -m pytest -q ) || {
      echo "ERROR: $product tests failed — not publishing" >&2; exit 1; }
  done
fi

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo
  echo "dry run — would run: ./scripts/push_gitea_monorepo.sh"
  exit 0
fi

./scripts/push_gitea_monorepo.sh

echo
echo "Done. Gitea only — GitHub was never contacted."
