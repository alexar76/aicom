#!/usr/bin/env bash
# Check markdown links in factory docs + optional live HTTP on GitHub URLs.
#
# Usage:
#   ./scripts/verify_whitepaper_links.sh
#   ./scripts/verify_whitepaper_links.sh --all        # entire monorepo .md audit
#   ./scripts/verify_whitepaper_links.sh --live       # HTTP check on github.com URLs in whitepaper
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LIVE=0
SCOPE="docs"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --live) LIVE=1; shift ;;
    --all) SCOPE="all"; shift ;;
    -h|--help)
      sed -n '1,10p' "$0"
      exit 0
      ;;
    *) echo "unknown: $1" >&2; exit 1 ;;
  esac
done

AUDIT=(python3 "${ROOT}/scripts/audit_satellite_md_links.py")
if [[ "$SCOPE" == "docs" ]]; then
  AUDIT+=(--docs-only)
fi

echo "=== Satellite link audit ($SCOPE) ==="
"${AUDIT[@]}"
FAIL=$?

if [[ "$LIVE" -eq 1 ]]; then
  echo ""
  echo "=== Live HTTP check (github.com) ==="
  WP="${ROOT}/docs/ecosystem/whitepaper"
  # bash 3.2 (macOS) has no `mapfile`; this audit is run from the laptop.
  URLS=()
  while IFS= read -r _u; do [[ -n "$_u" ]] && URLS+=("$_u"); done \
    < <(grep -ohE 'https://github.com/[^)]+' "$WP"/*.md | sort -u)
  for url in "${URLS[@]}"; do
    code="$(curl -fsSL -o /dev/null -w '%{http_code}' --max-time 25 "$url" 2>/dev/null || echo "000")"
    if [[ "$code" =~ ^(200|301|302)$ ]]; then
      echo "OK   ($code) $url"
    else
      echo "FAIL ($code) $url"
      FAIL=1
    fi
  done
fi

if [[ "$FAIL" -eq 0 ]]; then
  echo ""
  echo "All link checks passed."
  exit 0
fi
echo ""
echo "Link check FAILED."
exit 1
