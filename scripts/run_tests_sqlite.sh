#!/usr/bin/env bash
# Run pytest with USE_SQLITE=true using a project-local venv (aiosqlite + full requirements).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$ROOT/.venv"
PY="$VENV/bin/python"

if [[ ! -x "$PY" ]]; then
  echo "Creating .venv and installing requirements.txt …"
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q --upgrade pip
  "$VENV/bin/pip" install -q -r "$ROOT/requirements.txt"
fi

# Ensure SQLite async driver is present (common local miss when not using Docker).
if ! "$PY" -c "import aiosqlite" 2>/dev/null; then
  echo "Installing aiosqlite into .venv …"
  "$VENV/bin/pip" install -q 'aiosqlite==0.20.0'
fi

export USE_SQLITE=true
cd "$ROOT"
exec "$PY" -m pytest "$@"
