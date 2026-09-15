#!/usr/bin/env bash
# Editable installs for satellites fetched by ci_fetch_factory_test_deps.sh (factory CI only).
set -euo pipefail

ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$ROOT"

if [[ -f aimarket-hub/pyproject.toml ]]; then
  pip install --no-cache-dir -e ./aimarket-hub
fi

if [[ -f acex/pyproject.toml ]]; then
  pip install --no-cache-dir -e ./acex
fi
