#!/usr/bin/env bash
# Mesh-federate primary ↔ competing lab Hub ↔ Signal Hunt Hub.
#
# Each side: announce → approve(trusted) → crawl. Tokens stay in env (never written).
#
# Required env:
#   PRIMARY_ADMIN_TOKEN  — AIMARKET_ADMIN_TOKEN on https://modelmarket.dev
#   LAB_ADMIN_TOKEN      — Competing Lab Hub admin token
#   HUNT_ADMIN_TOKEN     — Signal Hunt Hub admin token
#
# Optional overrides:
#   PRIMARY_HUB  (default https://modelmarket.dev)
#   LAB_HUB      (default http://hunt.modelmarket.dev:9083)
#   HUNT_HUB     (default https://hunt.modelmarket.dev)
#
# Usage:
#   PRIMARY_ADMIN_TOKEN=… LAB_ADMIN_TOKEN=… HUNT_ADMIN_TOKEN=… \
#     ./scripts/register_federation_mesh.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REGISTER="$ROOT/scripts/register_hub_upstream.sh"
chmod +x "$REGISTER" 2>/dev/null || true

PRIMARY_HUB="${PRIMARY_HUB:-https://modelmarket.dev}"
LAB_HUB="${LAB_HUB:-http://hunt.modelmarket.dev:9083}"
HUNT_HUB="${HUNT_HUB:-https://hunt.modelmarket.dev}"

: "${PRIMARY_ADMIN_TOKEN:?Set PRIMARY_ADMIN_TOKEN}"
: "${LAB_ADMIN_TOKEN:?Set LAB_ADMIN_TOKEN}"
: "${HUNT_ADMIN_TOKEN:?Set HUNT_ADMIN_TOKEN}"

echo "=== primary ← lab + hunt ==="
UPSTREAM_ADMIN_TOKEN="$PRIMARY_ADMIN_TOKEN" "$REGISTER" "$LAB_HUB" "$PRIMARY_HUB"
UPSTREAM_ADMIN_TOKEN="$PRIMARY_ADMIN_TOKEN" "$REGISTER" "$HUNT_HUB" "$PRIMARY_HUB"

echo "=== lab ← primary + hunt ==="
UPSTREAM_ADMIN_TOKEN="$LAB_ADMIN_TOKEN" "$REGISTER" "$PRIMARY_HUB" "$LAB_HUB"
UPSTREAM_ADMIN_TOKEN="$LAB_ADMIN_TOKEN" "$REGISTER" "$HUNT_HUB" "$LAB_HUB"

echo "=== hunt ← primary + lab ==="
UPSTREAM_ADMIN_TOKEN="$HUNT_ADMIN_TOKEN" "$REGISTER" "$PRIMARY_HUB" "$HUNT_HUB"
UPSTREAM_ADMIN_TOKEN="$HUNT_ADMIN_TOKEN" "$REGISTER" "$LAB_HUB" "$HUNT_HUB"

# Second crawl pass after the graph is linked
for pair in \
  "$PRIMARY_ADMIN_TOKEN|$PRIMARY_HUB" \
  "$LAB_ADMIN_TOKEN|$LAB_HUB" \
  "$HUNT_ADMIN_TOKEN|$HUNT_HUB"
do
  token="${pair%%|*}"; hub="${pair##*|}"
  curl -fsS -X POST -H "Authorization: Bearer $token" \
    "$hub/ai-market/v2/federation/crawl" >/dev/null || true
done

python3 - "$PRIMARY_HUB" "$LAB_HUB" "$HUNT_HUB" <<'PY'
import json,sys,urllib.request
names=["primary","lab","hunt"]
bases=sys.argv[1:]
print()
for name,base in zip(names,bases):
    peers=json.load(urllib.request.urlopen(base+"/ai-market/v2/federation/peers",timeout=30))
    plist=peers.get("peers") or peers.get("items") or (peers if isinstance(peers,list) else [])
    man=json.load(urllib.request.urlopen(base+"/ai-market/v2/manifest",timeout=30))
    tools=man.get("tools") or []
    sources={}
    for t in tools:
        s=t.get("source_hub") or "?"
        sources[s]=sources.get(s,0)+1
    print(f"== {name} ({base}) ==")
    print(f"peers={len(plist)} tools={len(tools)}")
    for p in plist:
        print(" -", p.get("name") or p.get("hub_name"), "|", p.get("url") or p.get("hub_url"))
    for s,n in sorted(sources.items(), key=lambda x:-x[1])[:10]:
        print(f"   src {n:3d}  {s}")
    print()
PY
