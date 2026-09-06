#!/usr/bin/env bash
# Clone satellite repos excluded from the trimmed alexar76/aicom factory tree so pytest can import them.
set -euo pipefail

ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$ROOT"

clone_if_missing() {
  local dir="$1"
  local repo="$2"
  if [[ -f "$dir/pyproject.toml" || -f "$dir/setup.py" ]]; then
    return 0
  fi
  rm -rf "$dir"
  git clone --depth 1 "https://github.com/alexar76/${repo}.git" "$dir"
}

clone_if_missing acex acex
clone_if_missing aimarket-hub aimarket-hub

if [[ ! -d plugins/aimarket-mcp-packager ]]; then
  tmp_plugins="_ci_aimarket-plugins"
  rm -rf "$tmp_plugins"
  git clone --depth 1 https://github.com/alexar76/aimarket-plugins.git "$tmp_plugins"
  mkdir -p plugins
  cp -R "$tmp_plugins/plugins/." plugins/
  rm -rf "$tmp_plugins"
fi
