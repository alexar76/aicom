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

# Encyclopedia locale HTML is generated (gitignored) — same gate as
# .github/workflows/pages-ecosystem.yml. Without this, a host deploy that only
# copies docs/encyclopedia/ ships missing ru/es/en and nginx SPA fallback
# (try_files … /index.html) silently serves the landing page at
# /encyclopedia/ru/ etc.
if [[ -f "$ROOT/docs/encyclopedia/scripts/generate-encyclopedia.mjs" ]]; then
  if command -v node >/dev/null 2>&1; then
    echo "Rendering encyclopedia HTML (en/ru/es/fr/zh) ..."
    (cd "$ROOT/docs/encyclopedia" && node scripts/generate-encyclopedia.mjs all)
    for l in en ru es fr zh; do
      if [[ ! -s "$ROOT/docs/encyclopedia/$l/index.html" ]]; then
        echo "FAIL: docs/encyclopedia/$l/index.html missing after generate" >&2
        exit 1
      fi
    done
  else
    echo "FAIL: node required to render docs/encyclopedia/*/index.html before deploy" >&2
    exit 1
  fi
fi

python3 scripts/build_seo_landings.py --base-url "${SEO_BASE_URL}"

# school/ is the aimarket-school satellite — absent on the trimmed factory tree.
# SEO /learn/ must still build from seo-landings/data/courses.yaml alone.
if [[ -f "$ROOT/school/build.py" ]]; then
  python3 school/build.py
else
  echo "skip school/build.py (not in this tree — aimarket-school satellite)"
fi

if [[ ! -f "$ROOT/ecosystem-landing/learn/index.html" ]]; then
  echo "FAIL: ecosystem-landing/learn/index.html missing after SEO build" >&2
  echo "      Ensure seo-landings/data/courses.yaml (or courses/) is present." >&2
  exit 1
fi

echo "OK: ecosystem-landing ready ($(find ecosystem-landing -name 'index.html' | wc -l | tr -d ' ') index pages)"
