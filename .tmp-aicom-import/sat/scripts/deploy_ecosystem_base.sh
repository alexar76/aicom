#!/usr/bin/env bash
# Deploy the audited-safe ecosystem core to BASE MAINNET: FakeUSDT + AIMarketEscrow +
# AIMarketCapabilityNFT. (AIAgentLottery is deployed separately by deploy_lottery_base.sh.)
# ACEX is intentionally EXCLUDED — the audit flagged AuditPool TWAP + PulseAMM as HIGH.
#
#   ./scripts/deploy_ecosystem_base.sh           # dry-run (no gas)
#   ./scripts/deploy_ecosystem_base.sh broadcast # real deploy
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
KEYFILE="${BURNER_KEYFILE:-$HOME/.aicom-base-deployer.json}"
RPC="${BASE_RPC:-https://mainnet.base.org}"
CHAIN=8453
OWNER="${OWNER:-0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a}"
FORGE="$HOME/.foundry/bin/forge"
MODE="${1:-dryrun}"
BC=""; [ "$MODE" = "broadcast" ] && BC="--broadcast --slow"

PK=$(python3 -c "import json;d=json.load(open('$KEYFILE'));a=d['accounts'][0] if 'accounts' in d else d;print(a['private_key'])")
export PRIVATE_KEY="$PK"
cd "$ROOT/contracts/evm"

addr_of() {  # script-basename -> deployed address from the latest run json
  python3 -c "
import json,glob,sys
sub='$1'
g=glob.glob(f'broadcast/{sub}/$CHAIN/run-latest.json')
if not g: print(''); sys.exit()
d=json.load(open(g[-1]))
for tx in d.get('transactions',[]):
    if tx.get('contractAddress') and tx.get('transactionType')=='CREATE':
        print(tx['contractAddress']); break
"
}

echo ">>> [$MODE] FakeUSDT"
ALLOW_FAKE_USDT=true "$FORGE" script script/DeployFakeUSDT.s.sol:DeployFakeUSDTScript --rpc-url "$RPC" $BC >/tmp/d1.log 2>&1 || { tail -20 /tmp/d1.log; exit 1; }
USDT=$(addr_of DeployFakeUSDT.s.sol); [ -z "$USDT" ] && USDT="$OWNER"   # dry-run: no real addr yet → placeholder
echo ">>> [$MODE] AIMarketEscrow (hub=$OWNER, token=$USDT) — owned by deployer, transfer after"
INITIAL_HUBS="$OWNER" INITIAL_TOKENS="$USDT" "$FORGE" script script/Deploy.s.sol:DeployScript --rpc-url "$RPC" $BC >/tmp/d2.log 2>&1 || { tail -20 /tmp/d2.log; exit 1; }
echo ">>> [$MODE] AIMarketCapabilityNFT — owned by deployer, transfer after"
"$FORGE" script script/DeployNFT.s.sol:DeployCapabilityNFTScript --rpc-url "$RPC" $BC >/tmp/d3.log 2>&1 || { tail -20 /tmp/d3.log; exit 1; }

if [ "$MODE" = "broadcast" ]; then
  CAST="$HOME/.foundry/bin/cast"
  USDT=$(addr_of DeployFakeUSDT.s.sol); ESCROW=$(addr_of Deploy.s.sol); NFT=$(addr_of DeployNFT.s.sol)
  echo ""
  echo ">>> transferring Escrow + NFT ownership to $OWNER (2-step; OWNER must acceptOwnership)"
  "$CAST" send "$ESCROW" "transferOwnership(address)" "$OWNER" --private-key "$PK" --rpc-url "$RPC" >/dev/null 2>&1 && echo "  escrow → pending $OWNER" || echo "  escrow transfer skipped"
  "$CAST" send "$NFT" "transferOwnership(address)" "$OWNER" --private-key "$PK" --rpc-url "$RPC" >/dev/null 2>&1 && echo "  nft → pending $OWNER" || echo "  nft transfer skipped"
  echo ""
  echo "FakeUSDT:               $USDT"
  echo "AIMarketEscrow:         $ESCROW"
  echo "AIMarketCapabilityNFT:  $NFT"
  echo "$USDT|$ESCROW|$NFT" > /tmp/base_eco_addrs.txt
else
  echo "(dry-run complete — gas estimates in /tmp/d{1,2,3}.log; re-run with 'broadcast')"
  grep -hiE 'Estimated amount required|Total' /tmp/d1.log /tmp/d2.log /tmp/d3.log | head
fi
