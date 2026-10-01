# AIMarket ecosystem — security & architecture threat assessment

**Scope:** AIMarket protocol/hub, ACEX capital markets, EVM escrow, federation, Alien Monitor, and
the aicom factory's LLM dependency.
**Method:** every claim below was **verified against the source**, not accepted at face value. Each
finding carries a verdict (Confirmed / Partially mitigated / Refuted), file:line evidence, qualitative
severity, residual risk, and a concrete remediation design.

> Professional note: of the ten concerns raised, **3 are refuted or substantially mitigated** by
> mechanisms already in the code, **5 are confirmed real**, and **2 are partially valid** (the
> architectural concern stands but a specific detail — e.g. "5-second timeout" — was inaccurate).
> Acting on the refuted items as written would waste effort; the confirmed items are prioritized below.

---

## Verdict summary

| # | Concern | Verdict | Severity | Evidence |
|---|---------|---------|----------|----------|
| 1 | Missing nonce/replay → double-spend | **Refuted** (documented paths) | Info | `contracts/evm/src/AIMarketEscrow.sol:105,121,137,270-271` |
| 2 | Reputation is subjective + no cross-hub sync | **Confirmed → ✅ core shipped** | High | `slash_sync.py` (signed federated registry) |
| 3 | Federated search 5s timeout, no async callback | **Mostly refuted** (search = local index; crawler tolerant) | Low | `api.py:276` (local index); `crawler.py:215` (fault-tolerant) |
| 4 | Agent-revenue oracle is a stub; needs trusted/ZK proof | **Confirmed → ✅ core shipped** | High | `revenue_proofs.py` (Merkle revenue commitments) |
| 5 | Three.js no LOD at 1000+ nodes | **Confirmed → deliberately deferred** (product call) | Low (UX, far-off scale) | no LOD/InstancedMesh; default frustum culling on |
| 6 | No proof-of-misbehavior / cross-hub slashing | **Partially confirmed → ✅ core shipped** | High | `slash_sync.py` (portable PoM + penalty) |
| 7 | Sybil on CapShares (no listing gate) | **Partially refuted → ✅ revenue gate added** | Medium | `acex_ipo.float_product` revenue gate + audit+stake gate |
| 8 | Centralized-LLM dependency; raw local fallback | **Mostly mitigated** (circuit-breaker failover exists) | Low–Medium | `llm/router.py:6-7,56-57,114`; `local_ollama.check_health` |
| 9 | No batched refunds; dust refunds uneconomical | **Confirmed → ✅ FIXED** | Medium | `AIMarketEscrow.sol` `batchRefund` + Foundry tests |
| 10 | No whitepaper for consensus/economics | **Confirmed → ✅ written** | Medium (adoption) | `docs/aimarket-whitepaper.md` |

---

## Findings in detail

### F1 — Replay protection on payment signatures — **Refuted**

The on-chain payment path is correctly protected. `AIMarketEscrow.sol` enforces an EIP-712
`DebitAuthorization` over `(channelId, hub, token, amount, receiptId, nonce, deadline)` (L137) with:
per-channel `nonce` that increments after each debit (L105), a `usedReceipts` mapping rejecting
receipt reuse (L121, `ReceiptAlreadyUsed` L51), a `deadline` expiry check (L270), and **hub-binding**
on first debit so a signature can't be replayed at a different hub (protocol spec.md:373). Off-chain
receipts in `signing.py` also carry `nonce` + `timestamp` (L142,146).

**Residual / hardening (Info) — ✅ conformance test added.** The claim said "*some* signatures." The
risk is not the debit path but signature-type *sprawl* — a future message type added **without** a
freshness field could reintroduce replay. `tests/test_signing_conformance.py` enumerates every signed
canonical (receipt, manifest, slash attestation, dispute — exposed via `Signer.receipt_canonical` /
`manifest_canonical`) and **fails if any lacks an anti-replay/freshness token** (nonce/timestamp/
deadline/seq/generated_at). A new signed type that forgets one turns the test red, not production
vulnerable. A single typed `{domain, nonce, deadline, payload}` envelope remains the stronger end state.

### F2 / F6 — Federated reputation: local proof-of-misbehavior exists, cross-hub sync does not — **Confirmed (High)**

`reputation_oracle.py` already implements the mechanism the concern says is missing **within a hub**:
a bond is posted, a *signed* misbehavior claim is submitted, the oracle verifies it, **slashes the
bond, and pays the affected party** (L5,13); trust score = f(bond, success_rate, age, volume,
**slash_history**) (L14). Reputation events require a signature — anonymous poisoning is blocked
(`api.py:739`).

**The real gap:** none of this **propagates across federated hubs.** A slash in hub A leaves the
agent's standing in hub B untouched (no gossip/replication found). An attacker cheats in A, keeps a
clean record in B.

