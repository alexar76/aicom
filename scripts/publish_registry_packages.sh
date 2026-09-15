#!/usr/bin/env bash
# Publish aimarket-hub + top-5 plugins to PyPI (requires PYPI_API_TOKEN).
#
# Order: hub first (plugins depend on aimarket-hub>=3.0.0).
#
# Usage:
#   PYPI_API_TOKEN=pypi-... ./scripts/publish_registry_packages.sh
#   ./scripts/publish_registry_packages.sh --dry-run
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DRY=0
[[ "${1:-}" == "--dry-run" ]] && DRY=1

publish() {
  local dir="$1"
  if [[ "$DRY" -eq 1 ]]; then
    "$ROOT/scripts/publish_pypi.sh" "$dir" --dry-run
  else
    "$ROOT/scripts/publish_pypi.sh" "$dir"
  fi
}

echo "=== 1/6 aimarket-hub ==="
publish aimarket-hub

for plugin in aimarket-tee aimarket-channels aimarket-reputation aimarket-safety aimarket-mcp-packager; do
  echo ""
  echo "=== plugins/$plugin ==="
  publish "plugins/$plugin"
done

echo ""
echo "OK — published hub + 5 plugins to PyPI"
