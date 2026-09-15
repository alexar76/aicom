#!/usr/bin/env bash
# payment_preflight.sh — can this hub actually take money?
#
# Answers one question: would a deposit posted to /ai-market/v2/channel/open be
# verified on-chain, or silently refused / credited unverified? Run it on the hub
# host BEFORE flipping AIFACTORY_PROD=1, and against the public URL afterwards.
#
#   ./scripts/payment_preflight.sh                      # local env
#   ./scripts/payment_preflight.sh https://modelmarket.dev   # + live manifest
#
# Exit 0 = ready, 1 = not ready. No keys are read, nothing is written.
set -uo pipefail

URL="${1:-}"
fail=0

say()  { printf '%s\n' "$*"; }
ok()   { printf '  \033[32mOK\033[0m    %s\n' "$*"; }
bad()  { printf '  \033[31mMISS\033[0m  %s\n' "$*"; fail=1; }
warn() { printf '  \033[33mWARN\033[0m  %s\n' "$*"; }

# ── 1. Local env interlocks ────────────────────────────────────────────
# Mirrors HubConfig.payment_readiness() and security/prod_startup_guard.py.
# Defaults repeated here on purpose: an unset var must read the same way the
# hub reads it, not the way the operator assumes.
say "── env interlocks ─────────────────────────────────"

crypto="$(printf '%s' "${AIFACTORY_CRYPTO_ENABLED:-0}" | tr '[:upper:]' '[:lower:]')"
case "$crypto" in
  1|true|yes|on) ok "AIFACTORY_CRYPTO_ENABLED=$crypto" ;;
  *) bad "AIFACTORY_CRYPTO_ENABLED=$crypto — master switch off, no payment surface" ;;
esac

if [ "${AIFACTORY_PAYMENT_VERIFY_STUB:-0}" = "1" ]; then
  bad "AIFACTORY_PAYMENT_VERIFY_STUB=1 — ANY tx_hash is accepted without verification"
else
  ok "AIFACTORY_PAYMENT_VERIFY_STUB=${AIFACTORY_PAYMENT_VERIFY_STUB:-0}"
fi

if [ "${AIFACTORY_PROD:-}" = "1" ]; then
  ok "AIFACTORY_PROD=1"
else
  bad "AIFACTORY_PROD=${AIFACTORY_PROD:-<unset>} — verifier never runs; deposits are refused"
fi

if [ "${AIFACTORY_PAYMENT_TESTNET:-1}" = "0" ]; then
  ok "AIFACTORY_PAYMENT_TESTNET=0 (mainnet)"
else
  warn "AIFACTORY_PAYMENT_TESTNET=${AIFACTORY_PAYMENT_TESTNET:-1} — testnet accepts demo tx hashes"
fi

# Anvil/Hardhat dev accounts — their private keys are public, so money sent there is
# gone. Kept in sync with security/prod_startup_guard.py:_WELL_KNOWN_DEV_ADDRESSES.
DEV_ADDRS="0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266 0x70997970c51812dc3a010c7d01b50e0d17dc79c8
0x3c44cdddb6a900fa2b585dd299e03d12fa4293bc 0x90f79bf6eb2c4f870365e785982e1f101e93b906
0x15d34aaf54267db7d7c367839aaf71a00a2c6a65 0x9965507d1a55bcc2695c58ba16fb37d819b0a4dc
0x976ea74026e726554db657fa54763abd0c3a0aa9 0x14dc79964da2c08b23698b3d3cc7ca32193d9955
0x23618e81e3f5cdf7f54c3d65f7fbc0abf5b21e8f 0xa0ee7a142d267c1f36714e4a8f75612f20a79720
0x5fbdb2315678afecb367f032d93f642f64180aa3 0xe7f1725e7734ce288f8367e1bb143e90bb3f0512
0x9fe46736679d2d9a65f0992f2272de9f3c7fa6e0 0xcf7ed3acca5a467e9e704c703e8d87f634fb0fc9
0xdc64a140aa3e981100a9beca4e685f962f0cf6c9"