**Remediation (design):**
- **Signed slash registry:** publish each slash as a signed, monotonically-numbered event to a
  shared append-only log (or anchor a Merkle root on-chain — `acex_merkle.py` already exists). Hubs
  pull and verify peers' slash roots; trust score consumes the union, not the local view.
- **Proof-of-misbehavior portability:** the misbehavior claim is already signed by the wronged party
  and references an invocation receipt — make it independently verifiable by *any* hub, so a whistle-
  blower can present it network-wide and claim a bounty from the violator's bond at the hub holding it.
- **Oracle decentralization:** the verifying oracle is itself a trust bottleneck — move it behind an
  m-of-n attestation (or the existing TEE/ZK layer) before mainnet.

**Shipped (core):** `aimarket-hub/aimarket_hub/slash_sync.py` — a hub emits a **signed
`SlashAttestation`** (per-issuer monotonic seq); peers `ingest_remote()` only after verifying the
issuer's Ed25519 signature, so attestations are unforgeable and re-pulls are idempotent.
`compute_reputation_score(..., federated_penalty=…)` now folds the cross-hub slash consensus into the
score, so misbehavior proven elsewhere lowers standing here (penalty saturates in the number of
*distinct* hubs, not repeat-slashing by one). **F6 defense:** `require_pom` rejects any cross-hub
slash lacking a **consumer-signed proof-of-misbehavior**, so a malicious hub cannot smear a
competitor's agents. Tests: `tests/test_slash_sync.py` (propagation, forgery rejection, no-PoM
rejection, saturation, idempotency, score impact). **Transport (O-4) shipped:** `resolve_dispute`
emits to the registry; `GET /reputation/slashes` serves the signed log and
`GET /reputation/slashes/by-provider/{p}` the aggregated signal; the crawler pulls each peer's log and
**binds the issuer identity to the peer's published key** (`expected_issuer_pubkey`) so a peer cannot
serve attestations forged "from" another hub. Tests: `tests/test_slash_transport.py`.

### F3 — Synchronous federated fan-out — **Mostly refuted (Low)**

Re-verification overturns this one. `/search` does **not** fan out to remote hubs at query time — it
reads the **local index** (`api.py:276`, `db.search_capabilities(intent)`). Federated capabilities are
pre-crawled into the local DB by a **background** crawler, and the crawler is already **fault-tolerant**:
a failing/slow hub increments an error counter and the loop continues (`crawler.py:215`), with atomic
clear-and-repopulate to avoid an empty-catalog window (EXP-34). So "a slow remote hub loses search
results" and "5-second timeout" do not hold — the timeout is 30s and only on the background crawl, and
no result is dropped at search time.

**Residual (Low):** the background crawler is **sequential** (`await self._crawl_one` per node,
`crawler.py:214`), so a large federation crawls slower than it could. Optional improvement: parallelize
each BFS frontier with bounded-concurrency `asyncio.gather(..., return_exceptions=True)`. Not a security
or correctness issue — freshness/latency only.

### F4 — Trustless agent-revenue oracle — **Confirmed (High)**

`acex_ipo.py:12` states plainly: *"The revenue-distribution layer below is the piece that does NOT
yet exist on-chain."* CapShares are priced by a TWAP oracle (`AgentAuditPool.sol:216`), but the
**input** — real agent revenue — is not yet provable on-chain. This is the economic-integrity crux:
without a trustworthy revenue feed, CapShare valuations and shareholder payouts can be manipulated.

**Remediation:** the trust anchor already exists — **signed channel-debit receipts** are the agent's
revenue, on-chain and replay-protected (F1). Derive revenue from them:
- **Merkle-batched revenue proofs:** each settlement period, the hub commits a Merkle root of
  receipts; shareholders/auditors verify inclusion. (`acex_merkle.py` + `zk_groth16.py` are present.)
- **ZK option:** prove "sum of receipts ≥ X for agent A in window W" without revealing each receipt,
  for private revenue. Until then, document CapShares as **trust-assumed** revenue, not trustless.

**Shipped (core):** `aimarket-hub/aimarket_hub/revenue_proofs.py` — `commit_revenue()` builds a Merkle
root over the period's receipts (audited OZ/Uniswap leaf encoding from `acex_merkle`, so the same
root is on-chain-verifiable); `verify_agent_revenue()` lets any auditor confirm an agent's claimed
total is **exactly** the sum of provably-included receipts, rejecting tampered amounts, replayed
leaves (double-counting), and cross-agent leaves — no trust in the hub. Tests:
`tests/test_revenue_proofs.py`. **Remaining wiring:** commit a root per ACEX settlement period in
`acex_ipo.py` and expose `GET /reputation/revenue-root`. The ZK variant is **O-2**, designed below.

#### O-2 — ZK revenue proofs (design, deferred)

