#!/usr/bin/env bash
# Publish npm namespace placeholders under npm-reserve/packages/*.
#
#   NPM_TOKEN=npm_... ./scripts/publish_npm_placeholders.sh
#   ./scripts/publish_npm_placeholders.sh --dry-run
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RESERVE="$ROOT/npm-reserve/packages"
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help)
      echo "Usage: NPM_TOKEN=... $0 [--dry-run]"
      exit 0
      ;;
    *) echo "unknown option: $1" >&2; exit 1 ;;
  esac
done

TOKEN="${NPM_TOKEN:-${NODE_AUTH_TOKEN:-}}"
[[ "$DRY_RUN" -eq 1 || -n "$TOKEN" ]] || {
  echo "error: set NPM_TOKEN (or NODE_AUTH_TOKEN)" >&2
  exit 3
}

NPMRC_PUBLISH=""
if [[ "$DRY_RUN" -eq 0 ]]; then
  NPMRC_PUBLISH="$(mktemp "${TMPDIR:-/tmp}/npmrc.placeholders.XXXXXX")"
  printf '//registry.npmjs.org/:_authToken=%s\n' "$TOKEN" > "$NPMRC_PUBLISH"
  npm --userconfig "$NPMRC_PUBLISH" whoami || {
    echo "error: npm token invalid (whoami failed)" >&2
    exit 4
  }
fi

publish_one() {
  local dir="$1"
  local name version
  name="$(node -p "require('$dir/package.json').name")"
  version="$(node -p "require('$dir/package.json').version")"

  if npm view "${name}@${version}" version >/dev/null 2>&1; then
    echo "SKIP  $name@$version (already on npm)"
    return 0
  fi

  echo "== Publish $name@$version =="
  (
    cd "$dir"
    if [[ -f package-lock.json ]]; then
      npm ci
    fi
    npm test
    if [[ "$DRY_RUN" -eq 1 ]]; then
      npm publish --dry-run --access public
    else
      if npm --userconfig "$NPMRC_PUBLISH" publish --access public 2>"${dir}.publish.err"; then
        :
      elif grep -q 'previously published versions' "${dir}.publish.err" 2>/dev/null; then
        echo "SKIP  $name@$version (already on npm)"
        rm -f "${dir}.publish.err"
        return 0
      else
        cat "${dir}.publish.err" >&2
        rm -f "${dir}.publish.err"
        return 1
      fi
      rm -f "${dir}.publish.err"
    fi
  )
  echo "OK    $name@$version"
}

shopt -s nullglob
for pkg_dir in "$RESERVE"/*/; do
  [[ -f "${pkg_dir}package.json" ]] || continue
  publish_one "$pkg_dir" || exit 1
done

[[ -n "$NPMRC_PUBLISH" ]] && rm -f "$NPMRC_PUBLISH"
echo "Done — npm placeholders"
