#!/usr/bin/env bash
# Ensure satellite directories exist before Docker COPY (trimmed VPS clones).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

missing=()
for dir in acex aimarket-hub aimarket-protocol plugins; do
  if [[ ! -d "$ROOT/$dir" ]]; then
    missing+=("$dir")
  fi
done

if [[ ${#missing[@]} -eq 0 ]]; then
  echo "ensure_deploy_satellites: all satellite dirs present"
  exit 0
fi

echo "ensure_deploy_satellites: missing ${missing[*]} — fetching from GitHub…" >&2
if [[ -x "$ROOT/scripts/ci_fetch_factory_test_deps.sh" ]]; then
  "$ROOT/scripts/ci_fetch_factory_test_deps.sh" "$ROOT"
else
  echo "ERROR: scripts/ci_fetch_factory_test_deps.sh not found" >&2
  exit 1
fi

for dir in "${missing[@]}"; do
  if [[ ! -d "$ROOT/$dir" ]]; then
    echo "ERROR: still missing $dir after fetch" >&2
    exit 1
  fi
done
echo "ensure_deploy_satellites: satellites ready"