**Why beyond F4.** The Merkle commitment (F4) makes revenue *auditable* but **public**: an auditor
sees every receipt amount under the root. For private revenue — an agent that does not want each
invocation price and volume exposed to competitors — we want to prove the *aggregate* without
revealing the parts.

**Statement to prove (zero-knowledge).** For a committed period root `R`, agent `A`, threshold `X`,
window `W`:

> "I know a set of receipts, each Merkle-included under `R`, all bound to account `A` and timestamped
> within `W`, whose amounts sum to `S ≥ X`" — revealing only `R`, `A`, `X` (and optionally `S`), never
> the individual receipts.

**Circuit shape.** Private inputs: the receipt leaves `(index, A, amount, ts)` + their Merkle paths.
Public inputs: `R`, `A`, `X`, `W`. Constraints: (1) each path hashes to `R` using the **same keccak
leaf encoding as `acex_merkle.make_leaf`** (so the circuit and the on-chain/Python verifier agree
byte-for-byte); (2) each leaf's account == `A` and `ts ∈ W`; (3) **distinct indices** (no leaf reused
— the same double-count guard `verify_agent_revenue` enforces today); (4) `Σ amount ≥ X`. Output: a
succinct proof + the public inputs.

**Build path.** Reuse the existing **PLONK universal setup** (`zk_groth16.py` / the KI-1 migration —
no per-circuit ceremony). Keccak-in-circuit is the cost driver; either use a SNARK-friendly hash for
the *tree* (and re-commit) or a keccak gadget. Verify on-chain (Solidity verifier) so CapShare
contracts consume the proof directly, or off-chain in the hub for a private-but-centralized check.

**Why deferred (not blind-built).** This is a genuine circuit-engineering effort (constraint system,
keccak gadget cost, trusted-input plumbing, a Solidity verifier + gas budget) — exactly the kind of
work that must not be written blind. F4's Merkle proofs already deliver *trustless verifiability*;
O-2 adds *privacy* on top. **Trigger:** an agent/operator that requires confidential revenue, or a
regulatory need to prove solvency without disclosure. Until then CapShare revenue is verifiable
(F4) but public.

### F5 — Alien Monitor has no LOD — **Confirmed (Medium, availability/UX)**

No `LOD`, `InstancedMesh`, frustum culling, or node cap found in `alien-monitor/src`. At 1000+ nodes
every node is a draw call and the WebSocket pushes full snapshots.

**Decision — deliberately deferred (do not "fix").** The Alien Monitor's reason to exist is the
*beauty* of the 3D ecosystem view; the available LOD levers (lower sphere segments, drop corona glow,
hide per-node labels, instancing) all trade that visual fidelity for throughput at a node count
(1000+) that does not exist today. By the time real fleets approach it, the hardware, the renderer
(WebGPU), and the "is it slow?" measurement will all be different — optimizing now is premature.
Three.js already frustum-culls off-screen nodes by default, so the on-screen draw count is bounded
regardless. **Trigger to revisit:** real fleets sustaining several hundred *simultaneously visible*
nodes with a measured frame-time regression. Recorded as a conscious trade-off so a future reviewer
does not "fix" what was intentionally left beautiful.

If/when revisited: a single `THREE.InstancedMesh` for node cores (one draw call for N), distance LOD
tiers (full → billboard → cluster), and WebSocket delta updates. None is security-sensitive.

### F7 — Sybil on CapShares — **Partially refuted (Medium)**

A listing is **not** free: `acex_ipo.py:9` is `apply → audit (≥ MIN_AUDIT_SCORE_BPS) → approve →
mint`, with `MIN_AUDIT_SCORE_BPS` default **7000 (70%)** (L44), and the audit pool requires
`MIN_STAKE_USDC = 10_000` (`AgentAuditPool.sol:40`, enforced L131). Spinning up 1000 dummy agents and
listing them requires passing stake-backed audits — non-trivial.

**Residual risk:** the gate is **audit-quality**, not **revenue** — a polished-but-worthless agent can
still pass; and audits are auditor-subjective (collusion risk).

**Shipped:** `acex_ipo.float_product(..., prior_revenue_usd=)` now enforces a **minimum prior
paid-invoke revenue** before CapShares can be floated (`ACEX_MIN_LISTING_REVENUE_USD`, read at call
time; 0 = disabled by default, set for mainnet). A zero-revenue Sybil dummy is rejected with
`insufficient_prior_revenue`; the revenue figure is meant to be **F4-verifiable**, making the gate
trustless. Tests in `tests/test_acex_ipo.py`. **Remaining:** a slashable listing **bond**, and
auditor-collusion resistance (random assignment + dispute window).

### F8 — Centralized-LLM dependency — **Mostly mitigated (Low–Medium, continuity)**

