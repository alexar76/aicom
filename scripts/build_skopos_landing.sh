#!/usr/bin/env bash
# Prepare skopos/docs/landing/ for GitHub Pages (https://alexar76.github.io/skopos/).
#
#   ./scripts/build_skopos_landing.sh
#
# Called from remote-sync.sh and before publish_all_repos.sh --satellite skopos.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LANDING="${ROOT}/skopos/docs/landing"

if [[ ! -f "${LANDING}/index.html" ]]; then
  echo "ERROR: ${LANDING}/index.html not found" >&2
  exit 1
fi

touch "${LANDING}/.nojekyll"
echo "OK: SKOPOS landing ready for GitHub Pages (${LANDING})"
