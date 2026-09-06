# Case study — one tool call, $0.08 of real USDC, five transactions on Base

> **What this is.** A complete, independently verifiable record of an agent buying one capability
> through the AIMarket Hub and paying for it in real USDC on Base mainnet: an escrow deposit, a
> signed off-chain receipt, an on-chain debit that carries that receipt, and a settlement that moved
> the money. Every hash below is live on Base mainnet (chainId **8453**) and every check in
> [Verify it yourself](#verify-it-yourself) was run against a public RPC while writing this page.

> **What this is not.** Not a customer story. The buyer wallet belongs to us and was funded by our
> operator wallet ten minutes before the run
> ([`0x646bd8…f86fd5`](https://basescan.org/tx/0x646bd883bb4670dd20311e4b0aeb44eebf77772489f0f558d3df03fcf9f86fd5),
> 1.00 USDC). What is being proved here is the **payment path**, end to end, with real money and
> real signatures — not demand.

## The cast

| Role | Address | Note |
|---|---|---|
| Buyer (escrow depositor) | [`0x6E94c380d908531f9822035d6cc4c8D2B0186C9c`](https://basescan.org/address/0x6E94c380d908531f9822035d6cc4c8D2B0186C9c) | Separate wallet, funded by the operator; signs the debit authorization |
| Hub operator (payee) | [`0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a`](https://basescan.org/address/0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a) | Bound to the channel on first debit; receives the used amount |
| Escrow contract | [`0x0606983cbEc6D0C12a0B750f72Ceb6032c72C25D`](https://basescan.org/address/0x0606983cbEc6D0C12a0B750f72Ceb6032c72C25D) | `AIMarketEscrow`, source-verified. **The escrow of this run**, superseded on 2026-09-04 by [`0x12Db8FAC81E5999D2f2087B79e38951571562CF2`](https://basescan.org/address/0x12Db8FAC81E5999D2f2087B79e38951571562CF2) (journal §5). The commands below are deliberately left pointing here — this channel exists on this contract and nowhere else, so re-aiming them at the current escrow would destroy the proof rather than update it. |
| Token | [`0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`](https://basescan.org/address/0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913) | Circle USDC on Base — not a testnet token |
| Capability bought | `skopos.security.posture@v1` | Priced at **$0.08** per call in the Hub catalogue on the day of the run. It is not in the live catalogue any more; that catalogue carried **94 federated capabilities** from the oracle family, GAIA and ATLAS when this page was last checked (2026-08-27) — see [`production-metrics.md`](production-metrics.md) for how to re-read it live |

## What happened, in order

All times UTC, 2026-07-27. Escrow channel id
`0xa3ebd1478c847cc9b58ed57dfac478d67cbf8a689291506a5aab7b0987c2fb13`, hub ledger channel
`ch_9417f011bbe54d8a`.

| # | Time | Step | On chain | Effect |
|--:|---|---|---|---|
| 0 | 20:49:29 | Operator funds the buyer wallet | [`0x646bd8…f86fd5`](https://basescan.org/tx/0x646bd883bb4670dd20311e4b0aeb44eebf77772489f0f558d3df03fcf9f86fd5) | 1.00 USDC → buyer. Stated here because it is the honest part of the story |
| 1 | 20:57:11 | `USDC.approve(escrow, 1.00)` | [`0x93c71f…f8a5f1`](https://basescan.org/tx/0x93c71f782fd8d382e2c23f98c2f5f5adb556728391910dabcb9986894ef8a5f1) | Allowance only; no USDC moves yet |
| 2 | 20:57:13 | `escrow.openChannel(id, USDC, 1.00)` | [`0xea4038…83549e`](https://basescan.org/tx/0xea4038c9f6dedb26ece1c0454a4b181cd17c71686c6e73b5f092e70a2c83549e) | **1.00 USDC locked** in escrow; `usedAmount = 0`, hub unbound |
| 3 | ~20:58 | Hub: `POST /channel/open` → `POST /invoke` → `POST /channel/close` | off-chain | Capability returns **200**; ledger records **$0.08 used**, **$0.92 owed back**. The buyer signs an EIP-712 `DebitAuthorization` for exactly $0.08 |
| 4 | 20:59:41 | `escrow.debitChannel(id, 80000, receiptId, deadline, signature)` | [`0xf740cd…824355`](https://basescan.org/tx/0xf740cd0cd2ada97dd243ad067c2dc0f16504d40030c54b4aef37137f2a824355) | Contract recovers the buyer's signature, binds the hub, marks the receipt spent, meters **80000** base units |
| 5 | 20:59:47 | `escrow.settleChannel(id)` | [`0xcce0dc…942472`](https://basescan.org/tx/0xcce0dcdddfd962cd2d16840246cfc2761b8325d4a58f186009bcdd5b3c942472) | **$0.08 → operator**, **$0.92 → buyer**, channel `Settled` |

Two minutes and thirty-six seconds from deposit to settlement. Gas on Base for the whole sequence
was a fraction of a cent.

## The receipt

The receipt is not a PDF and not a database row — it is a value the buyer signed and the contract
consumed:

```
receiptId  0x409356b384b8542ab1961c2d238a781f751e9e277115fc87ac7224b951bce5ce
```

The buyer signed an EIP-712 `DebitAuthorization` over exactly this struct:

```solidity
DebitAuthorization(
  bytes32 channelId,
  address hub,
  address token,
  uint256 amount,
  bytes32 receiptId,
  uint256 nonce,
  uint256 deadline
)
```

Three properties follow from what is signed, and each one closes a specific attack:

- **`hub` is inside the signature.** An authorization written for one hub cannot be replayed by
  another authorized hub to capture the channel.
- **`receiptId` is marked spent** (`usedReceipts[receiptId] = true`) on debit, and `nonce`
  increments. The same authorization cannot be charged twice.
- **`amount` is signed.** The hub can charge the buyer's channel for `$0.08` and nothing else — it
  cannot round up, and it cannot charge a channel the buyer never authorized, because
  `ECDSA.recover(digest, signature)` must equal the channel depositor or the transaction reverts.

The receipt and the buyer's signature are not merely referenced on chain — they are *in the
calldata* of transaction 4, permanently readable by anyone:

```
0xf7becd80                                                          debitChannel selector
a3ebd147…fb13                                                       channelId
0000…013880                                                         amount = 80000 = $0.08
409356b384b8542ab1961c2d238a781f751e9e277115fc87ac7224b951bce5ce    receiptId
0000…6a67d4b9                                                       deadline = 1785189561
…0041 111fa772…edf041b                                              65-byte depositor signature
```

## Verify it yourself

Everything below was run against `https://mainnet.base.org` while this page was written. No
Basescan account, no API key, no trust in this document required.

**The money moved.** The settlement transaction contains two USDC `Transfer` events out of the
escrow — `0x13880` (80000 = $0.08) to the operator and `0xe09c0` (920000 = $0.92) back to the buyer:

```bash
cast receipt 0xcce0dcdddfd962cd2d16840246cfc2761b8325d4a58f186009bcdd5b3c942472 --rpc-url https://mainnet.base.org
```

**The channel agrees.** Reading the escrow's own state: depositor `0x6E94…`, hub `0x1218…`, token
USDC, deposit `0xf4240` (1.00), balance `0xe09c0` (0.92), used `0x13880` (0.08), nonce 1, status
`Settled`:

```bash
cast call 0x0606983cbEc6D0C12a0B750f72Ceb6032c72C25D \
  "channels(bytes32)" \
  0xa3ebd1478c847cc9b58ed57dfac478d67cbf8a689291506a5aab7b0987c2fb13 \
  --rpc-url https://mainnet.base.org
```

**The buyer really signed it.** Ask the contract for the EIP-712 digest of that authorization, then
recover the signer from the signature sitting in the debit calldata:

```bash
cast call 0x0606983cbEc6D0C12a0B750f72Ceb6032c72C25D \
  "computeDebitDigest(bytes32,address,address,uint256,bytes32,uint256,uint256)(bytes32)" \
  0xa3ebd1478c847cc9b58ed57dfac478d67cbf8a689291506a5aab7b0987c2fb13 \
  0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a \
  0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913 \
  80000 \
  0x409356b384b8542ab1961c2d238a781f751e9e277115fc87ac7224b951bce5ce \
  0 1785189561 \
  --rpc-url https://mainnet.base.org
# → 0xae58bcf00c07ea01ea403f6565850f90b26845979ee0ce581ad44cc93ccedfbe
```

```python
from eth_keys import keys

digest = bytes.fromhex("ae58bcf00c07ea01ea403f6565850f90b26845979ee0ce581ad44cc93ccedfbe")
sig = bytes.fromhex(
    "111fa772d71f8794f9005fdc20510c78af45e35d622c4f66da79a014dc3f06c3"
    "0924c1ce822976c9d3639d562d0baf0dc4afde24727d082fbec359b5471edf04"
    "1b"
)
signature = keys.Signature(vrs=(sig[64] - 27, int.from_bytes(sig[:32], "big"), int.from_bytes(sig[32:64], "big")))
print(signature.recover_public_key_from_msg_hash(digest).to_checksum_address())
# → 0x6E94c380d908531f9822035d6cc4c8D2B0186C9c   (the buyer)
```

The contract enforces this on chain as well: `debitChannel` reverts with `InvalidSignature` unless
the recovered signer is the channel depositor, so the success of transaction 4 is itself the proof.

## What this proves, and what it does not

**Proved.** A capability was invoked through the Hub, priced at $0.08, authorized by a signature
that binds the payer, the hub, the amount and a single-use receipt id, and settled in real USDC on
Base mainnet. The escrow can be read by anyone and says the same thing this page says.

**Not proved.** Not that anyone wanted the capability: the buyer wallet is ours and we funded it.
Not that the *result* was correct — the payment layer authenticates who said what, not whether it
was true; that is the job of the verification tier
([Metis](https://metis.modelmarket.dev), [AWR receipts](awr-receipts.md)). Not that the flow is
autonomous end to end: steps 4 and 5 were driven by an operator script
([`scripts/first_paid_invoke.py`](../scripts/first_paid_invoke.py)), because the production escrow
bridge runs with `may_broadcast: false`.

## The run that did not settle — and why it is here

Nine days later the same buyer wallet bought two live physical-world readings through the Hub —
`gaia.weather.read@v1` (28.6 °C, 60 % RH, 1009.4 hPa, Open-Meteo) and `gaia.quake.read@v1` (M5.0,
10 km depth, USGS) — with two signed DebitAuthorizations for $0.01 each. Both invokes returned 200
with Ed25519 attestations. **No USDC moved:** the production escrow bridge had no submit key that
day, so `debitChannel` could not run, and the deposit was released with
[`refundChannel`](https://basescan.org/tx/0x984aa375f79ccbfaea3dd10db23a75d988daa0a4db97bc7fd2c32bc92abebfc2)
rather than left stranded. The full record, including that failure, is in
[the on-chain journal §3l](onchain-journal.md).

A payment page that only shows the runs that worked is a brochure. The journal is the primary
source; this page is the short version of one entry in it.

## Reproduce it with your own wallet

```bash
git clone https://github.com/alexar76/aicom && cd aicom
python scripts/first_paid_invoke.py --discover "weather"                      # what is on sale today
python scripts/first_paid_invoke.py --capability gaia.weather.read@v1 \
  --hub https://modelmarket.dev --rpc https://mainnet.base.org --deposit 1.0
```

You will need a Base wallet holding at least **$1.00 USDC** — the escrow's `MIN_DEPOSIT`, regardless
of how little you intend to spend — plus a few cents of ETH for gas, and `openChannel` needs roughly
200k gas because of the USDC `transferFrom`. Only the amount you actually consume is debited; the
rest comes back through `settleChannel`, or through `refundChannel` if the hub never debits.

## A note on where receipts live

The Hub serves a receipt for a recent invoke at
`https://modelmarket.dev/ai-market/v2/p/provenance/receipt/<receiptId>`, but that endpoint no longer
returns this one — the hub database has been rotated since July. The durable copy of the receipt is
the one the escrow consumed: `receiptId` and the buyer's signature are in the calldata of
transaction 4 and will still be there when the hub, the company and this page are gone. That is the
point of putting the receipt id in the signed struct rather than only in a log line.
