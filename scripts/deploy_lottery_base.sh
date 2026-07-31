#!/usr/bin/env bash
# Deploy AIAgentLottery to BASE MAINNET (8453). Real funds — minimal.
#   ./scripts/deploy_lottery_base.sh           # dry-run (simulate, NO gas spent)
#   ./scripts/deploy_lottery_base.sh broadcast # real deploy
#
# Roles: admin/governance/treasury = OWNER (controls money/admin from the first block);
# operator/oracle-signer = the deployer burner (the relayer drives rounds). So ownership
# is set AT DEPLOY — no fragile post-deploy admin transfer.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
KEYFILE="${BURNER_KEYFILE:-$HOME/.aicom-base-deployer.json}"
RPC="${BASE_RPC:-https://mainnet.base.org}"
CHAIN_ID=8453
OWNER="${OWNER:-0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a}"
FORGE="$HOME/.foundry/bin/forge"
CAST="$HOME/.foundry/bin/cast"
MODE="${1:-dryrun}"

PK=$(python3 -c "import json;d=json.load(open('$KEYFILE'));a=d['accounts'][0] if 'accounts' in d else d;print(a['private_key'])")
DEPLOYER=$(python3 -c "import json;d=json.load(open('$KEYFILE'));a=d['accounts'][0] if 'accounts' in d else d;print(a['address'])")
echo "Deployer $DEPLOYER — balance $("$CAST" balance "$DEPLOYER" --rpc-url "$RPC") wei — owner $OWNER"

export PRIVATE_KEY="$PK"
export ADMIN="$OWNER" GOVERNANCE="$OWNER" TREASURY="$OWNER"
export OPERATOR="$DEPLOYER" ORACLE_SIGNER="$DEPLOYER"
export TOKEN="0x0000000000000000000000000000000000000000"   # native-ETH tickets
export TICKET_PRICE="3000000000000"      # 0.000003 ETH (~$0.01) — tiny real stakes
export PRIZE_BPS="8000" OPEX_BPS="1200" OPERATOR_BPS="800"
export ENTRY_WINDOW="120" MIN_DRAW_DELAY="30"
# ONCHAIN_VDF=false → the Chronos VDF proof is verified OFF-chain by the relayer and
# only committed to on-chain (the ORACLE_SIGNER's EIP-712 beacon hashes the exact
# proof). The winner is then keccak256(roundId, blockhash(seedBlock), platonRandom).
#
# There is NO prevrandao in that word any more. `_randomWord` used to mix
# `block.prevrandao` in; it was removed in the fairness rework because it made the
# outcome a function of the SUBMISSION block — a re-roll lever for whoever submits,
# and on an OP-stack L2 (this IS Base) prevrandao is inherited from the L1 origin
# block, so it is identical across many L2 blocks and predictable to the submitter.
#
# What carries fairness with the VDF off-chain, and why false is still the right
# default here: closeEntries pins seedBlock = block.number + SEED_BLOCK_OFFSET and
# stores keccak(platonRandom) as a commitment, so the randomness is committed BEFORE
# its blockhash exists and fulfillDraw rejects any other reveal. Nobody — operator,
# signer or submitter — can grind the winner, and settlement is permissionless so it
# cannot be withheld. On-chain VDF verification (ChronosVDF) buys one extra property:
# proof that the delay was actually served, i.e. trustlessness against a signer who
# skips the grind. It costs a large modexp per settlement.
#
# Set ONCHAIN_VDF=true if this deployment must be trustless with respect to the
# oracle signer as well; the gas is the price of that guarantee.
export ONCHAIN_VDF="false"
export ADMIN_TRANSFER_DELAY="0"

cd "$ROOT/lottery/contracts"
if [ "$MODE" = "broadcast" ]; then
  echo ">>> BROADCASTING to Base mainnet…"
  "$FORGE" script script/DeployLottery.s.sol:DeployLottery --rpc-url "$RPC" --broadcast --slow 2>&1 | tee /tmp/deploy_base.log
  DEPLOYED=$(python3 -c "
import json,glob,sys
f=glob.glob('broadcast/DeployLottery.s.sol/$CHAIN_ID/run-latest.json')
if not f: sys.exit('no broadcast json')
d=json.load(open(f[-1]))
for tx in d.get('transactions',[]):
    if tx.get('contractName')=='AIAgentLottery' and tx.get('contractAddress'):
        print(tx['contractAddress']); break
")
  echo ""
  echo "==================================================================="
  echo " AIAgentLottery (Base 8453): $DEPLOYED"
  echo " owner/admin: $OWNER · operator/signer: $DEPLOYER"
  echo " https://basescan.org/address/$DEPLOYED"
  echo "==================================================================="
  DOC="$ROOT/lottery/docs/deployments-base.md"
  {
    echo "## Base mainnet (8453)"
    echo ""
    echo "| Contract | Address | Explorer |"
    echo "|---|---|---|"
    echo "| AIAgentLottery | \`$DEPLOYED\` | https://basescan.org/address/$DEPLOYED |"
    echo ""
    echo "- owner/admin/treasury: \`$OWNER\` · operator/oracle-signer: \`$DEPLOYER\`"
    echo "- native-ETH tickets · ticket 0.000003 ETH · prize/opex/operator 80/12/8 · off-chain VDF"
  } > "$DOC"
  echo "wrote $DOC"
else
  echo ">>> DRY-RUN (simulation only, no broadcast)…"
  "$FORGE" script script/DeployLottery.s.sol:DeployLottery --rpc-url "$RPC" 2>&1 | tee /tmp/deploy_base_dry.log
fi
