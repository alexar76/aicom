# Spec 03 — Paying for MCP-invoked capabilities (+ payment security)

**Status:** draft · **Owner:** ecosystem · **Depends on:** AIMarketEscrow (Base), AIMarket Hub v2, the Oracle Gateway

How a capability invoked through the MCP gateway gets **paid**, end to end, and the **threat model**
+ mandatory controls. Grounded in the live escrow (`debitChannel`/`settleChannel`/`refundChannel`/
`expireChannel`), the Hub (signed receipts + signed `/.well-known` + signed `/ai-market/v2/prices`),
and the gateway.

> **This is a TARGET design, not the shipped rail.** No runtime code calls
> `AIMarketEscrow.debitChannel` today — the contract has only been driven end-to-end by hand
> ([`onchain-journal.md`](../onchain-journal.md)). What the hub actually runs is a **custodial,
> off-chain metering ledger** funded by a verified transfer to the platform settlement wallet, whose
> close records the remainder as a payout **obligation** rather than refunding it. See
> [`ecosystem-architecture.md`](../ecosystem-architecture.md) §5.1 and **KI-11** in
> [`known-issues.md`](../known-issues.md). Everything in §2 below describes what the gateway must do
> once the escrow bridge exists (§6 "Next"), so do not read it as a description of production.

## 1. Two payment models (different trust)
| Model | Key custody | Flow | Use when |
|---|---|---|---|
| **Local stdio** *(default)* | The payer key lives **on the user's machine** (the MCP server is spawned locally by Claude Desktop/Cursor). The gateway signs `DebitAuthorization`s **locally** — the key never leaves the machine. | open channel → per call: hub quotes `price_usd` → gateway signs EIP-712 debit (tight deadline) → hub `debitChannel` → signed receipt → settle/refund on close. | dev, single agent, agent holds its own wallet. Same trust domain as the agent. |
| **Remote / hosted** | **No custody.** Agent deposits on-chain and **pre-authorizes** spend (debit vouchers bounded by a ceiling); the gateway only **relays** signed vouchers. | agent approves USDC + pre-signs bounded vouchers → gateway relays per call, never exceeding the ceiling → settle/expiry. | shared/hosted gateway; the gateway must never hold a user key. |

**Default = local stdio** (the MCP server already runs locally). The remote model is for a hosted gateway and must use pre-signed, bounded vouchers — never custody.

## 2. Channel lifecycle (what an agent experiences)
1. Approve USDC to the escrow + `openChannel(channelId, USDC, deposit)` — a small float (MIN $1).
2. Per call: `invoke {capability_id, input, X-Payment-Channel}` → hub returns `price_usd` + signed receipt.
3. Debit: depositor signs EIP-712 `DebitAuthorization{channelId, hub, token, amount(6dp), receiptId, nonce, deadline}`; hub `debitChannel`. `receiptId` single-use, `nonce` increments, first debit binds the hub.
4. Settle on close/low-balance/timer: `settleChannel` → used→hub, refund→depositor.
5. Recovery: `refundChannel` (pre-debit), or permissionless `expireChannel` after 24h. **No admin freeze/seize** — funds are always recoverable.

USD→token: prices are advertised in **USD**; the debit `amount` is **USDC 6-dp** (`round(usd * 1e6)`); the signed receipt's `price_usd` is authoritative.

## 3. Threat model & mandatory controls
From an adversarial red-team across three vectors. **C** = client/gateway-enforceable, **P** = protocol/contract, **O** = ops/governance.

### 3a. Key custody & prompt-injection-driven drain (the #1 MCP-specific risk)
An MCP tool call is driven by an LLM that can be manipulated (malicious tool output / injected content) into spending. Mitigations:
- **[C] Hard spending caps, client-side** — per-call cap + per-session/total budget enforced **in the gateway**; it refuses an invoke that would exceed them. The model *cannot* override this (it's not "trust the model", it's "the gateway won't sign/relay past the cap"). **Must-fix.**
- **[C] Price ≤ advertised check** — verify the hub's quoted `price_usd` against the pinned/advertised price (and the signed `/prices`); refuse overcharge (±tolerance). **Must-fix.**
- **[C] Key hygiene** — key never logged/echoed/embedded in tool output; held in memory only; ideally OS keychain/KMS, not a plaintext file. **Must-fix.**
- **[C] Local safety gate** — block known-dangerous capability ids / injected inputs before signing.

### 3b. On-chain payment integrity
- **[C] Verify the hub's Ed25519 receipt** before trusting `price_usd`/result; pin `signer_public_key` from the signed `/.well-known`. Fail-closed. **Must-fix.**
- **[P] Replay/double-spend** — `receiptId` single-use + per-channel `nonce` (contract-enforced). Gateway generates a fresh random `receiptId` per call; fetches the current nonce before signing. **Must-fix (nonce sync).**
- **[C] Tight deadline** — sign debits with `now+5min`, not 24h, so a stolen signature can't be replayed later. **Must-fix.**
- **[C] Hub field bound + validated** — the EIP-712 struct includes `hub`; gateway validates the signed hub == the intended hub (kills cross-hub signature replay). **Must-fix.**
- **[C] TLS / hub pinning** — pin the hub URL cert + signer pubkey to stop MITM/DNS hub substitution.

### 3c. Stuck funds & griefing
- **[P] Always recoverable** — `refundChannel` (pre-debit), `settleChannel` (depositor or bound hub), permissionless `expireChannel` after 24h; no admin trap. A malicious hub that never settles → depositor waits 24h and anyone expires it.
- **[C] Channel-state preflight** — read balance/nonce/status before each debit; **persist pending debits** so a gateway crash mid-flow can resume; settle open channels on graceful shutdown.
- **[O] Owner = multisig** — escrow owner must be an N-of-M Safe (≥3 signers); `setHubAuthorization` only via governance; audited hub whitelist. **Must-fix before mainnet value.**
- **[O] Sweep monitoring** — the hub's expiry-sweep job must be monitored/alerted; whitelist only canonical USDC/USDT (SafeERC20, no fee-on-transfer surprises).

## 4. What this spec ships now vs later
- **Now (this PR):** the **client-side security core** in the gateway — hard spending caps (per-call + total), price ≤ advertised guard, fail-closed when over budget/overcharged. This neutralizes the prompt-injection-drain and overcharge — the highest-severity risks — without custody.
- **Next:** the full channel lifecycle in the gateway (auto open/sign/settle/refund) with nonce-sync, tight deadlines, receipt-signature verification, and TLS/pubkey pinning; the remote pre-signed-voucher path; OS-keychain key storage.
- **Before any real-value mainnet payments (ops):** escrow owner → N-of-M multisig, audited hub whitelist, sweep monitoring, Base-Sepolia full-suite rehearsal.

## 5. Acceptance criteria
- A manipulated agent cannot spend beyond the configured per-call and total caps — the gateway refuses, regardless of what the model "decides".
- An overcharging hub (price > advertised + tolerance) is rejected client-side, no debit authorized.
- Funds in a channel are always recoverable (refund pre-debit; settle/expire otherwise) with no admin action.
