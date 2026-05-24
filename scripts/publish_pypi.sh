#!/usr/bin/env bash
# Publish a Python package from the monorepo (or satellite path) to PyPI.
#
# Usage:
#   PYPI_API_TOKEN=pypi-xxx ./scripts/publish_pypi.sh aimarket-agent
#   ./scripts/publish_pypi.sh aimarket-agent --dry-run
#   ./scripts/publish_pypi.sh aimarket-agent --testpypi
#
# Requires: python3 -m pip install build twine
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PKG="${1:-}"
DRY_RUN=0
TEST_PYPI=0

usage() {
  cat <<'EOF'
publish_pypi.sh — build and upload a package to PyPI

  PYPI_API_TOKEN=pypi-... ./scripts/publish_pypi.sh <package-dir>

  <package-dir>  Path under monorepo root (e.g. aimarket-agent, aimarket-hub)

Options:
  --dry-run     Build + twine check only
  --testpypi    Upload to https://test.pypi.org (token from TESTPYPI_API_TOKEN)
  -h, --help    This help

First-time setup:
  1. Create account: https://pypi.org/account/register/
  2. Enable 2FA (required for new projects)
  3. Create API token: https://pypi.org/manage/account/token/
     Scope: "Entire account" (first upload) or project aimarket-agent
  4. export PYPI_API_TOKEN=pypi-...
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --testpypi) TEST_PYPI=1; shift ;;
    -h|--help) usage; exit 0 ;;
    -*) echo "unknown option: $1" >&2; usage; exit 1 ;;
    *) PKG="$1"; shift ;;
  esac
done

[[ -n "$PKG" ]] || { usage; exit 1; }
[[ -f "$ROOT/$PKG/pyproject.toml" ]] || {
  echo "error: no pyproject.toml at $ROOT/$PKG/" >&2
  exit 2
}

python3 -m pip install --quiet --upgrade pip build twine

echo "== Build $PKG =="
cd "$ROOT/$PKG"
rm -rf dist build *.egg-info
python3 -m build
python3 -m twine check dist/*

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "OK dry-run — dist/ ready:"
  ls -la dist/
  exit 0
fi

if [[ "$TEST_PYPI" -eq 1 ]]; then
  TOKEN="${TESTPYPI_API_TOKEN:-${PYPI_API_TOKEN:-}}"
  REPO="testpypi"
  URL="https://test.pypi.org/legacy/"
else
  TOKEN="${PYPI_API_TOKEN:-}"
  REPO="pypi"
  URL="https://upload.pypi.org/legacy/"
fi

[[ -n "$TOKEN" ]] || {
  echo "error: set PYPI_API_TOKEN (or TESTPYPI_API_TOKEN for --testpypi)" >&2
  exit 3
}

echo "== Upload to $REPO =="
TWINE_USERNAME=__token__ TWINE_PASSWORD="$TOKEN" \
  python3 -m twine upload --repository-url "$URL" dist/*

echo "OK published $(basename "$PKG") to $REPO"
if [[ "$REPO" == "pypi" ]]; then
  echo "Install: pip install aimarket-agent"
fi
