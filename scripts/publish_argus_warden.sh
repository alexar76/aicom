#!/usr/bin/env bash
# Publish unscoped argus-warden to npm (alias tarball — same CLI `argus` as @alexar76/argus3).
#
#   NPM_TOKEN=npm_... ./scripts/publish_argus_warden.sh
#   ./scripts/publish_argus_warden.sh --dry-run
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
pkg.name = 'argus-warden';
pkg.version = version;
pkg.description =
  'WARDEN MCP firewall — blocks poisoned MCP servers before any tool runs. ARGUS-3 agent CLI (argus); wallet and crypto optional.';
const extra = ['mcp', 'mcp-security', 'prompt-injection', 'warden', 'firewall', 'argus-warden'];
pkg.keywords = [...new Set([...(pkg.keywords || []), ...extra])];
fs.writeFileSync(path, JSON.stringify(pkg, null, 2) + '\n');
console.log('argus-warden@' + version);
" "$ARGUS/package.json" "$VERSION"

echo "== Build & test argus-warden =="
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

NPMRC="$(mktemp "${TMPDIR:-/tmp}/npmrc.warden.XXXXXX")"
printf '//registry.npmjs.org/:_authToken=%s\n' "$TOKEN" > "$NPMRC"
npm --userconfig "$NPMRC" publish --access public
rm -f "$NPMRC"

echo "OK published argus-warden@${VERSION}"
echo "Install: npm install -g argus-warden"
