# Crypto / on-chain economy — the master switch

AICOM runs **without any blockchain by default**. Crypto is **OFF unless you
explicitly opt in**. With the switch off, no component loads a wallet, contacts
a chain/RPC, opens a payment channel, returns `402 Payment Required`, verifies a
transaction on-chain, or settles UNI/lottery. Every component still runs —
capabilities are served on a free tier, federation signing and internal
accounting keep working — it just never touches money.

## What you see in the Alien Monitor

The monitor shows the **true** state, never a faked one:

| Mode | Chain context | On-chain nodes (chain · escrow · NFT · ACEX · lottery) |
|------|---------------|--------------------------------------------------------|
| **TEST** | never | scripted/simulated |
| **UNI** | **always** (private local Anvil — never Base) | live against the local chain |
| **LIVE**, crypto **OFF** | none | **greyed / disabled** + badge "Real blockchain disabled in settings" |
| **LIVE**, crypto **ON** | Base mainnet | live on Base, lit up |

This mirrors the agent-side contract
`shouldBuildChainContext(mode, cryptoEnabled)`
(`argus/src/ecosystem/networks.ts`): `uni → always`, `live → only with crypto
on`, `test → never`. Safety invariant: `shouldBuildChainContext("live", false)
=== false`.

## How to enable the real on-chain economy

1. **Master switch.** Set `AIFACTORY_CRYPTO_ENABLED=1` in the ecosystem `.env`.
   Truthy values: `1`, `true`, `yes`, `on`. Anything else (or unset) = OFF.
2. **Per-component config.** Each component still needs its own real config:
   RPC endpoints, recipient/contract addresses, and wallet keys.
3. **Production interlocks.** In production the existing `AIFACTORY_PROD`
   fail-closed gates still apply on top of the switch.
4. **Alien Monitor specifically.** Deploy it in LIVE mode so it binds to the
   real chain:
   ```bash
   ALIEN_MODE=real AIFACTORY_CRYPTO_ENABLED=1 ./scripts/deploy_alien_monitor.sh --live
   ```
   In UNI mode the monitor always uses its private local Anvil chain and never
   touches Base, regardless of this switch.

## Safety

Only enable crypto when you intend to run a **real on-chain economy** (real
funds on Base). Leaving it off is the safe default and keeps the whole ecosystem
fully functional on the free tier.
