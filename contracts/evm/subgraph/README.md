# AIMarketEscrow subgraph

Indexes the payment-channel lifecycle of `contracts/evm/src/AIMarketEscrow.sol`:
open → debit(s) → settle / refund / expire, plus the hub and token allow-lists.

```
subgraph.yaml   data source + event bindings (a TEMPLATE — see "Before deploying")
schema.graphql  Channel, Debit, Settlement, Refund, Hub, Token
src/mapping.ts  AssemblyScript handlers
tests/          agreement test: manifest ↔ .sol ↔ schema ↔ mapping
```

## Why this directory has a test

A subgraph fails **silently**. Each `eventHandlers[].event` string is hashed into
a topic0 log filter. If it no longer matches the Solidity declaration, graph-node
matches nothing, reports a healthy sync, and serves an empty dataset — no error
anywhere. Two such drifts existed here:

- `ChannelSettled` gained a fifth parameter when `recipient` was split into
  `usedRecipient` + `refundRecipient` (one field had attributed the hub's
  revenue to the depositor). Different arity ⇒ different topic0.
- `ChannelExpired` was renamed to `ChannelExpiredAndSettled` — it collided with
  the `ChannelExpired()` *error* in log decoders — and now carries the
  used/refund split, because expiry pays the hub instead of returning the whole
  deposit.

```bash
python3 -m pytest contracts/evm/subgraph/tests -q     # no toolchain needed
```

The test derives every expected signature from `src/AIMarketEscrow.sol`, so a
future contract change cannot leave this manifest quietly indexing nothing. It is
**not** wired into `.github/workflows/contracts-ci.yml` yet — that workflow only
runs Foundry and Slither.

## Before deploying

1. `forge build` in `contracts/evm/` — the manifest binds the JSON artifact at
   `../out/AIMarketEscrow.sol/AIMarketEscrow.json` (graph-cli cannot read `.sol`),
   and `out/` is git-ignored.
2. Substitute `{{AIMARKET_ESCROW_EVM_ADDRESS}}` with the escrow address for the
   target network.
3. Set `startBlock` to the escrow's **deploy block**. At `0` the indexer replays
   all of Base before the first channel can exist.
4. `graph codegen && graph build && graph deploy …`

## Re-deploy, do not migrate

`ChannelSettled` changed shape, so its topic0 changed. An indexer already synced
against the old event **cannot** pick the new one up: there is no in-place fix.
Deploy a new subgraph version and re-index from the escrow's deploy block, and
point consumers at the new endpoint only once it has caught up. The same applies
to any other consumer that hard-codes the old 4-parameter signature.

Note also that the escrow's own event change is **not** upgradeable in place on a
live deployment — see `docs/deploy-real-ecosystem-lottery.md` → *Migrating a live
deployment*.

## What the mapping will not invent

`ChannelExpiredAndSettled` names neither payout recipient. The depositor is known
from `ChannelOpened`; the bound hub is only ever named by a `ChannelSettled` log,
so `Settlement.usedRecipient` stays `null` for an expiry on a channel that never
settled. Expiry is permissionless, so the transaction sender is **not** a safe
stand-in for the hub and is deliberately not used as one.
