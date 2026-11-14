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

if [[ -f atlas/pyproject.toml ]]; then
  pip install --no-cache-dir -e ./atlas
fi

# Optional satellite packages used by factory signing / registry / mesh tests.
for path in \
  oracles/core \
  platon/backend \
  oracles/oracles/platon/backend \
  aimarket-hub/plugins/aimarket-provenance \
  plugins/aimarket-provenance \
  momus \
  skopos \
  gaia \
  basanos \
  histor \
  themis \
  aimarket-agent \
  aimarket-bridges \
  aimarket-protocol \
  create-aimarket-agent \
  lottery/relayer \
  lottery/agent \
  ai-service-mesh/backend
do
  if [[ -f "$path/pyproject.toml" || -f "$path/setup.py" ]]; then
    pip install --no-cache-dir -e "./$path"
  fi
done
