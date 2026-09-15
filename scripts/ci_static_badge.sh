#!/usr/bin/env bash
# Refresh docs/badges/coverage.svg for smoke / validation repos.
# CI only verifies generation — never git-push (avoids github-actions[bot] contributors).
# Committed badges ship via scripts/mirror_satellites.sh from the monorepo.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

label="${1:-checks}"
value="${2:-pass}"
python scripts/generate_static_badge.py "$label" "$value" docs/badges/coverage.svg

if [[ "${AICOM_CI_ENFORCE_BADGE_SYNC:-}" == "1" ]]; then
  git diff --quiet docs/badges/coverage.svg || {
    echo "docs/badges/coverage.svg drift — update in monorepo and re-mirror" >&2
    exit 1
  }
fi
