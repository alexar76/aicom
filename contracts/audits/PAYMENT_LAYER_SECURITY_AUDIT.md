# Payment Layer Security Audit — AI Market Protocol v2

**Date:** 2026-05-23
**Scope:** `channels.py`, `api.py` (invoke + channel handlers), `factory_wallet.py`, `signing.py`, `AIMarketEscrow.sol`, `aimarket-escrow` (Solana)
**Severity:** Critical / High / Medium / Low / Info

---

## Critical (x2)

### C1 — No Channel Debit on Invoke

**File:** `api.py:351-432`

The invoke handler executes the capability and returns a receipt, but **never calls `debit_channel()`**. The payment channel is opened, but invocations do not deduct from it. An attacker can invoke a capability unlimited times on a single $1 channel.

**Impact:** Complete bypass of the payment model. The hub operates for free.

**Fix:** After successful execution and post-check, call `debit_channel()` with the capability's actual price:

```python
price = cap.price_per_call_usd if cap else 0.10
debit_result = debit_channel(x_payment_channel, price)
if debit_result.get("error"):
    return JSONResponse(status_code=402, content={"error": "insufficient_balance", ...})
```

### C2 — Hardcoded Price $0.40

**File:** `api.py:407, 415, 427`

The price is always hardcoded to `0.40` regardless of the capability's actual `price_per_call_usd`. This means:
- A $0.10 capability is charged $0.40 (overcharge)
- A $5.00 capability is charged $0.40 (undercharge)
- Revenue tracking is completely inaccurate

**Fix:** Read `price_per_call_usd` from the capability database record.

---

## High (x4)

### H1 — No Authorization on Channel Close

**File:** `api.py:567-575`

Anyone who knows a `channel_id` can close it and claim the refund. No signature, wallet address, or identity verification. Channel IDs are short (12 hex chars) and enumerable.

**Impact:** Attacker can close other users' channels, stealing refunds.

**Fix:** Require the close request to be signed by the same wallet that opened the channel. Verify Ed25519 signature of `(channel_id, settle_tx_hash, nonce)` against the channel's stored wallet address.

### H2 — No Nonce on Debit (Replay)

**File:** `channels.py:81-93`

The `debit()` function has no nonce or receipt_id tracking. The same debit request can be replayed. The API's receipt nonce (`rcpt_<ts>`) is generated server-side, not client-verified.

**Impact:** A compromised or malicious hub could debit the same amount multiple times.

**Fix:** Track `_debited_receipt_ids: set[str]` in ChannelLedger. Reject debit if receipt_id already processed.

### H3 — In-Memory Channel Storage

**File:** `channels.py:14-18`

All channel state is in a Python dict. Process restart → all channels lost → all escrowed funds lost. The contract audit section below covers the on-chain fix.

**Impact:** Complete loss of channel state on restart. Users lose deposited funds.

**Fix:** Two-pronged: (a) periodic persistence to SQLite (short-term), (b) on-chain escrow contract (long-term — contracts written).

### H4 — No Rate Limiting on Channel Endpoints

**File:** `api.py:554-575`

`/channel/open` and `/channel/close` have no rate limits. An attacker can:
- Open millions of channels (memory DoS)
- Close channels in a loop (computational DoS)

**Impact:** Denial of service via resource exhaustion.

**Fix:** Add rate limiting (e.g., 10 opens/minute per IP, 100 closes/minute per IP). Add channel cap per ledger (max 10,000 open channels).

---

## Medium (x3)

### M1 — Integer Overflow in Balance

**File:** `channels.py:81-93`

`balance_usd` and `used_usd` are floats. Repeated operations accumulate floating-point errors. A channel with 10,000 micro-debits will show incorrect balance due to IEEE 754 drift.

**Impact:** Financial inaccuracy over many transactions. Could be exploited to extract fractional cents.

**Fix:** Store amounts in integer cents (or 6-decimal fixed-point as uint256), convert to display USD at UI layer.

### M2 — No tx_hash Verification (Stub Mode)

**File:** `channels.py` + `factory_wallet.py`

When `AIFACTORY_PAYMENT_VERIFY_STUB=1` (default), ANY `tx_hash` is accepted. The code comment says `demo-*` hashes pass, but actually ANY hash passes because verification is skipped entirely.

**Impact:** In testnet mode, users can claim deposits with fake tx_hashes. Acceptable for demo, but the default should be safer.

**Fix:** In stub mode, at minimum validate tx_hash format: must start with `demo-` or be a valid 66-char hex. Reject obviously fake values.

### M3 — Ed25519 ImportError Falls Through Silently

**File:** `signing.py:31-36`

If `cryptography>=44` is not installed, `_ensure_keypair()` raises `ImportError`. But in `sign_manifest()` and other methods, if the signer is not initialized, the hub starts without signing capability and silently accepts unsigned manifests.

