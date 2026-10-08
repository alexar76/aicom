# AIMarketEscrowV2 — what changes, and what deploying it costs

**Status: written, tested, NOT deployed.** `AIMarketEscrow.sol` stays in the tree
untouched because it is what lives at `0x12Db8FAC81E5999D2f2087B79e38951571562CF2` on
Base. A repo that quietly stops matching its deployed contract is the same defect this
audit found on PyPI, and it is not worth repeating in a place where the artefact is
immutable.

`forge test`: 143 passing, of which 14 are new. Every finding below has a test that
asserts the **V1** behaviour and then the V2 fix, in one file, so none of this has to be
taken on trust.

## Why

The escrow is only half the settlement path. An authorization is captured off chain when
a call is served and submitted on chain later — the collector is opt-in and defaults to
never. The gap between "served" and "debited" is therefore the normal state, not an edge
case, and four of the five defects below live in it.

It is measurable. `escrow_bridge.db` on the production hub holds **113** captured
authorizations: 27 confirmed, **86 abandoned**, every one of the 86 with `attempts = 0` —
$5.05 delivered and never collected against $1.53 collected. (79 of those 86 are a
separate, off-chain bug, fixed in `c1fa28609`.)

## The five

| # | V1 | V2 |
|---|---|---|
| 1 | A depositor can `settleChannel` at any instant, so every captured-but-unsubmitted authorization dies with the channel | A depositor must `requestClose` and wait `SETTLE_WINDOW` |
| 2 | `refundChannel` is gated on `usedAmount > 0`, which is exactly zero for every call served but not yet debited — the buyer takes the whole deposit back after being served | Same window; the `usedAmount` gate stays as a second lock |
| 3 | `usedReceipts` is one namespace for the whole contract over ids the BUYER chooses, so burning an id on a $1 channel of your own blocks a delivered call on somebody else's forever | Keyed by `(channelId, receiptId)`. The signature already binds `channelId`, so this takes nothing away |
| 4 | `debitChannel` needs `now <= expiresAt`, `expireChannel` needs `now > expiresAt` — complementary to the second, so an authorization signed near expiry can never land | The hub keeps `SETTLE_WINDOW` past expiry; `expireChannel` moves behind it |
| 5 | Both settlement legs push in one transaction, so a token blacklist on either party locks the whole channel — including the other party's money — permanently, because status is written first | A refused transfer is recorded as `withdrawable` and claimed with `withdraw(token)`. The happy path still pushes both legs |

`SETTLE_WINDOW` is **1 hour**: far longer than a collection pass (floored at 60s) and far
shorter than the 24h channel, so no buyer's money is held meaningfully longer than today.

## What it costs to deploy

**A new address.** The escrow is not upgradeable and must not be. That address is
published in `docs/onchain-journal.md`, on the landing pages and in
`AIMARKET_ESCROW_CONTRACT` / `AIMARKET_ESCROW_EVM_ADDRESS` on the live hub.

**Existing channels do not migrate.** V1 channels stay on V1 and must drain there —
settle, refund or expire as they always would. Run both addresses until V1 is empty.

**One client-visible change.** A depositor closing a channel now calls `requestClose`
first and settles an hour later. Any buyer tooling that calls `settleChannel` or
`refundChannel` directly needs that extra step. In this repo, since 2026-10-08,
`pov-demo/buyer.py` asks to close every channel of a run first (after a passing seller's
debit has landed) and settles them all once the window is over: one wait, not one per
seller. On V1 it settles at once, as before. `pov-demo/journey.py`, the six-hourly UNI
canary, sends `requestClose` on V2 and settles the channel on its next run, which finds it
from its `ChannelOpened` log. The bubble clock is never moved. Many dust channels close in two transactions:
`batchRequestClose`, then `batchRefund` after the window (`batchRefund` honours the same
window as `refundChannel` since 2026-10-08 — it used to skip it).

**Changes in our own stack — done 2026-10-08, V1 behaviour unchanged.** V2 keys its replay
flag by `(channelId, receiptId)`, so `usedReceipts(receiptId)` read raw always says "not used"
there. Both readers now ask `isReceiptUsed(channelId, receiptId)` first. The hub's mirror
does, and so does `escrow-signer` (HORKOS), on the debit path and in boot reconciliation.
HORKOS treats an escrow as V1 only after two reverts, `isReceiptUsed` and the V2-only
`SETTLE_WINDOW()`. A spurious revert or an outage on V2 never falls back to the V1
question. HORKOS also follows V2's timing: it signs debits until `expiresAt +
SETTLE_WINDOW` (V1 stops at `expiresAt`), and it signs `expireChannel` only after that
(earlier it would revert). `scripts/escrow_settlement_sweep.py` reads the ten-word
`getChannel` and asks for expiry at the same moment. Hub-initiated settle is unchanged and
immediate. The hub stops serving a V2 channel once its depositor has requested the close
(`closableAt != 0`). All of it was checked against real V1 and V2 bytecode on a private
anvil. The checks covered HORKOS's full sign → broadcast → reconcile path, a debit two
minutes past expiry (V1 refused, V2 signed and landed), expiry inside and after the
window, and the buyer's `requestClose` → wait → settle path.

**HORKOS pins one escrow.** `escrow-signer/escrow_signer/config.py` `ESCROW` is a constant,
and boot fails closed if the domain separator disagrees, so it cannot sign for V1 and V2 at
once. Switch it in the same deploy as the hub's escrow address. V1 channels left over after
the switch can still be closed: `expireChannel` is permissionless, and anyone can pay its gas.

## Deploy, when you decide to

```bash
cd contracts/evm
forge test                                   # 148, all green
forge create src/AIMarketEscrowV2.sol:AIMarketEscrowV2 \
  --rpc-url "$BASE_RPC" --private-key "$DEPLOYER_KEY" \
  --constructor-args "[$HUB_ADDRESS]" "[0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913]"
```

Then, and only once V1 is drained:

1. `AIMARKET_ESCROW_CONTRACT` and `AIMARKET_ESCROW_EVM_ADDRESS` → the new address, and
   `ESCROW` in `escrow-signer/escrow_signer/config.py` in the same deploy (HORKOS pins it).
2. Re-check `authorizedHubs` and the USDC whitelist on the new contract.
3. Update `docs/onchain-journal.md` and the landing pages.
4. Record the address here, and only then delete nothing — V1 stays in the tree as the
   record of what ran.

I will not deploy this. It spends your gas and changes an address you have published.
