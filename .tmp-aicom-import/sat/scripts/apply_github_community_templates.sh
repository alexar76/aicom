#!/usr/bin/env bash
# Copy GitHub Community Standards templates (.github/ISSUE_TEMPLATE, PR template,
# CODE_OF_CONDUCT.md) into the monorepo root and every satellite export root.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$ROOT/scripts/satellite-github-templates/.github"
COC_SRC="$ROOT/scripts/satellite-github-templates/CODE_OF_CONDUCT.md"

if [[ ! -d "$SRC/ISSUE_TEMPLATE" ]]; then
  echo "Missing template source: $SRC" >&2
  exit 1
fi

copy_templates() {
  local target="$1"
  mkdir -p "$target/.github/ISSUE_TEMPLATE"
  cp -R "$SRC/ISSUE_TEMPLATE/." "$target/.github/ISSUE_TEMPLATE/"
  cp "$SRC/pull_request_template.md" "$target/.github/pull_request_template.md"
  cp "$SRC/pull_request_template.md" "$target/pull_request_template.md"
  if [[ -f "$COC_SRC" ]]; then
    cp "$COC_SRC" "$target/CODE_OF_CONDUCT.md"
  elif [[ -f "$ROOT/CODE_OF_CONDUCT.md" ]]; then
    cp "$ROOT/CODE_OF_CONDUCT.md" "$target/CODE_OF_CONDUCT.md"
  fi
  echo "  ✓ $target"
}

echo "Applying GitHub community templates…"
copy_templates "$ROOT"

TARGETS=()
while IFS= read -r line; do
  TARGETS+=("$line")
done < <(python3 - "$ROOT" <<'PY'
import sys
from pathlib import Path
import yaml

root = Path(sys.argv[1])
data = yaml.safe_load((root / "scripts/satellite-map.yaml").read_text())
seen = set()
for sat in data.get("satellites", []):
    layout = sat.get("export_layout") or {}
    root_from = layout.get("root_from")
    if not root_from:
        paths = sat.get("paths") or []
        if len(paths) == 1 and "/" not in paths[0].strip("/"):
            root_from = paths[0]
    if not root_from or root_from in seen:
        continue
    target = root / root_from
    if not target.is_dir():
        continue
    seen.add(root_from)
    print(target)
PY
)

# Monorepo paths that mirror to satellites but lack root_from in satellite-map
EXTRA=(
  "$ROOT/plugins"
  "$ROOT/desktop-integrations"
)

for dir in "${TARGETS[@]}" "${EXTRA[@]}"; do
  [[ -d "$dir" ]] || continue
  copy_templates "$dir"
done

if [[ -d "$ROOT/coach/.github" || -d "$ROOT/coach" ]]; then
  copy_templates "$ROOT/coach"
fi

echo "Done."
