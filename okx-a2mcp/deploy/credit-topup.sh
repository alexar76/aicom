#!/bin/sh
# Keep the gateway's hub credit account funded (okx-a2mcp/src/hub.js buys hub capabilities with it).
#
# Runs on the apex host from okx-a2mcp-credit-topup.timer. Reads the balance with the gateway's own
# key; below TOPUP_BELOW_USD it grants TOPUP_AMOUNT_USD through the hub's operator endpoint, from
# inside the hub container (the admin token never leaves it). A grant is ledger credit inside the
# hub, not a transfer of money: the providers it pays for are ours.
#
# TOPUP_DAILY_CAP_USD bounds a day's grants, so a buyer flood that drains the account (each paid
# call also paid us in USDC) or a bug cannot mint credit without limit: past the cap it stops and
# says so in the journal.
set -eu
KEY_FILE=${KEY_FILE:-/opt/okx-a2mcp-secrets/hub_api_key}
HUB=${HUB:-http://127.0.0.1:9083}
HUB_CONTAINER=${HUB_CONTAINER:-modelmarket-hub}
BELOW=${TOPUP_BELOW_USD:-1}
AMOUNT=${TOPUP_AMOUNT_USD:-5}
CAP=${TOPUP_DAILY_CAP_USD:-20}
STATE_DIR=${STATE_DIR:-/var/lib/okx-a2mcp-topup}
mkdir -p "$STATE_DIR"
STATE="$STATE_DIR/$(date -u +%F).granted"

read_account() { curl -fsS -m 15 -H "X-API-Key: $(cat "$KEY_FILE")" "$HUB/ai-market/v2/account"; }
ACCOUNT=$(read_account)
ACCT=$(printf '%s' "$ACCOUNT" | python3 -c 'import json,sys; print(json.load(sys.stdin)["account_id"])')
BAL=$(printf '%s' "$ACCOUNT" | python3 -c 'import json,sys; print(json.load(sys.stdin)["balance_usd"])')
if python3 -c "import sys; sys.exit(0 if float('$BAL') < float('$BELOW') else 1)"; then :; else
  echo "balance \$$BAL >= \$$BELOW: nothing to do"; exit 0
fi
TODAY=$(cat "$STATE" 2>/dev/null || echo 0)
if python3 -c "import sys; sys.exit(0 if float('$TODAY') + float('$AMOUNT') <= float('$CAP') else 1)"; then :; else
  echo "REFUSED: balance \$$BAL, but today's grants (\$$TODAY) would pass the \$$CAP daily cap" >&2; exit 2
fi
docker exec -e ACCT="$ACCT" -e AMOUNT="$AMOUNT" "$HUB_CONTAINER" python -c '
import json, os, urllib.request
acct = os.environ["ACCT"]
req = urllib.request.Request(f"http://127.0.0.1:9083/ai-market/v2/accounts/{acct}/credit", method="POST",
    data=json.dumps({"amount_usd": float(os.environ["AMOUNT"]), "note": "auto top-up: okx-a2mcp relay below threshold"}).encode(),
    headers={"content-type": "application/json", "authorization": "Bearer " + os.environ["AIMARKET_ADMIN_TOKEN"]})
r = json.load(urllib.request.urlopen(req, timeout=15))
print("granted", os.environ["AMOUNT"], "ok" if r.get("success") else r)
'
python3 -c "print(float('$TODAY') + float('$AMOUNT'))" > "$STATE"
echo "balance was \$$BAL; granted \$$AMOUNT (today \$$(cat "$STATE") of \$$CAP)"
