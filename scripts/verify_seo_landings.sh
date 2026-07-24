#!/usr/bin/env bash
# Verify SEO landings build — local smoke (no network).
#
#   ./scripts/verify_seo_landings.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BASE="${SEO_BASE_URL:-https://modeldev.modelmarket.dev}"
echo "=== verify_seo_landings (base=${BASE}) ==="

python3 scripts/build_seo_landings.py --base-url "${BASE}"

fail=0
check() {
  local f="$1"
  if [[ ! -f "$f" ]]; then
    echo "MISSING: $f" >&2
    fail=1
  fi
}

check ecosystem-landing/sitemap.xml
check ecosystem-landing/robots.txt
check ecosystem-landing/shared/seo.css
check ecosystem-landing/learn/index.html
check ecosystem-landing/oracles/index.html
check ecosystem-landing/guides/index.html
check ecosystem-landing/encyclopedia/index.html
check ecosystem-landing/oracles/platon/index.html
check ecosystem-landing/guides/call-verifiable-oracle/index.html
check ecosystem-landing/learn/orchestration-course/index.html

if ! grep -q "${BASE}/sitemap.xml" ecosystem-landing/robots.txt; then
  echo "FAIL: robots.txt missing sitemap for ${BASE}" >&2
  fail=1
fi

if ! grep -q 'application/ld+json' ecosystem-landing/oracles/platon/index.html; then
  echo "FAIL: platon page missing JSON-LD" >&2
  fail=1
fi

if ! grep -q 'rel="canonical"' ecosystem-landing/learn/index.html; then
  echo "FAIL: learn hub missing canonical" >&2
  fail=1
fi

oracle_count="$(find ecosystem-landing/oracles -mindepth 2 -maxdepth 2 -name index.html | wc -l | tr -d ' ')"
if [[ "$oracle_count" -lt 17 ]]; then
  echo "FAIL: expected 17 oracle pages, got ${oracle_count}" >&2
  fail=1
fi

course_count="$(find ecosystem-landing/learn -mindepth 2 -maxdepth 2 -name index.html | wc -l | tr -d ' ')"
if [[ "$course_count" -lt 10 ]]; then
  echo "FAIL: expected 10 course pages, got ${course_count}" >&2
  fail=1
fi

if [[ "$fail" -ne 0 ]]; then
  exit 1
fi

echo "OK: SEO landings verified (${oracle_count} oracles, ${course_count} courses)"
