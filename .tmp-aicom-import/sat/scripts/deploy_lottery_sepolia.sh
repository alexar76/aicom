#!/usr/bin/env bash
# Deploy AIAgentLottery to BASE SEPOLIA (testnet demo) with the generated burner wallet.
#
# Prereqs: the burner wallet must hold a little Base-Sepolia ETH (faucet step — see the
# address printed by the wallet generator). Then just run this; it deploys, prints the
# address, and writes it to docs/deployments-sepolia.md.
#
# Burner key lives OUTSIDE the repo (~/.aicom-sepolia-burner.json, chmod 600) — never committed.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
KEYFILE="${BURNER_KEYFILE:-$HOME/.aicom-sepolia-burner.json}"
RPC="${BASE_SEPOLIA_RPC:-https://sepolia.base.org}"
CHAIN_ID=84532
FORGE="$HOME/.foundry/bin/forge"
CAST="$HOME/.foundry/bin/cast"

[ -f "$KEYFILE" ] || { echo "ERROR: burner key not found at $KEYFILE" >&2; exit 1; }
PK=$(python3 -c "import json;d=json.load(open('$KEYFILE'));print((d[0] if isinstance(d,list) else d)['private_key'])")
ADDR=$(python3 -c "import json;d=json.load(open('$KEYFILE'));print((d[0] if isinstance(d,list) else d)['address'])")

BAL=$("$CAST" balance "$ADDR" --rpc-url "$RPC")
echo "Deployer $ADDR — balance $BAL wei on Base Sepolia"
[ "$BAL" = "0" ] && { echo "ERROR: balance is 0 — fund $ADDR from a Base-Sepolia faucet first" >&2; exit 1; }

# ── demo params (fast rounds, native-ETH tickets, instant ownership handover) ──
export PRIVATE_KEY="$PK"
export TOKEN="0x0000000000000000000000000000000000000000"   # native ETH tickets
export TICKET_PRICE="100000000000000"      # 0.0001 ETH — tiny so agents play many rounds
export PRIZE_BPS="8000" OPEX_BPS="1200" OPERATOR_BPS="800"
export ENTRY_WINDOW="120"                  # 2-min entry window (fast to observe)
export MIN_DRAW_DELAY="30"
# ONCHAIN_VDF=false → Chronos VDF verified OFF-chain by the relayer, committed to
# on-chain via the ORACLE_SIGNER EIP-712 beacon. Winner =
# keccak256(roundId, blockhash(seedBlock), platonRandom) — NO prevrandao: the
# fairness rework removed it from `_randomWord` (it made the outcome a function of
# the submission block, i.e. a re-roll lever, and on OP-stack L2s it is inherited
# from L1 and repeats across L2 blocks). Unbiasability here comes from the
# commit-reveal (seedCommitment fixed at closeEntries) plus a seedBlock pinned in
# the future, not from prevrandao. ONCHAIN_VDF=true additionally proves the delay
# was served (trustless vs the oracle signer) at the cost of a modexp per draw —
# worth it for a value deployment, unnecessary for this testnet demo.
export ONCHAIN_VDF="false"
export ADMIN_TRANSFER_DELAY="0"            # instant admin handover for the demo
# ADMIN/GOVERNANCE/OPERATOR/ORACLE_SIGNER/TREASURY default to the deployer; transfer later.

cd "$ROOT/lottery/contracts"
echo "Deploying AIAgentLottery to Base Sepolia…"
"$FORGE" script script/DeployLottery.s.sol:DeployLottery \
  --rpc-url "$RPC" --broadcast --skip-simulation --slow 2>&1 | tee /tmp/deploy_sepolia.log

DEPLOYED=$(python3 -c "
import json,glob,sys
f=sorted(glob.glob('broadcast/DeployLottery.s.sol/$CHAIN_ID/run-latest.json'))
if not f: sys.exit('no broadcast json')
d=json.load(open(f[-1]))
for tx in d.get('transactions',[]):
    if tx.get('contractName')=='AIAgentLottery' and tx.get('contractAddress'):
        print(tx['contractAddress']); break
")
echo ""
echo "==================================================================="
echo " AIAgentLottery (Base Sepolia 84532): $DEPLOYED"
echo " explorer: https://sepolia.basescan.org/address/$DEPLOYED"
echo "==================================================================="

# record it in the docs
DOC="$ROOT/lottery/docs/deployments-sepolia.md"
{
  echo "## Base Sepolia (testnet demo)"
  echo ""
  echo "| Contract | Address | Explorer |"
  echo "|---|---|---|"
  echo "| AIAgentLottery | \`$DEPLOYED\` | https://sepolia.basescan.org/address/$DEPLOYED |"
  echo ""
  echo "- Chain ID: 84532 · ticket: 0.0001 ETH (native) · prize/opex/operator 80/12/8"
  echo "- Deployer/admin: \`$ADDR\` (burner). Run the relayer with LOTTERY_MODE=live RPC=$RPC LOTTERY_ADDRESS=$DEPLOYED."
} > "$DOC"
echo "wrote $DOC"