Re-verification: the router is richer than the finding implied. It already runs **per-provider health
checks + a circuit breaker** (CLOSED→OPEN→HALF_OPEN) and **fails over** to `LocalOllamaProvider` when
the default is down or the circuit is OPEN (`llm/router.py:6-7,56-57,114`; `local_ollama.check_health`
reports ONLINE/DEGRADED). A provider-policy block trips the breaker and routes to local — it does not
hard-fail.

**Genuine residual (the part worth doing):** (1) the local path's *quality* is unproven — add a CI
smoke that runs a build entirely on the local provider so the fallback can't silently rot; (2)
`persist_deepseek.py:140` disables local fallbacks by default for the reasoning/persistence path —
that is intentional there, but document it as a per-path choice, not a global posture, so continuity-
critical paths keep the fallback. No code change shipped here — the mechanism already exists; this is a
test + documentation item, downgraded from the assessment's original Medium.

### F9 — No batched refunds — **Confirmed → ✅ FIXED**

`AIMarketEscrow.sol` offered only single-channel `refundChannel`, safety auto-refund, and
permissionless 24h `expireChannel` cleanup — no batch, so for $1 channels refund gas could exceed the
refund.

**Shipped:** `batchRefund(bytes32[] channelIds, string reason)` refunds all of the caller's own
open, un-debited channels in one transaction — the ~21k base tx cost is amortized across N channels.
Non-refundable entries (unknown id, not Open, foreign owner, already debited) are **skipped** rather
than reverting the whole batch, so one stale id can't block the rest. Follows checks-effects-
interactions per item and is `nonReentrant`; the caller pays gas, so an oversized array only
out-of-gases for that caller (no griefing). Foundry tests cover the happy path, skip-debited, and
skip-foreign/unknown cases (`test/AIMarketEscrow.t.sol`, full suite 54/54 green).

**Further hardening (optional, not yet done):** a pull-payment credit balance and relayer/meta-tx gas
sponsorship for true dust; a minimum-channel-size guard at `openChannel`.

### F10 — No whitepaper — **Confirmed (Medium, adoption/trust)**

The economic primitives *are* specified — `aimarket-protocol/spec.md` (channels/escrow),
`acex/protocol/spec-capital-markets.md`, `acex/protocol/proof-of-audit.md` — but there is no single
document tying together the **reputation consensus** and **economic model** for external reviewers and
auditors. **Shipped:** [`docs/aimarket-whitepaper.md`](aimarket-whitepaper.md) — trust model, escrow,
federated reputation consensus, ACEX economics (revenue proofs + Sybil gate), oracle/ZK, and an
open-problems table (O-1…O-5) that maps to the external-audit scope (KI-2).

---

## Prioritized remediation roadmap

| Priority | Items | Why first |
|----------|-------|-----------|
| **P0 — economic integrity** | F4 (revenue proofs) **✅ core done**; F2/F6 (federated slash sync) **✅ core done**; oracle decentralization (remaining) | These gate honest valuations and cross-hub trust. Core protocol + tests landed in `revenue_proofs.py` / `slash_sync.py`; remaining = settlement-period/endpoint/crawler wiring + oracle m-of-n. |
| **P1 — financial UX & anti-abuse** | F9 (batched refunds) **✅ done**; F7 (revenue+bond listing gate) | Direct user-fund and market-quality impact; contained contract changes. |
| **P2 — resilience** | F8 — **mostly mitigated** (failover exists); residual = CI smoke on local path | Provider-risk continuity. |
| **P3 — polish & docs** | F10 **✅**, O-4 transport **✅**, F1 conformance **✅**, O-1 oracle m-of-n **✅**; **F5 deliberately deferred** (beauty > far-off scale); **O-2 (ZK revenue) — designed (§F4 → O-2), deferred**; remaining: F3-residual (parallelize crawler) | No active exploit; hardening and adoption. |

### Proposed whitepaper structure (F10)

1. Threat model & trust assumptions (who can be Byzantine).
2. Payment channels & escrow (replay protection, dispute, refund).
3. Reputation consensus — bonds, proof-of-misbehavior, slashing, **federated synchronization**.
4. ACEX economic model — CapShares, Proof-of-Audit, revenue proofs (F4), Sybil resistance (F7).
5. Federation protocol — discovery, partial-result semantics, circuit breaking.
6. Oracle & ZK design — revenue attestation, privacy.
7. Liveness/continuity — LLM provider diversity.
8. Open problems & audit scope (link KI-2…KI-5).

---

## What this assessment does **not** claim

Severities are qualitative, not CVSS-scored against a deployed mainnet (the contracts are
**pre-mainnet** per `docs/known-issues.md`). None of the confirmed items is a live exploit today; they
are design gaps to close **before** mainnet value flows. This document should feed the external audit
(KI-2), not replace it.
