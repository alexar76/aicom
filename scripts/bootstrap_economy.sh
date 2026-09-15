#!/usr/bin/env bash
# Genesis economy bootstrap — the INITIAL token distribution that lets the agent
# economy start turning. Works on any EVM chain (Base Sepolia / Base mainnet) via RPC.
#
# WHY this exists: on Anvil/UNI every account is pre-funded (anvil --balance 1000), so
# agents can buy tickets out of the box. On a REAL chain the deployer holds ALL the funds,
# so nothing can move until it's distributed. An agent with a zero balance literally
# cannot buy a ticket or a service — so the genesis deployer seeds the operational keys
# and the faucet; the relayer then auto-seeds each agent wallet, and from there the
# economy is CIRCULAR (winnings + service revenue + the Hub tithe / machine-UBI refill
# agents). This script is that one-time genesis distribution.
#
#   deployer ──seed──> operator (gas) + sponsor/Hub (tithe) + faucet
#   faucet ──relayer auto──> each agent wallet ──tickets/services──> lottery/providers
#   lottery ──prizes──> winners ;  Hub ──tithe(20%)──> lottery ──machine-UBI──> agents
#
# Usage:
#   GENESIS_KEY=0x... RPC=https://sepolia.base.org \
#   OPERATOR_ADDR=0x.. SPONSOR_ADDR=0x.. FAUCET_ADDR=0x.. \
#   ./scripts/bootstrap_economy.sh
set -euo pipefail

CAST="$HOME/.foundry/bin/cast"
RPC="${RPC:-https://sepolia.base.org}"
: "${GENESIS_KEY:?set GENESIS_KEY (the funded deployer/burner private key)}"
GENESIS=$("$CAST" wallet address --private-key "$GENESIS_KEY")

# Allocations (ETH). Defaults sized for a ~$20 / testnet budget; override via env.
OPERATOR_ADDR="${OPERATOR_ADDR:?set OPERATOR_ADDR}"; OPERATOR_ETH="${OPERATOR_ETH:-0.002}"   # round-driving gas
SPONSOR_ADDR="${SPONSOR_ADDR:?set SPONSOR_ADDR}";   SPONSOR_ETH="${SPONSOR_ETH:-0.003}"     # Hub's tithe source
FAUCET_ADDR="${FAUCET_ADDR:?set FAUCET_ADDR}";      FAUCET_ETH="${FAUCET_ETH:-0.008}"       # relayer auto-seeds agents from here

bal() { "$CAST" balance "$1" --rpc-url "$RPC"; }
echo "Genesis $GENESIS — balance $(bal "$GENESIS") wei on $RPC"
[ "$(bal "$GENESIS")" = "0" ] && { echo "ERROR: genesis balance is 0 — fund it first" >&2; exit 1; }

fund() {  # to amount role
  echo "  → $3: $1  ($2 ETH)"
  "$CAST" send "$1" --value "${2}ether" --private-key "$GENESIS_KEY" --rpc-url "$RPC" >/dev/null
}
echo "Distributing genesis allocation:"
fund "$OPERATOR_ADDR" "$OPERATOR_ETH" "operator (round gas)"
fund "$SPONSOR_ADDR"  "$SPONSOR_ETH"  "sponsor/Hub (tithe)"
fund "$FAUCET_ADDR"   "$FAUCET_ETH"   "faucet (agent seed pool)"

echo ""
echo "Resulting balances:"
for pair in "operator:$OPERATOR_ADDR" "sponsor:$SPONSOR_ADDR" "faucet:$FAUCET_ADDR"; do
  echo "  ${pair%%:*}: $(bal "${pair##*:}") wei"
done
echo ""
echo "Done. The relayer's faucet (FAUCET_KEY) auto-seeds each agent wallet on its first"
echo "round when balance < AGENT_FUND_WEI — agents then transact on their own; the economy"
echo "is circular from here (prizes + service revenue + Hub tithe refill participants)."
