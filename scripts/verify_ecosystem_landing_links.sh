#!/usr/bin/env bash
# Verify ecosystem landing GitHub project links (local file or live Pages URL).
#
# Usage:
#   ./scripts/verify_ecosystem_landing_links.sh
#   ./scripts/verify_ecosystem_landing_links.sh --live https://modeldev.modelmarket.dev
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HTML="${ROOT}/ecosystem-landing/index.html"
LIVE_URL=""
OFFLINE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --live) LIVE_URL="${2:-}"; shift 2 ;;
    --offline) OFFLINE=1; shift ;;
    -h|--help)
      sed -n '1,12p' "$0"
      exit 0
      ;;
    *) echo "unknown: $1" >&2; exit 1 ;;
  esac
done

if [[ -n "$LIVE_URL" ]]; then
  HTML="$(mktemp)"
  trap 'rm -f "$HTML"' EXIT
  curl -fsSL "$LIVE_URL" -o "$HTML"
  echo "Fetched: $LIVE_URL"
fi

if [[ ! -f "$HTML" ]]; then
  echo "missing HTML: $HTML" >&2
  exit 1
fi

# Extract github.com links from project cards (grep is enough for this static page).
LINKS=()
while IFS= read -r line; do
  LINKS+=("$line")
done < <(grep -oE 'https://github.com/[^"<> ]+' "$HTML" | sort -u)

if [[ ${#LINKS[@]} -eq 0 ]]; then
  echo "No GitHub links found in $HTML" >&2
  exit 1
fi

echo "Checking ${#LINKS[@]} unique GitHub URLs..."
FAIL=0
BROKEN_SUBPATH=0

for url in "${LINKS[@]}"; do
  if [[ "$url" =~ aicom/tree/main/(aimarket-hub|aimarket-protocol|alien-monitor|acex|aimarket-widget|aimarket-sdks|desktop-integrations|plugins) ]]; then
    echo "FAIL (stale monorepo path): $url"
    BROKEN_SUBPATH=$((BROKEN_SUBPATH + 1))
    FAIL=1
    continue
  fi

  if [[ "$OFFLINE" -eq 1 ]]; then
    echo "SKIP (offline) $url"
    continue
  fi

  fetch_url="${url%%#*}"
  code="$(curl -fsSL -o /dev/null -w '%{http_code}' --max-time 20 "$fetch_url" 2>/dev/null || echo "000")"
  if [[ "$code" =~ ^(200|301|302)$ ]]; then
    echo "OK   ($code) $url"
  else
    echo "FAIL ($code) $url"
    FAIL=1
  fi
done

if [[ "$BROKEN_SUBPATH" -gt 0 ]]; then
  echo ""
  echo "Found $BROKEN_SUBPATH stale aicom/tree/main/<satellite> links — run landing fix commit."
fi

if [[ "$FAIL" -eq 0 ]]; then
  echo ""
  echo "All checks passed."
  exit 0
fi

echo ""
echo "Some checks failed."
exit 1
