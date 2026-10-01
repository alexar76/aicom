#!/usr/bin/env bash
# Redeploy AIMarketEscrow and/or AIAgentLottery to Base mainnet.
#
#   ./scripts/deploy_escrow_lottery_base.sh escrow            # dry-run simulation
#   ./scripts/deploy_escrow_lottery_base.sh escrow broadcast  # real deploy
#   ./scripts/deploy_escrow_lottery_base.sh lottery
#   ./scripts/deploy_escrow_lottery_base.sh lottery broadcast
#
# Mirrors scripts/deploy_acex_base.sh: the private key is read from the keystore INSIDE
# this script and exported only into forge's environment — never an argument, so it never
# reaches `ps aux` or shell history.
#
# WHY THE PARAMETERS ARE PINNED HERE
# ----------------------------------
# DeployLottery.s.sol defaults every parameter to the deployer / to generic values
# (ENTRY_WINDOW 1 day, MIN_DRAW_DELAY 60, TICKET_PRICE 0.001 ether). The LIVE demo ran a
# quite different configuration, read off chain on 2026-09-04 from the then-live lottery
# (its address is in docs/onchain-journal.md — not repeated here, so this file cannot
# itself go stale):
#
#     token           0x0 (native ETH, NOT USDC)
#     ticketPrice     3000000000000 wei  (0.000003 ETH)
#     prize/opex/op   8000 / 1200 / 800 bps
#     entryWindow     30 s     (script default would be 86400)
#     minDrawDelay    15 s     (script default would be 60)
#     onchainVdf      false
#     all four roles  0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a
#
# Redeploying on the defaults would therefore have silently shipped a lottery with a
# 24-hour entry window and a 300x ticket price. A redeploy is meant to change the CODE.
#
# Escrow constructor args are likewise the live ones: HORKOS is the only authorized hub
# (it holds the only key in AIMarketEscrow.authorizedHubs) and Base USDC the only
# whitelisted token.
#
# AFTER A BROADCAST — none of this is automatic:
#   1. put the new address into config/deployments/base-mainnet.json (the ONLY hand-edited
#      file) and run: python scripts/sync_deployment_addresses.py
#   2. record the run in docs/onchain-journal.md
#   3. FOR THE ESCROW ONLY: repoint HORKOS (escrow-signer pins cfg.ESCROW and verifies at
#      boot that its key is an authorized hub AND that the domain separator matches — it
#      fails CLOSED, so it stops signing until reconfigured) and the hub's own escrow env.
#      Until both are done the payment rail is down.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
KEYFILE="${BURNER_KEYFILE:-$HOME/.aicom-base-deployer-v4.json}"
RPC="${BASE_RPC:-https://mainnet.base.org}"
CHAIN=8453
FORGE="$HOME/.foundry/bin/forge"
CAST="$HOME/.foundry/bin/cast"

WHAT="${1:-}"
MODE="${2:-dryrun}"
case "$WHAT" in
  escrow|lottery) : ;;
  *) echo "usage: $0 <escrow|lottery> [broadcast]" >&2; exit 1 ;;
esac

[ -f "$KEYFILE" ] || { echo "keystore not found: $KEYFILE" >&2; exit 1; }
[ -x "$FORGE" ]   || { echo "forge not found at $FORGE" >&2; exit 1; }

PK=$(python3 -c "import json;d=json.load(open('$KEYFILE'));a=d['accounts'][0] if 'accounts' in d else d;print(a['private_key'])")
SENDER=$(python3 -c "import json;d=json.load(open('$KEYFILE'));a=d['accounts'][0] if 'accounts' in d else d;print(a['address'])")

# Deploy.s.sol and DeployLottery.s.sol both read vm.envUint("PRIVATE_KEY").
export PRIVATE_KEY="$PK"

OWNER="0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a"
USDC="0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
HORKOS="0xBE0bBE44cceCfEb048dd53f601C37525a3D6C5f1"

echo "network : Base mainnet (chain $CHAIN)"
echo "rpc     : $RPC"
echo "sender  : $SENDER"
echo "target  : $WHAT"
echo "mode    : $MODE"
echo "balance : $("$CAST" balance "$SENDER" --rpc-url "$RPC") wei"
if [ "$SENDER" != "$OWNER" ]; then
  echo "⚠️  sender is not the canonical owner $OWNER — the new contract's roles would differ." >&2
fi
echo

if [ "$WHAT" = "escrow" ]; then
  cd "$ROOT/contracts/evm"
  export INITIAL_HUBS="$HORKOS"
  export INITIAL_TOKENS="$USDC"
  TARGET="script/Deploy.s.sol:DeployScript"
  echo "INITIAL_HUBS   = $INITIAL_HUBS   (HORKOS — the only authorized hub)"
  echo "INITIAL_TOKENS = $INITIAL_TOKENS   (Base USDC)"
else
  cd "$ROOT/lottery/contracts"
  export ADMIN="$OWNER" GOVERNANCE="$OWNER" OPERATOR="$OWNER"
  export ORACLE_SIGNER="$OWNER" TREASURY="$OWNER"
  export TOKEN="0x0000000000000000000000000000000000000000"
  export TICKET_PRICE="3000000000000"
  export PRIZE_BPS="8000" OPEX_BPS="1200" OPERATOR_BPS="800"
  export ENTRY_WINDOW="30" MIN_DRAW_DELAY="15"
  export ONCHAIN_VDF="false"
  TARGET="script/DeployLottery.s.sol:DeployLottery"
  echo "reproducing the live config (see the header for why these are pinned)"
fi
echo

if [ "$MODE" = "broadcast" ]; then
  "$FORGE" script "$TARGET" --rpc-url "$RPC" --broadcast --slow -vvv
  echo
  echo "Deployed. NEXT STEPS ARE NOT AUTOMATIC — see this script's header."
else
  "$FORGE" script "$TARGET" --rpc-url "$RPC" --sender "$SENDER" -vvv
  echo
  echo "(dry run — nothing was broadcast. Re-run with 'broadcast' to deploy.)"
fi
