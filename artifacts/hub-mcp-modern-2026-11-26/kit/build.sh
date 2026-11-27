#!/usr/bin/env bash
# build.sh CONTAINER — image FROM the running one with this change; refuses when a running file is not
# an expected version, or when the container holds files under /app that its image does not (a change
# another session copied in: rebuilding from the image would drop it).
# mcp_gateway.py: a81bde47a61d = 3.22.0, c78c8d068d88 = hub.modelmarket.dev's Tutu build,
# ca9d61d55fc4 / b5600ddedee0 = the two HALOWERK builds (the second is main before this change).
set -euo pipefail
C="$1"; D="$(cd "$(dirname "$0")" && pwd)"
BASE="$(docker inspect -f '{{.Config.Image}}' "$C")"
h() { docker exec "$C" sha256sum "/app/aimarket_hub/$1" 2>/dev/null | cut -c1-12; }
[[ "$(h hub_routes/ai_catalog.py)" == 1e5fb7d2a40e ]] || { echo "unexpected ai_catalog.py in $C: $(h hub_routes/ai_catalog.py)"; exit 3; }
[[ "$(h static/well-known/mcp/server-card.json)" == b5134a7a40b2 ]] || { echo "unexpected server-card.json in $C"; exit 3; }
[[ -z "$(h mcp_modern.py)" ]] || { echo "$C already has mcp_modern.py"; exit 3; }
case "$(h mcp_gateway.py)" in
  a81bde47a61d) GW=3220 ;; c78c8d068d88) GW=tutu ;; ca9d61d55fc4) GW=halowerk1 ;; b5600ddedee0) GW=main ;;
  *) echo "unknown mcp_gateway.py in $C: $(h mcp_gateway.py)"; exit 3 ;;
esac
# A directory is listed as changed as soon as Python writes a __pycache__ into it; only files count.
copied="$( (docker diff "$C" | grep -E '^[AC] /app/' | grep -vE '__pycache__|\.pyc$' || true) | while read -r kind path; do
  docker exec "$C" test -d "$path" || echo "$kind $path"; done)"
[[ -z "$copied" ]] || { echo "files in $C that its image does not have:"; echo "$copied"; exit 4; }
NEW="${BASE%-httpvalid-20261126}-mcp0728-20261126"
docker build -q --build-arg BASE="$BASE" --build-arg GATEWAY="$GW" -t "$NEW" "$D" >/dev/null
echo "$NEW (gateway $GW)"
