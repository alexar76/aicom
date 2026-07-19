#!/usr/bin/env bash
# Clone satellite sources excluded from trimmed alexar76/aicom (SEO landing build).
set -euo pipefail

ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$ROOT"

clone_if_missing() {
  local dir="$1"
  local repo="$2"
  local marker="$3"
  if [[ -e "$marker" ]]; then
    return 0
  fi
  rm -rf "$dir"
  git clone --depth 1 "https://github.com/alexar76/${repo}.git" "$dir"
}

# courses/catalog.yaml + *-course/ folders for learn/ landings
if [[ ! -f courses/catalog.yaml ]]; then
  tmp="_ci_aimarket-courses"
  rm -rf "$tmp" courses
  git clone --depth 1 https://github.com/alexar76/aimarket-courses.git "$tmp"
  mkdir -p courses
  cp "$tmp/catalog.yaml" courses/
  for sku in "$tmp"/*-course; do
    [[ -d "$sku" ]] || continue
    cp -R "$sku" "courses/$(basename "$sku")"
  done
  rm -rf "$tmp"
fi

clone_if_missing oracles oracles oracles/frontend/src/oracles.ts
clone_if_missing argus argus argus/docs/use-case-external-operator.md

echo "SEO build deps ready (courses + oracles + argus guide)"