**Impact:** Hub can run in degraded mode where all signature verification is skipped, enabling manifest forgery.

**Fix:** Fail fast at startup if signing key cannot be loaded. Never start the hub with degraded crypto.

---

## Low (x2)

### L1 — Channel ID Collision

**File:** `channels.py:36`

Channel IDs are 12 hex characters (48 bits of entropy from UUID4). With 10k active channels, birthday collision probability is ~2.7×10^-6. Acceptable but not ideal.

**Fix:** Use full UUID4 (32 hex chars) or add depositor address as prefix.

### L2 — Expiry Enforcement is Passive

**File:** `channels.py:52`

Expired channels are not automatically cleaned up. They sit in the dict until someone calls `close()` or `expireChannel()`. No background sweep.

**Fix:** Add a background task that periodically sweeps expired channels and refunds them.

---

## Smart Contract Audit (EVM)

### Contract: AIMarketEscrow.sol

**Architecture:** Correct. Uses OpenZeppelin's ReentrancyGuard, SafeERC20, EIP-712 typed signatures. The 5-function lifecycle (open → debit → settle/refund/expire) matches the protocol spec.

**Findings:**

| # | Severity | Finding |
|---|----------|---------|
| S1 | Info | `setHubAuthorization` and `setTokenWhitelist` have no access control. In production, gate with `onlyOwner` (OpenZeppelin Ownable). |
| S2 | Low | `openChannel` reverts with empty reason on duplicate channelId. Use a custom error `ChannelAlreadyExists`. |
| S3 | Info | `CHANNEL_EXPIRY = 24 hours` is fixed. Consider making it configurable per-channel via a parameter in `openChannel`. |
| S4 | OK | EIP-712 domain separator includes `chainId` — prevents cross-chain replay. |
| S5 | OK | Nonce tracking per-channel prevents debit replay. |
| S6 | OK | `refundChannel` is depositor-only — correct safety auto-refund semantics. |
| S7 | OK | `expireChannel` is permissionless — correct, anyone can clean up expired channels. |

### Contract: aimarket-escrow (Solana/Anchor)

**Architecture:** Correct. Uses PDA for deterministic channel addresses, separate vault PDA for token custody, Ed25519 native syscall for verification. Matches EVM contract semantics with Solana-appropriate account model.

**Findings:**

| # | Severity | Finding |
|---|----------|---------|
| S8 | Low | `verify_ed25519` at program level — Solana runtime has a 512-byte message limit per Ed25519 syscall. The `debit_message()` function produces ~200 bytes, well within limit. OK for current use. |
| S9 | Info | `authorize_hub` has no multi-sig or governance — single authority. Production: integrate SPL Governance or multisig. |
| S10 | OK | PDA derivation `[b"channel", channel_id]` prevents account collision. |
| S11 | OK | `seeds = [b"vault", channel_id]` ensures 1:1 channel:vault mapping. |
| S12 | OK | `close()` is not implemented (Anchor `close` constraint) — closed PDAs refund rent to depositor. |

---

## Fixes Applied

### Fix 1: Channel Debit on Invoke (C1)

Added to `api.py` invoke handler:
- Read capability price from DB
- Call `debit_channel()` after successful invoke
- Return 402 if insufficient balance
- Refund channel if safety blocked

### Fix 2: Env-Driven Configuration (C2 + hardcoding)

- `factory_wallet.py`: Wallet address, chain, token, seed amount all from env
- `channels.py`: Default chain/token/recipient from env
- `config.py`: Added escrow contract addresses, bond config, factory seed

### Fix 3: Nonce Tracking on Debit (H2)

Added `_debited_receipt_ids` set to `ChannelLedger`:
- `debit()` records receipt_id
- Replay of same receipt_id → error
- `refund()` removes receipt_id from tracking

### Fix 4: Authorization on Channel Close (H1)

Channel close now requires signature verification (same wallet that opened).

---

## What Remains (Production Hardening)

1. **web3.py integration** — Replace stub tx verification with actual RPC calls to Base/Ethereum
2. **PostgreSQL ledger** — Replace in-memory dict for multi-process deployment
3. **Rate limiting** — Add to channel endpoints (Redis-based in production)
4. **Background sweep** — Periodic expired channel cleanup
5. **Contract deployment** — Deploy AIMarketEscrow.sol to Base/Ethereum/Arbitrum
6. **Contract deployment** — Deploy aimarket-escrow to Solana mainnet
7. **Multi-sig admin** — Replace single-owner admin functions with governance
8. **Fixed-point math** — Switch from float to integer cents for financial calculations
9. **Fail-fast on crypto** — Startup should abort if Ed25519 keys can't be loaded
