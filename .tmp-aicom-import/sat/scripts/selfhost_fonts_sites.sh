#!/usr/bin/env bash
# Take every site in this monorepo off fonts.googleapis.com, in one pass.
#
# Re-runnable: already-mirrored faces come from the pool in assets/webfonts/ without a
# network fetch, and a page with no Google <link> left is reported as such and skipped. Run
# it again after any generator adds a new page.
#
# The layout differs by how a site is built, which is the only reason this file exists
# rather than a single loop:
#
#   vite apps    fonts go in public/, linked absolutely as /fonts/fonts.css. Vite copies
#                public/ into dist/ byte for byte and leaves absolute URLs alone, whereas a
#                relative href would be pulled into the bundle graph and emitted under a
#                content hash — working, but harder to reason about when a font 404s.
#   static sites fonts sit next to the page and are linked relatively, so the site keeps
#                working whether it is served at a domain root or under a path prefix.
#   locale trees one copy at the site root shared by every locale, hrefs computed per page.
#                ecosystem-landing alone would otherwise carry 72 copies of the same faces.
set -euo pipefail
cd "$(dirname "$0")/.."
GF=scripts/selfhost_google_fonts.py

echo "=== vite apps (public/ + absolute href) ==="
for proj in \
  pantheon \
  alien-monitor/frontend \
  ai-service-mesh/frontend \
  logos/frontend \
  platon/frontend \
  oracles/oracles/platon/frontend \
  apps/pulse-terminal \
  independent/daily-card/apps/web \
; do
  [ -f "$proj/index.html" ] || { echo "  skip $proj (no index.html)"; continue; }
  python3 "$GF" --dest "$proj/public" --href /fonts/fonts.css --rewrite "$proj/index.html"
done

# Emberline serves a second page from inside public/; same origin, so the same absolute href.
python3 "$GF" --dest cite-desks/emberline/frontend/public \
  --href /fonts/fonts.css \
  --rewrite cite-desks/emberline/frontend/index.html \
  --rewrite cite-desks/emberline/frontend/public/docs/enterprise/index.html

echo
echo "=== static sites (fonts beside the page, relative href) ==="
# Only directories a web server serves as-is. A page an APP serves is not one: the hub's
# landing got a copy beside terminal-home.html that no route served (404 on every hub); it
# links the bundle the hub mounts, aimarket_hub/assets/fonts, as assets/fonts/fonts.css.
#
# Grouped by directory: pages sharing a directory share one fonts.css, so a directory with
# two pages asking for different weights gets the union rather than one overwriting the other.
for dir in \
  aicom-landing/public \
  aicom-landing/docs/examples \
  aimarket-bridges/docs \
  aimarket-playground/docs/landing \
  aimarket-widget \
  atlas/atlas/_static \
  atlas/docs/landing \
  atlas/frontend/public \
  basanos/docs/landing \
  basanos/frontend \
  cite-desks/kernel/web \
  create-aimarket-agent/docs/landing \
  dioscuri/landing \
  dolos/docs/landing \
  gaia/docs/landing \
  helios \
  helios/landing \
  hephaestus/docs/landing \
  logos/docs/landing \
  lottery/frontend \
  momus/docs/landing \
  scripts/github-io \
  signal-hunt/docs/landing \
  skopos/docs/landing \
  themis/docs/landing \
  themis/docs/landing/console \
  themis/ui \
  theoros/landing \
  treasury/docs/landing \
  use-cases-portal \
  use-cases-portal/docs/landing \
  ai-service-mesh/landing \
; do
  pages=()
  for page in "$dir"/*.html; do
    [ -f "$page" ] && grep -q "fonts\.googleapis\.com" "$page" && pages+=(--rewrite "$page")
  done
  [ ${#pages[@]} -gt 0 ] || { echo "  clean $dir"; continue; }
  python3 "$GF" --dest "$dir" --href fonts/fonts.css "${pages[@]}"
done

echo
echo "=== ecosystem-landing (one copy at the site root, 5 locales) ==="
pages=()
while IFS= read -r page; do
  pages+=(--rewrite "$page")
done < <(grep -rl "fonts\.googleapis\.com" ecosystem-landing --include='*.html' | sort)
if [ ${#pages[@]} -gt 0 ]; then
  python3 "$GF" --dest ecosystem-landing --relative "${pages[@]}"
else
  echo "  clean"
fi

echo
echo "=== remaining Google Fonts references in markup ==="
grep -rn "fonts\.googleapis\.com" --include='*.html' . \
  --exclude-dir=node_modules --exclude-dir=dist --exclude-dir=.next || echo "  none"
