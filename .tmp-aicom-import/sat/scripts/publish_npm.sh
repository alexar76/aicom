#!/usr/bin/env bash
# Publish an npm package from the monorepo (or satellite path).
#
# Usage:
#   NPM_TOKEN=npm_xxx ./scripts/publish_npm.sh argus
#   ./scripts/publish_npm.sh argus --dry-run
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PKG_DIR="${1:-}"
DRY_RUN=0

usage() {
  cat <<'EOF'
publish_npm.sh — build and publish an npm package

  NPM_TOKEN=npm_... ./scripts/publish_npm.sh <package-dir>

  <package-dir>  Path under monorepo root (e.g. argus)

Options:
  --dry-run   npm publish --dry-run (no upload)
  -h, --help  This help

First-time setup:
  1. Create npm account + enable 2FA
  2. Use org "aimarket" on npm (scope @aimarket) — @aicom is unavailable
  3. Add your user to the org with read-write / publish on @aimarket/*
  4. Create granular token: read-write on @aimarket, enable "Bypass 2FA for automation"
  5. export NPM_TOKEN=npm_...
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    -*) echo "unknown option: $1" >&2; usage; exit 1 ;;
    *) PKG_DIR="$1"; shift ;;
  esac
done

[[ -n "$PKG_DIR" ]] || { usage; exit 1; }
[[ -f "$ROOT/$PKG_DIR/package.json" ]] || {
  echo "error: no package.json at $ROOT/$PKG_DIR/" >&2
  exit 2
}

cd "$ROOT/$PKG_DIR"
NAME="$(node -p "require('./package.json').name")"
VERSION="$(node -p "require('./package.json').version")"

echo "== Build $NAME@$VERSION =="
npm ci
npm run build
npm test

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "== Dry-run publish =="
  npm publish --dry-run --access public
  exit 0
fi

TOKEN="${NPM_TOKEN:-${NODE_AUTH_TOKEN:-}}"
[[ -n "$TOKEN" ]] || {
  echo "error: set NPM_TOKEN (or NODE_AUTH_TOKEN)" >&2
  exit 3
}
export NODE_AUTH_TOKEN="$TOKEN"
NPMRC_PUBLISH="$(mktemp "${TMPDIR:-/tmp}/npmrc.publish.XXXXXX")"
trap 'rm -f "$NPMRC_PUBLISH"' EXIT
printf '//registry.npmjs.org/:_authToken=%s\n' "$TOKEN" > "$NPMRC_PUBLISH"
export NPM_CONFIG_USERCONFIG="$NPMRC_PUBLISH"
NPM_USERCONFIG=(--userconfig "$NPMRC_PUBLISH")

echo "== Publish $NAME@$VERSION to npm =="
npm "${NPM_USERCONFIG[@]}" whoami || {
  echo "error: npm token invalid or expired (npm whoami failed)" >&2
  echo "hint: create granular token with read-write on @aimarket + bypass 2FA" >&2
  exit 4
}
npm "${NPM_USERCONFIG[@]}" publish --access public

echo "OK published $NAME@$VERSION"
echo "Install: npm install $NAME"
