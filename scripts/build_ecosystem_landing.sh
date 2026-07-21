#!/usr/bin/env bash
# Build ecosystem-landing/ static tree (main page + SEO landings).
#
#   ./scripts/build_ecosystem_landing.sh
#   SEO_BASE_URL=https://alexar76.github.io/aicom ./scripts/build_ecosystem_landing.sh
#
# Always run before deploy_ecosystem_landing.sh or GitHub Pages workflow.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export SEO_BASE_URL="${SEO_BASE_URL:-https://modeldev.modelmarket.dev}"

echo "=== Build ecosystem landing (base=${SEO_BASE_URL}) ==="
python3 scripts/build_seo_landings.py --base-url "${SEO_BASE_URL}"
echo "OK: ecosystem-landing ready ($(find ecosystem-landing -name 'index.html' | wc -l | tr -d ' ') index pages)"