is_dev_addr() {
  local needle; needle="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"
  local a; for a in $DEV_ADDRS; do [ "$a" = "$needle" ] && return 0; done; return 1
}

recipient="${AIMARKET_PAYMENT_RECIPIENT:-}"
if is_dev_addr "$recipient"; then
  bad "AIMARKET_PAYMENT_RECIPIENT=$recipient is an ANVIL/HARDHAT DEV ADDRESS — its private key is public; every deposit is sweepable by anyone"
else
  case "$recipient" in
    ""|0x0000000000000000000000000000000000000000|*YOUR*|*XXXX*)
      bad "AIMARKET_PAYMENT_RECIPIENT='${recipient:-<unset>}' — deposits have nowhere to settle" ;;
    *) ok "AIMARKET_PAYMENT_RECIPIENT=${recipient:0:10}…" ;;
  esac
fi

contract="${AIFACTORY_AI_MARKET_CONTRACT:-}"
if is_dev_addr "$contract"; then
  bad "AIFACTORY_AI_MARKET_CONTRACT=$contract is a dev-chain deterministic address — no such contract on a real chain"
else
  case "$contract" in
    ""|0x0000000000000000000000000000000000000000)
      bad "AIFACTORY_AI_MARKET_CONTRACT unset — on-chain verification has no contract to query" ;;
    *) ok "AIFACTORY_AI_MARKET_CONTRACT=${contract:0:10}…" ;;
  esac
fi

if [ "${AIMARKET_ALLOW_DEMO_CREDIT:-}" = "1" ]; then
  bad "AIMARKET_ALLOW_DEMO_CREDIT=1 — unverified deposits are credited (must be unset in prod)"
else
  ok "AIMARKET_ALLOW_DEMO_CREDIT unset"
fi

if is_dev_addr "${AIMARKET_ESCROW_EVM_ADDRESS:-}"; then
  bad "AIMARKET_ESCROW_EVM_ADDRESS=${AIMARKET_ESCROW_EVM_ADDRESS} is a dev-chain address — no escrow contract lives there on a real chain"
elif [ -n "${AIMARKET_ESCROW_EVM_ADDRESS:-}" ]; then
  ok "AIMARKET_ESCROW_EVM_ADDRESS=${AIMARKET_ESCROW_EVM_ADDRESS:0:10}… (escrow-funded channels available)"
else
  warn "AIMARKET_ESCROW_EVM_ADDRESS unset — escrow-funded channels disabled, transfer path only"
fi

# ── 2. Live manifest, if a URL was given ───────────────────────────────
if [ -n "$URL" ]; then
  say ""
  say "── live manifest: $URL ────────────────────────────"
  body="$(curl -fsS -m 20 "$URL/.well-known/ai-market.json" 2>/dev/null)"
  if [ -z "$body" ]; then
    bad "could not fetch $URL/.well-known/ai-market.json"
  else
    printf '%s' "$body" | python3 -c '
import json, sys
d = json.load(sys.stdin)
ch = (d.get("plugin_extensions", {}).get("aimarket-channels", {}) or {}).get("channels", {})
rows = [
    ("payment_configured", d.get("payment_configured"), True),
    ("payment_testnet", d.get("payment_testnet"), False),
    ("channels.demo_mode", ch.get("demo_mode"), False),
]
bad = 0
for name, got, want in rows:
    mark = "\033[32mOK\033[0m   " if got is want else "\033[31mMISS\033[0m "
    if got is not want:
        bad = 1
    print(f"  {mark} {name}={got} (want {want})")
local_n, fed_n = d.get("capabilities_count"), d.get("federated_capabilities_count")
print(f"  advertised capabilities: {local_n} local, {fed_n} federated")
sys.exit(bad)
' || fail=1
  fi
fi

say ""
if [ "$fail" = "0" ]; then
  say "READY — deposits would be verified on-chain."
else
  say "NOT READY — fix the MISS lines above. See docs/payment-enable-runbook.md"
fi
exit "$fail"
