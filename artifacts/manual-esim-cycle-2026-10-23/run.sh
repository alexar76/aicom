#!/usr/bin/env bash
set -euo pipefail
umask 077
mode="${1:-quote}"
case "$mode" in quote|buy|refund) ;; *) echo 'Use: bash run.sh quote|buy|refund' >&2; exit 2 ;; esac
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
workspace="$(cd -- "$script_dir/../.." && pwd)"
if [[ "$mode" == buy && -e "$script_dir/delivery.json" ]]; then
  echo 'A purchase checkpoint already exists. Do not buy again; preserve delivery.json for reconciliation.' >&2
  exit 1
fi
tunnel_dir="$(mktemp -d /tmp/esim-manual.XXXXXX)"
cleanup() {
  ssh -S "$tunnel_dir/control" -O exit factory-vps </dev/null >/dev/null 2>&1 || true
  rmdir "$tunnel_dir" 2>/dev/null || true
}
trap cleanup EXIT
ssh -M -S "$tunnel_dir/control" -fNT -o BatchMode=yes -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 -L 127.0.0.1:19489:127.0.0.1:9489 factory-vps
node --import "$script_dir/transport.mjs" --input-type=module - <<'JS'
const response = await fetch('https://esim.modelmarket.dev/stand/healthz');
const health = await response.json();
if (!response.ok || !health.ok || health.demo || !health.paid_orders || health.refunds !== 'automatic' || health.reconciliation !== 'finalized-base') {
  throw Error('The private production stand is not ready for a paid test');
}
console.log('Production stand: ready; Base USDC; automatic refunds');
JS
if [[ "$mode" == refund ]]; then
  node --import "$script_dir/transport.mjs" "$script_dir/refund.mjs"
else
  args=(node --import "$script_dir/transport.mjs" "$workspace/esim-kit/rails/examples/agent-buy.mjs" \
    https://esim.modelmarket.dev/stand TR --key-file "${ESIM_TEST_BUYER_KEY_FILE:-$HOME/.aicom-pov-buyer.json}" \
    --max-usd 0.31 --no-share --output "$script_dir/delivery.json")
  [[ "$mode" != buy ]] || args+=(--yes)
  "${args[@]}"
fi
