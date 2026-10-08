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
TODAY=$(cat "$STATE" 2>/dev/null || echo 0)
# Everything the hub answered stays DATA: it reaches Python through the environment and stdin,
# never through the program text. Interpolating it into `python3 -c` made the hub's JSON code
# that this root timer ran on the host — a hub compromise became host root.
DECISION=$(printf '%s' "$ACCOUNT" | BELOW="$BELOW" AMOUNT="$AMOUNT" CAP="$CAP" TODAY="$TODAY" python3 -c '
import json, math, os, re, sys
a = json.load(sys.stdin)
acct, bal = a.get("account_id"), a.get("balance_usd")
if not isinstance(acct, str) or not re.fullmatch(r"acct_[A-Za-z0-9_-]{1,64}", acct):
    sys.exit("refusing: the hub returned an account id that is not one")
if isinstance(bal, bool) or not isinstance(bal, (int, float)) or not math.isfinite(bal):
    sys.exit("refusing: the hub returned a balance that is not a number")
below, amount, cap = (float(os.environ[k]) for k in ("BELOW", "AMOUNT", "CAP"))
try:
    today = float(os.environ["TODAY"])
except ValueError:
    today = cap  # an unreadable ledger of grants counts as a spent day
if bal >= below:
    print("skip", acct, bal, today)
elif today + amount > cap:
    print("cap", acct, bal, today)
else:
    print("grant", acct, bal, today + amount)
')
set -- $DECISION
VERDICT=$1; ACCT=$2; BAL=$3; AFTER=$4
case "$VERDICT" in
  skip) echo "balance \$$BAL >= \$$BELOW: nothing to do"; exit 0 ;;
  cap)  echo "REFUSED: balance \$$BAL, but today's grants (\$$AFTER) would pass the \$$CAP daily cap" >&2; exit 2 ;;
  grant) : ;;
  *) echo "REFUSED: no decision" >&2; exit 2 ;;
esac
docker exec -e ACCT="$ACCT" -e AMOUNT="$AMOUNT" "$HUB_CONTAINER" python -c '
import json, os, urllib.parse, urllib.request
acct = urllib.parse.quote(os.environ["ACCT"], safe="")
req = urllib.request.Request(f"http://127.0.0.1:9083/ai-market/v2/accounts/{acct}/credit", method="POST",
    data=json.dumps({"amount_usd": float(os.environ["AMOUNT"]), "note": "auto top-up: okx-a2mcp relay below threshold"}).encode(),
    headers={"content-type": "application/json", "authorization": "Bearer " + os.environ["AIMARKET_ADMIN_TOKEN"]})
r = json.load(urllib.request.urlopen(req, timeout=15))
print("granted", os.environ["AMOUNT"], "ok" if r.get("success") else r)
'
printf '%s\n' "$AFTER" > "$STATE"
echo "balance was \$$BAL; granted \$$AMOUNT (today \$$AFTER of \$$CAP)"
