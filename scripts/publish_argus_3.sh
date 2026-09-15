#!/usr/bin/env bash
# Publish unscoped argus-3 to npm (alias tarball — same CLI `argus` as @alexar76/argus3).
#
# Note: npm blocks bare `argus3` (too similar to this package). Use argus-3.
#
#   NPM_TOKEN=npm_... ./scripts/publish_argus_3.sh
#   ./scripts/publish_argus_3.sh --dry-run
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARGUS="$ROOT/argus"
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

[[ -f "$ARGUS/package.json" ]] || { echo "error: missing argus/package.json" >&2; exit 2; }

VERSION="$(node -p "require('$ARGUS/package.json').version")"
BACKUP="$(mktemp "${TMPDIR:-/tmp}/argus-pkg.XXXXXX.json")"
trap '[[ -f "$BACKUP" ]] && cp "$BACKUP" "$ARGUS/package.json"; rm -f "$BACKUP"' EXIT

cp "$ARGUS/package.json" "$BACKUP"

node -e "
const fs = require('fs');
const path = process.argv[1];
const version = process.argv[2];
const pkg = JSON.parse(fs.readFileSync(path, 'utf8'));
pkg.name = 'argus-3';
pkg.version = version;
pkg.description =
  'ARGUS-3 — MCP security firewall (WARDEN) + frugal personal AI agent. Wallet and on-chain economy optional; crypto OFF by default.';
const extra = ['argus-3', 'argus3', 'argus', 'mcp', 'warden', 'ai-agent'];
pkg.keywords = [...new Set([...(pkg.keywords || []), ...extra])];
fs.writeFileSync(path, JSON.stringify(pkg, null, 2) + '\n');
console.log('argus-3@' + version);
" "$ARGUS/package.json" "$VERSION"

if npm view "argus-3@${VERSION}" version >/dev/null 2>&1; then
  echo "SKIP  argus-3@${VERSION} (already on npm)"
  exit 0
fi

echo "== Build & test argus-3 =="
cd "$ARGUS"
npm ci
npm run build
npm test

if [[ "$DRY_RUN" -eq 1 ]]; then
  npm publish --dry-run --access public
  exit 0
fi

TOKEN="${NPM_TOKEN:-${NODE_AUTH_TOKEN:-}}"
[[ -n "$TOKEN" ]] || { echo "error: set NPM_TOKEN" >&2; exit 3; }

NPMRC="$(mktemp "${TMPDIR:-/tmp}/npmrc.argus3.XXXXXX")"
printf '//registry.npmjs.org/:_authToken=%s\n' "$TOKEN" > "$NPMRC"
npm --userconfig "$NPMRC" publish --access public
rm -f "$NPMRC"

echo "OK published argus-3@${VERSION}"
echo "Install: npm install -g argus-3"
