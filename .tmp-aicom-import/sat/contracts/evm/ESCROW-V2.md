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
`refundChannel` directly needs that extra step; nothing in this repo does, because closing
is a buyer action.

**One change in our own stack.** `escrow-signer` (HORKOS) signs `settleChannel` and
`expireChannel` on the hub's behalf. Hub-initiated settle is unchanged and immediate.
`expireChannel` simply reverts for an extra hour — the signer already treats an early
revert as normal, so its policy needs no edit.

## Deploy, when you decide to

```bash
cd contracts/evm
forge test                                   # 143, all green
forge create src/AIMarketEscrowV2.sol:AIMarketEscrowV2 \
  --rpc-url "$BASE_RPC" --private-key "$DEPLOYER_KEY" \
  --constructor-args "[$HUB_ADDRESS]" "[0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913]"
```

Then, and only once V1 is drained:

1. `AIMARKET_ESCROW_CONTRACT` and `AIMARKET_ESCROW_EVM_ADDRESS` → the new address.
2. Re-check `authorizedHubs` and the USDC whitelist on the new contract.
3. Update `docs/onchain-journal.md` and the landing pages.
4. Record the address here, and only then delete nothing — V1 stays in the tree as the
   record of what ran.

I will not deploy this. It spends your gas and changes an address you have published.
