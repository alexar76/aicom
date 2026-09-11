#!/usr/bin/env bash
# Build Flutter web builds and capture screenshots for all desktop SKUs.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="${FLUTTER_ROOT:-/root/flutter}/bin:$PATH"

PYTHON="${ROOT}/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON=python3
fi

exec "$PYTHON" "$ROOT/scripts/capture_desktop_screenshots.py" "$@"
