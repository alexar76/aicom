#!/usr/bin/env bash
# Link the in-repo @aimarket/warden into the consumers that depend on it.
#
#   ./scripts/link_warden_local.sh [--no-build]
#
# WARDEN lives in warden/ and is consumed as a published npm package. Inside the
# monorepo there is nothing to publish yet, so consumers resolve it through a
# symlink in their node_modules — which is git-ignored and never mirrored, so the
# committed package.json stays exactly what a registry install needs.
#
# Run this after `git clone`, after `npm ci` in a consumer (npm ci wipes
# node_modules and takes the symlink with it), and after changing warden/src.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WARDEN="$ROOT/warden"
CONSUMERS=(argus)   # add a directory here when something else depends on the package
BUILD=1

[[ "${1:-}" == "--no-build" ]] && BUILD=0

[[ -f "$WARDEN/package.json" ]] || { echo "error: missing warden/package.json" >&2; exit 2; }

if [[ "$BUILD" -eq 1 ]]; then
  echo "== build @aimarket/warden =="
  cd "$WARDEN"
  [[ -d node_modules ]] || npm install --no-audit --no-fund
  npm run build
fi

[[ -f "$WARDEN/dist/index.js" ]] || {
  echo "error: warden/dist/index.js missing — run without --no-build" >&2; exit 3; }

for consumer in "${CONSUMERS[@]}"; do
  target="$ROOT/$consumer/node_modules/@aimarket/warden"
  mkdir -p "$(dirname "$target")"
  rm -rf "$target"
  # relative link: <consumer>/node_modules/@aimarket/ -> ../../../warden
  ln -s ../../../warden "$target"
  cd "$ROOT/$consumer"
  resolved="$(node --input-type=module -e \
    "import('@aimarket/warden').then(m => console.log(typeof m.Warden === 'function' ? 'ok' : 'broken'))")"
  [[ "$resolved" == "ok" ]] || { echo "error: $consumer cannot resolve @aimarket/warden" >&2; exit 4; }
  echo "linked  $consumer/node_modules/@aimarket/warden -> warden/  ($resolved)"
done

echo
echo "Reminder: the dependency is pinned EXACTLY in argus/package.json. Release order is"
echo "@aimarket/warden first (scripts/publish_warden.sh), then argus — a registry install of"
echo "argus cannot resolve a version of the firewall that was never published."
