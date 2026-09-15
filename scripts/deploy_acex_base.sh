#!/usr/bin/env bash
# Deploy the ACEX capital-markets stack to Base mainnet.
#
#   ./scripts/deploy_acex_base.sh           # dry-run simulation (no gas, no broadcast)
#   ./scripts/deploy_acex_base.sh broadcast # real deploy
#
# Mirrors scripts/deploy_ecosystem_base.sh: the private key is read from the keystore
# INSIDE this script and exported only into forge's environment.
#
# After a broadcast, update config/deployments/base-mainnet.json with the printed
# addresses and run:  python scripts/sync_deployment_addresses.py
# That is the only place addresses are edited by hand — every consumer is generated.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
KEYFILE="${BURNER_KEYFILE:-$HOME/.aicom-base-deployer-v4.json}"
RPC="${BASE_RPC:-https://mainnet.base.org}"
CHAIN=8453
USDC="${USDC_ADDRESS:-0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913}"  # Base mainnet USDC
FORGE="$HOME/.foundry/bin/forge"
MODE="${1:-dryrun}"

[ -f "$KEYFILE" ] || { echo "keystore not found: $KEYFILE" >&2; exit 1; }
[ -x "$FORGE" ] || { echo "forge not found at $FORGE" >&2; exit 1; }

PK=$(python3 -c "import json;d=json.load(open('$KEYFILE'));a=d['accounts'][0] if 'accounts' in d else d;print(a['private_key'])")
SENDER=$(python3 -c "import json;d=json.load(open('$KEYFILE'));a=d['accounts'][0] if 'accounts' in d else d;print(a['address'])")

# DeployACEX.s.sol reads these two names.
export DEPLOYER_PRIVATE_KEY="$PK"
export USDC_ADDRESS="$USDC"

echo "network : Base mainnet (chain $CHAIN)"
echo "rpc     : $RPC"
echo "sender  : $SENDER"
echo "usdc    : $USDC"
echo "mode    : $MODE"
BAL=$("$HOME/.foundry/bin/cast" balance "$SENDER" --rpc-url "$RPC")
echo "balance : $BAL wei"
echo

cd "$ROOT/acex/contracts/evm"

if [ "$MODE" = "broadcast" ]; then
  "$FORGE" script script/DeployACEX.s.sol:DeployACEX \
    --rpc-url "$RPC" --broadcast --slow -vvv
  echo
  echo "Deployed. Next:"
  echo "  1. put the addresses above into config/deployments/base-mainnet.json"
  echo "  2. python scripts/sync_deployment_addresses.py"
  echo "  3. record the run in docs/onchain-journal.md"
else
  "$FORGE" script script/DeployACEX.s.sol:DeployACEX \
    --rpc-url "$RPC" --sender "$SENDER" -vvv
  echo
  echo "Dry run only — nothing was broadcast. Re-run with: $0 broadcast"
fi
