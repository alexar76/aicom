#!/usr/bin/env bash
# Install optional CPU text-to-image stack (torch CPU + diffusers).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PY="${PYTHON:-python3}"
VENV="${AICOM_VENV:-$ROOT/venv-local-image}"
export HF_HOME="${HF_HOME:-$ROOT/data/.cache/huggingface}"
export TRANSFORMERS_CACHE="${TRANSFORMERS_CACHE:-$HF_HOME/hub}"
mkdir -p "$HF_HOME"

if [[ ! -d "$VENV" ]]; then
  "$PY" -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"

pip install -U pip wheel
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements-local-image.txt

echo "OK — local image venv: $VENV"
echo "HF cache (gitignored): $HF_HOME"
echo "Start server: HF_HOME=$HF_HOME $VENV/bin/python scripts/local_image_server.py"
echo "Set dioscuri content.images.aiProvider=local"
