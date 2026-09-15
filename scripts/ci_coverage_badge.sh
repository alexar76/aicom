#!/usr/bin/env bash
# Run pytest with coverage JSON + refresh docs/badges/coverage.svg.
# CI only verifies generation — never git-push (avoids github-actions[bot] contributors).
# Committed badges ship via scripts/mirror_satellites.sh from the monorepo.
#
# Usage: scripts/ci_coverage_badge.sh [--] [pytest args...]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

pip install -q pytest-cov

pytest_args=()
if [[ "${1:-}" == "--" ]]; then
  shift
fi
if [[ $# -gt 0 ]]; then
  pytest_args=("$@")
else
  pytest_args=(tests/ -q --tb=short --maxfail=5)
fi

pytest "${pytest_args[@]}" --cov-report=json:coverage.json
python scripts/generate_coverage_badge.py coverage.json docs/badges/coverage.svg

# Refresh the live tests-count endpoint badge for repos that opted in.
if [[ -f docs/badges/tests.json ]]; then
  python scripts/generate_tests_badge.py --rootdir . --out docs/badges/tests.json
fi

if [[ "${AICOM_CI_ENFORCE_BADGE_SYNC:-}" == "1" ]]; then
  git diff --quiet docs/badges/coverage.svg || {
    echo "docs/badges/coverage.svg drift — update in monorepo and re-mirror" >&2
    exit 1
  }
  if [[ -f docs/badges/tests.json ]]; then
    git diff --quiet docs/badges/tests.json || {
      echo "docs/badges/tests.json drift — update in monorepo and re-mirror" >&2
      exit 1
    }
  fi
  if [[ -f docs/badges/tests.svg ]]; then
    git diff --quiet docs/badges/tests.svg || {
      echo "docs/badges/tests.svg drift — update in monorepo and re-mirror" >&2
      exit 1
    }
  fi
fi
