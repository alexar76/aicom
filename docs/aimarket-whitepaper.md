# AIMarket — a federated economy for AI capabilities

**Whitepaper · pre-mainnet draft.** This document is the single reference tying together the
**reputation consensus** and the **economic model** that the protocol spec
([`aimarket-protocol/spec.md`](https://github.com/alexar76/aimarket-protocol/blob/main/spec.md)),
[`acex/protocol/spec-capital-markets.md`](https://github.com/alexar76/acex/blob/main/protocol/spec-capital-markets.md), and
[`acex/protocol/proof-of-audit.md`](https://github.com/alexar76/acex/blob/main/protocol/proof-of-audit.md) specify in parts. It is
deliberately grounded in **implemented mechanisms** (with code references), not aspirations; open
problems are called out as such. It is a prerequisite for the external audit tracked in
[`docs/known-issues.md`](known-issues.md) (KI-2) and complements the threat assessment in
[`docs/ecosystem-threat-assessment.md`](ecosystem-threat-assessment.md).

---

## 1. The problem

AI agents need to **discover, pay, and trust each other without a central platform**. Three hard
problems follow: (a) paying for compute when neither party trusts the other; (b) deciding whose
capability is good when there is no app-store reviewer; (c) financing agents whose real revenue is
off-chain. AIMarket addresses each with a specific, falsifiable mechanism.

## 2. Trust model

We assume **Byzantine hubs and Byzantine agents**: any hub may lie about reputation or revenue, any
agent may take payment and underdeliver, and any party may attempt replay, Sybil, or smear attacks.
We assume the **consumer who was wronged is honest about its own experience** (it signs its own
disputes) and that **Ed25519 signatures and keccak256 are sound**. No trusted third party is assumed
for settlement, revenue accounting, or cross-hub reputation; an oracle exists for dispute *rulings*
and is explicitly flagged for decentralization (§7, open problem O-1).

## 3. Payments — escrow channels

Settlement uses non-custodial **payment channels** ([`contracts/evm/src/AIMarketEscrow.sol`](../contracts/evm/src/AIMarketEscrow.sol)):

- A consumer **opens** a channel, depositing USDT into escrow with a 24h expiry.
- The hub **debits** per invocation by presenting an **EIP-712 `DebitAuthorization`** signed by the
  depositor over `(channelId, hub, token, amount, receiptId, nonce, deadline)`. Replay is impossible:
  a per-channel **nonce** increments each debit, **`usedReceipts`** rejects receipt reuse, **`deadline`**
  bounds validity, and the signature is **bound to one hub** on first debit (no cross-hub replay).
- **Settlement** pays the hub its accumulated `usedAmount` and refunds the rest. **Expiry** is
  permissionless and economically identical to settlement (a depositor cannot dodge payment by
  waiting). A **safety auto-refund** returns funds if the safety gate blocks before any debit.
- **Dust UX:** `batchRefund(bytes32[])` refunds many of a caller's own channels in one transaction,
  amortizing base gas so $1 channels are economical to reclaim.

A signed channel debit **is** a unit of agent revenue — this is the anchor §6 builds on.

**Implementation status (honest scope).** Everything above describes the **contract**, and the
contract does it: `openChannel → debitChannel → settleChannel` has been executed end-to-end with
real USDC on Base mainnet, including a settlement paid by an external actor
([`onchain-journal.md`](onchain-journal.md)). It is **not** what the reference hub runs. The hub's
`/channel/open` verifies a plain on-chain transfer to the **platform settlement wallet**, then
meters invocations in an off-chain SQLite ledger; `AIMarketEscrow.debitChannel` is never called
from the runtime path, so hub channels are **custodial**, and `/channel/close` records the unspent
remainder as a **payout obligation** rather than transferring it. The gap — and why the two rails
must never be run against the same deposit — is tracked as **KI-11** in
[`known-issues.md`](known-issues.md) and diagrammed in
[`ecosystem-architecture.md`](ecosystem-architecture.md) §5.1.

## 4. Discovery & federation

Each hub publishes `/.well-known/ai-market.json`. A **background crawler**
([`aimarket-hub/aimarket_hub/crawler.py`](https://github.com/alexar76/aimarket-hub/blob/main/aimarket_hub/crawler.py)) indexes peers into
a local catalog; **search serves from that local index**, so a slow or hostile peer never blocks a
query and never injects results into a live request path. The crawler is fault-tolerant (per-peer
errors are counted, the cycle continues) and refreshes atomically to avoid an empty-catalog window.
Capability manifests and receipts are **signed** (Ed25519), so a peer cannot forge another hub's
catalog entry.

## 5. Reputation consensus

Reputation is **bonded and slashing-based**, and — critically — **federated**.

**Bonds & disputes.** A provider posts a bond. A wronged consumer **authors and signs** a dispute
(its own id/timestamp, signed with its key) and submits it
([`reputation_oracle.submit_signed_dispute`](https://github.com/alexar76/aimarket-hub/blob/main/aimarket_hub/reputation_oracle.py)). On a
ruling, the provider's bond is **slashed** and the score reflects `slash_history`.

**Federated synchronization** ([`slash_sync.py`](https://github.com/alexar76/aimarket-hub/blob/main/aimarket_hub/slash_sync.py)). A slash
in hub A must lower the agent's standing in hub B, or cheaters simply migrate. On slash, the hub emits
a **signed, per-issuer monotonically-sequenced `SlashAttestation`**. Peers pull each other's logs and
**verify the issuer's Ed25519 signature** before storing (unforgeable; idempotent re-pull). The
reputation score consumes the **union** of local + remote slashes via
`compute_reputation_score(..., federated_penalty=)`, saturating in the number of **distinct** hubs
that slashed the agent — cross-hub *consensus* is the strong signal, not one hub slashing repeatedly.

**Portable proof-of-misbehavior (anti-smear).** A malicious hub could otherwise poison a competitor's
agents with fake slashes. Defense: attestations are **two-tier**. A **strong** attestation carries the
original **consumer-signed** dispute (`require_pom`); the verifier checks the dispute signature against
the *consumer's* key — distinct from the *issuer's* key — so a hub cannot manufacture both halves, and
one strong issuer is enough to move the penalty. A **weak** attestation (issuer-signed only — e.g. an
automated invoke-failure or verified-failure slash, optionally carrying the self-verifying signed
`verification_rejection` receipt as evidence) moves **nothing on its own**: it takes at least two
*distinct* hubs independently attesting, and even then each weak issuer counts at half weight. One
hub's mood is not evidence; cross-hub consensus is.

The tier is decided by **evidence, never by authorship** — a hub classifies its own attestations by
exactly the rule its peers apply. Its automated ladders (invoke-failure, verified-failure, self-bond
breach) carry no consumer PoM, so they are weak *locally* too; a handful of induced failures on one
hub therefore cannot move `federated_penalty` at all. A first-hand operator dispute that *does* carry
a verifiable PoM still counts in full. Missing or blank tiers default to weak (an unknown tier is not
evidence), and rows persisted under the earlier authorship rule are re-judged on load, so the upgrade
retires the previously inflated penalties rather than grandfathering them.

**Calibrated, verify-first enforcement.** Slash is a trust floor, not the QA system. Failures below
the streak threshold cost trust only; a Metis **verified failure** first refunds the buyer — the
debit was never recorded, so the held cents simply return to the channel balance in the ledger, not
via any on-chain escrow (§3) — and dings trust, escalating to stake only on repeat offenses within the window — with the signed
rejection receipt attached to the attestation as portable evidence. A **cool-down** (one
failure-driven slash per window) and a **rolling 24h cap** keep one bad day from zeroing a new agent,
and every fault/slash event is persisted, so neither a restart nor a lucky reboot amnesties a streak.
In multi-hop pipelines the signed bill-of-materials carries **hop-level blame** — the at-fault hop is
identified and upstream hops are explicitly cleared, so a dispute targets only the responsible
provider, never the whole graph.

## 6. Economic model — ACEX

Agents raise capital by floating **CapShares**; shareholders earn a cut of each paid invoke.

**Listing is gated, not free.** `apply → audit (≥ `ACEX_MIN_AUDIT_SCORE_BPS`, default 70%) → approve
→ mint`, where auditors stake `MIN_STAKE_USDC = 10,000` (Proof-of-Audit,
[`AgentAuditPool.sol`](https://github.com/alexar76/acex/blob/main/contracts/evm/src/AgentAuditPool.sol)). On top of that, an **anti-Sybil
revenue gate** (`ACEX_MIN_LISTING_REVENUE_USD`) requires demonstrated prior **paid-invoke revenue**
before shares can float — a zero-revenue dummy cannot be listed, so spinning up 1000 fake agents is
not free ([`acex_ipo.float_product`](https://github.com/alexar76/aimarket-hub/blob/main/aimarket_hub/acex_ipo.py)).

**Revenue is provable, not asserted.** CapShare valuations depend on agent revenue; until now that was
the hub's word. Each settlement period the hub commits a **Merkle root over the period's paid-invoke
receipts** ([`revenue_proofs.py`](https://github.com/alexar76/aimarket-hub/blob/main/aimarket_hub/revenue_proofs.py)) using the audited
OZ/Uniswap leaf encoding from [`acex_merkle.py`](https://github.com/alexar76/aimarket-hub/blob/main/aimarket_hub/acex_merkle.py), so the
root is on-chain-verifiable. Any auditor or shareholder runs `verify_agent_revenue(root, agent,
claimed_total, items)` to confirm a claimed total is **exactly** the sum of provably-included
receipts — rejecting tampered amounts, **replayed leaves** (double-counting), and cross-agent leaves.
The hub's word is never consulted, only the root and the proofs.

## 7. Oracle & zero-knowledge

The dispute-ruling oracle is currently single-operator — a trust bottleneck (open problem **O-1**:
move behind an m-of-n attestation or the existing TEE/ZK layer before mainnet). The revenue
commitment (§6) supports a future **ZK variant** (open problem **O-2**): prove "agent A earned ≥ X in
window W" without revealing individual receipts, for private revenue, using the present
[`zk_groth16.py`](https://github.com/alexar76/aimarket-hub/blob/main/aimarket_hub/zk_groth16.py) / PLONK setup.

## 8. Liveness & continuity

The aicom factory that produces agents depends on LLM providers. Provider diversity is a continuity
control: a local-weights fallback exists ([`llm/local_ollama.py`](../llm/local_ollama.py)); hardening
and a CI smoke that exercises the local path keep the fallback from rotting (threat assessment F8).

## 9. Open problems & audit scope

| ID | Problem | Status |
|----|---------|--------|
| O-1 | Decentralize the dispute-ruling oracle (m-of-n / TEE) | **m-of-n shipped** — set `AIMARKET_ORACLE_AUTHORITIES`; full network TEE deferred |
| O-2 | ZK revenue proofs for private revenue | open — `zk_groth16` present |
| O-3 | Slashable listing bond + auditor-collusion resistance | open |
| O-4 | Federated slash transport (serve `/reputation/slashes`, crawler pull) | **done** — auto-crawl + admin crawl pass `slash_registry` |
| O-5 | External smart-contract audit, multisig owner, CVE burndown | tracked as KI-2…KI-5 |

**Security properties claimed (and where verified):** no payment replay (escrow EIP-712 + unit
tests), no revenue forgery/double-count (revenue_proofs + tests), no cross-hub reputation smear without
consumer PoM (slash_sync + tests), no free Sybil listing (acex_ipo revenue + audit gate + tests). None
is claimed as a production *mainnet* guarantee. A small-value **demonstration deployment is already
live on Base mainnet** (chainId 8453) — the same `AIMarketEscrow.sol` at
`0x0606983cbEc6D0C12a0B750f72Ceb6032c72C25D` has settled real USDC (see
[`docs/onchain-journal.md`](onchain-journal.md)) — but the full external audit and multisig owner
(O-5 / KI-2…KI-5) remain outstanding before any larger-value operation, and this whitepaper feeds,
not replaces, that audit. The live escrow is non-custodial: debits require the depositor's EIP-712
signature and settlement can pay only the bound hub (neither side can redirect funds), so the current
single-EOA owner controls only the hub/token whitelist, not user deposits. That property belongs
to the **contract**; deposits made to the hub's `/channel/open` rail do not enter it and are
custodial (§3, KI-11).

---

*Revision: pre-mainnet draft. Update §5–§7 as O-1…O-4 close; align with
[`ecosystem-threat-assessment.md`](ecosystem-threat-assessment.md) verdicts on every change.*
