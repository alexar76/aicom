#!/usr/bin/env bash
# Register one Hub peer on an upstream Hub: announce → approve(trusted) → crawl.
# Generic (any Hub). For Signal Hunt tool verification use:
#   signal-hunt/scripts/register-upstream.sh
#
# Usage:
#   UPSTREAM_ADMIN_TOKEN=… ./scripts/register_hub_upstream.sh \
#     https://new-hub.example https://modelmarket.dev
set -euo pipefail

NEW_HUB="${1:-}"
UPSTREAM_HUB="${2:-https://modelmarket.dev}"
: "${NEW_HUB:?Usage: register_hub_upstream.sh <new-hub-url> [upstream-hub-url]}"
: "${UPSTREAM_ADMIN_TOKEN:?Set UPSTREAM_ADMIN_TOKEN for this one process only}"

NEW_HUB="${NEW_HUB%/}"
UPSTREAM_HUB="${UPSTREAM_HUB%/}"

WK="$(curl -fsS "$NEW_HUB/.well-known/ai-market.json")"
python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("signer_public_key"); assert d.get("manifest_url")' <<<"$WK"

ANNOUNCE="$(python3 -c '
import json,sys
d=json.load(sys.stdin)
base=sys.argv[1]
print(json.dumps({
  "hub_url": base,
  "well_known_url": base+"/.well-known/ai-market.json",
  "capabilities_count": int(d.get("capabilities_count",0) or 0),
  "hub_name": d.get("name", base),
  "signer_public_key": d["signer_public_key"],
}))
' "$NEW_HUB" <<<"$WK")"

AUTH="Authorization: Bearer ${UPSTREAM_ADMIN_TOKEN}"
echo "announce $NEW_HUB → $UPSTREAM_HUB"
curl -fsS -X POST -H "$AUTH" -H "Content-Type: application/json" \
  -d "$ANNOUNCE" "$UPSTREAM_HUB/ai-market/v2/federation/announce" >/dev/null
curl -fsS -X POST -H "$AUTH" -H "Content-Type: application/json" \
  -d "{\"url\":\"$NEW_HUB\",\"trusted\":true}" \
  "$UPSTREAM_HUB/ai-market/v2/federation/peers/approve" >/dev/null
curl -fsS -X POST -H "$AUTH" \
  "$UPSTREAM_HUB/ai-market/v2/federation/crawl" >/dev/null

python3 - "$NEW_HUB" "$UPSTREAM_HUB" <<'PY'
import json,sys,urllib.request
new,upstream=sys.argv[1:]
with urllib.request.urlopen(upstream + "/ai-market/v2/federation/peers", timeout=30) as r:
    data=json.load(r)
peers=data.get("peers") or data.get("items") or (data if isinstance(data, list) else [])
hit=any(new.rstrip("/") in json.dumps(p) for p in peers)
if not hit:
    raise SystemExit(f"peer not listed on upstream after crawl: {new}")
print(json.dumps({"upstream":upstream,"peer":new,"peers":len(peers),"status":"registered"},indent=2))
PY
