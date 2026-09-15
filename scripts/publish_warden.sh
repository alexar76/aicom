#!/usr/bin/env bash
# Publish @aimarket/warden (the standalone WARDEN MCP firewall) to npm.
#
#   NPM_TOKEN=npm_... ./scripts/publish_warden.sh
#   ./scripts/publish_warden.sh --dry-run
#
# Release order: this package FIRST, then argus. argus pins it exactly, so a
# published argus that names an unpublished firewall version is broken on install.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WARDEN="$ROOT/warden"
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) echo "Usage: NPM_TOKEN=... $0 [--dry-run]"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 1 ;;
  esac
done

[[ -f "$WARDEN/package.json" ]] || { echo "error: missing warden/package.json" >&2; exit 2; }
cd "$WARDEN"

NAME="$(node -p "require('./package.json').name")"
VERSION="$(node -p "require('./package.json').version")"
echo "== $NAME@$VERSION =="

# The zero-dependency claim is the reason this package exists; refuse to publish
# a tarball that contradicts it, whatever the tests said at some earlier commit.
node -e "
const p = require('./package.json');
const deps = Object.keys(p.dependencies || {});
const peers = Object.keys(p.peerDependencies || {});
if (deps.length || peers.length) {
  console.error('refusing to publish: runtime dependencies present ->', [...deps, ...peers].join(', '));
  process.exit(1);
}
"

if npm view "$NAME@$VERSION" version >/dev/null 2>&1; then
  echo "error: $NAME@$VERSION is already on npm — bump the version in warden/package.json" >&2
  exit 3
fi

echo "== install, typecheck, build, test =="
npm ci 2>/dev/null || npm install --no-audit --no-fund
npm run typecheck
npm run build
npm test

# Regenerate the badges so a release never ships a stale test count.
node scripts/make-badges.mjs

if [[ "$DRY_RUN" -eq 1 ]]; then
  npm publish --dry-run --access public
  exit 0
fi

TOKEN="${NPM_TOKEN:-${NODE_AUTH_TOKEN:-}}"
[[ -n "$TOKEN" ]] || { echo "error: set NPM_TOKEN" >&2; exit 4; }

NPMRC="$(mktemp "${TMPDIR:-/tmp}/npmrc.aimarket-warden.XXXXXX")"
trap 'rm -f "$NPMRC"' EXIT
printf '//registry.npmjs.org/:_authToken=%s\n' "$TOKEN" > "$NPMRC"
npm --userconfig "$NPMRC" publish --access public

echo "OK published $NAME@$VERSION"
echo "Install: npm install $NAME"
echo "Next: publish/mirror argus, which pins $NAME@$VERSION exactly."
