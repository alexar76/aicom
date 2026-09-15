#!/usr/bin/env bash
# Sync aimarket-widget from monorepo to a standalone git checkout (e.g. alexar76/aimarket-widget).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/aimarket-widget"
DEST="${1:?Usage: $0 /path/to/aimarket-widget-clone}"

FILES=(
  LICENSE
  README.md
  SECURITY.md
  CONTRIBUTING.md
  CONTRIBUTORS.md
  widget.js
  themes.css
  demo.html
  live-stream.html
)

for f in "${FILES[@]}"; do
  cp "$SRC/$f" "$DEST/$f"
done

if [[ -d "$SRC/docs" ]]; then
  mkdir -p "$DEST/docs"
  cp -r "$SRC/docs/." "$DEST/docs/"
fi

echo "Synced ${#FILES[@]} root files (+ docs/) to $DEST"
echo "Next: cd $DEST && git add -A && git commit -m 'Add MIT license and governance docs' && git push"
