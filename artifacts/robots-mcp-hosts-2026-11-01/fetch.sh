#!/usr/bin/env bash
# Fetch /robots.txt once per host of the ScraperWatch MCP panel (panel.txt, 2,995 endpoints, 2,338 hosts).
# One GET per host, redirects followed (RFC 9309 §2.3.1.2: at least five hops), 10 s limit, 16 at a time.
# Output: raw/<host>.txt (body, first 512 KiB) and raw/<host>.meta (status code, final URL, content type).
set -euo pipefail
cd "$(dirname "$0")"
if [[ "${1:-}" == one ]]; then
  h="$2"
  curl -s -L --max-redirs 5 --max-time 10 -r 0-524287 \
    -A 'HISTOR-robots-survey/2026-11-01 (+https://histor.modelmarket.dev/)' \
    -o "raw/$h.txt" -w '%{http_code} %{url_effective} %{content_type}\n' "https://$h/robots.txt" > "raw/$h.meta" 2>/dev/null \
    || echo "000 - -" > "raw/$h.meta"
  exit 0
fi
grep '^http' panel.txt | sed -E 's#^https?://([^/]+).*#\1#' | tr 'A-Z' 'a-z' | sort -u > hosts.txt
xargs -P 16 -n 1 ./fetch.sh one < hosts.txt
wc -l < hosts.txt
