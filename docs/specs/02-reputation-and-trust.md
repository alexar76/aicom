# Spec 02 — Agent-Native Reputation & Trust (LUMEN)

**Status:** draft · **Owner:** ecosystem · **Depends on:** oracle-core, AIMarket Hub v2, AIMarketEscrow (Base)

## 0. Positioning
As the agent economy grows, every agent faces the same question before transacting: **"can I trust
this counterparty / this output?"** LUMEN answers it — a **reputation/trust score** computed by
PageRank / EigenTrust over a directed trust graph. This is the second focus area: a *growing*
market (trust infra for autonomous agents) that **compounds with our other rails** — LUMEN already
weights the lottery, and can gate escrow channels, prioritize Hub routing, and rank Mesh capabilities.

**Wedge:** agent-native (pay-per-call, MCP-discoverable, self-verifiable) **and composable** — LUMEN
is the trust layer the rest of the ecosystem (and external agents) reads from.

## 1. Capabilities
| capabilityId | price (USD) | input | output | status |
|---|---|---|---|---|
| `lumen.reputation@v1` | 0.005 | `{nodes (1..100k), edges [[i,j,w]…], damping=0.85}` | `{scores (N floats, Σ=1±1e-6), iterations, converged}` | **live** |
| **`lumen.score@v1`** | ~0.003 | `{graph, target_node}` | `{score, rank, percentile}` (single agent) | **TO BUILD** |
| **`lumen.verify@v1`** | ~0.002 | `{graph_commitment, scores, proof}` | `{valid}` | **TO BUILD** (gap §2) |

Source: `oracles/oracles/lumen`; invoked today by `lottery/relayer/ailottery_relayer/oracles.py`
(`lumen_reputation()` → per-agent odds bonus 0..5000 bps).

## 2. Verifiability — the hard part for reputation
Randomness/VDF outputs are self-contained; a reputation score is only meaningful **relative to the
input graph**. Today the **input edges are NOT in the signed receipt**, so a consumer cannot prove the
oracle scored the graph it claimed. To make LUMEN a *verifiable* product (not "trust our number"):

1. **Graph commitment in the signed receipt** — include `keccak256`/Merkle root of the canonical
   `(nodes, edges, damping)` so the consumer binds the score to an exact input.
2. **Convergence proof** — return `{delta, iterations, max_iterations, damping_used}` (not just a
   boolean `converged`), so a verifier can re-run the power iteration (or spot-check one step:
   `‖M·r − r‖ < ε`) and confirm the fixed point.
3. **`lumen.verify@v1`** — one call that re-derives the scores from `(graph_commitment, scores, proof)`
   and returns validity, so consumers don't need their own PageRank implementation.

> Product promise: "here is the trust score **and** a proof it's the correct PageRank of exactly this
> graph" — checkable without trusting LUMEN.

## 3. The data problem (LUMEN's moat — and its catch)
Reputation's value is the **graph** (network effect). Two product shapes:

- **(A) Pure compute service — shippable now.** The caller supplies their own trust graph; LUMEN
  returns a *verifiable* PageRank. No ecosystem data needed. Immediate, agent-native, undercuts
  rolling-your-own EigenTrust. **Start here.**
- **(B) Ecosystem trust ledger — the moat.** A persistent, ecosystem-wide trust graph built from
  **real signals** (successful paid invocations, escrow settlements, audit outcomes, Hub routing
  success) → LUMEN scores it → a queryable reputation of *every* agent over time. This is the
  complete product, but needs an **edge-collection pipeline**.

> ⚠️ **Catch (from the codebase):** today the ecosystem serves **scalar trust** (a hub `trust_score`
> from age/bond/success/volume), **not trust *edges*** — see [[reputation-graph-and-trust-data]].
> Shape (B) requires building the edge source (who-trusted-whom from real interactions). Shape (A)
> needs none of that and is the launch product.

## 4. MCP tool surface
```jsonc
{ "name": "get_reputation_scores",
  "description": "PageRank/EigenTrust trust scores over a directed trust graph you supply. Returns a score per node + a convergence proof. Pay-per-call (~$0.005 USDC).",
  "input_schema": { "nodes": "int 1..100000", "edges": "[[from,to,weight],…]", "damping": "0..1 (default 0.85)" } }
{ "name": "get_agent_trust",
  "description": "Single agent's trust score + rank + percentile within a supplied graph. ~$0.003." }
{ "name": "verify_reputation",
  "description": "Verify reputation scores against a graph commitment + convergence proof. ~$0.002." }
```
Names are agent-legible; rich param descriptions keep the Glama TDQS score high
([[glama-mcp-score-maintenance]]). Served by **[aimarket-oracle-gateway](https://github.com/alexar76/aimarket-oracle-gateway)** ([Glama](https://glama.ai/mcp/servers/alexar76/aimarket-oracle-gateway); Spec 01 §6 task 3 — shipped).

## 5. Payment & settlement
Identical rail to Spec 01: micropayment channel → invoke (`X-Payment-Channel`) → signed receipt →
on-chain `debitChannel` (EIP-712) → close; Hub routing fee → commons. **Pricing scales with graph
size** — power iteration on 100k nodes is real compute; spec **tiered pricing** (e.g. base ≤1k nodes,
surcharge per 10k) and a `max_nodes`/`max_iterations` guardrail to bound cost + latency.

## 6. Engineering backlog (gap → task)
1. **Graph commitment in the signed receipt** (keccak/Merkle root of nodes+edges+damping).
2. **Convergence proof** in output (`delta, iterations, max_iterations, damping_used`); stop clamping
   `damping` silently — echo the used value and reject out-of-range.
3. **`lumen.verify@v1`** capability (re-derive/spot-check the fixed point).
4. **`lumen.score@v1`** single-agent capability (score + rank + percentile).
5. **Tiered pricing + guardrails** (max nodes/iterations).
6. **MCP tools** in the passthrough server (§4).
7. *(Shape B, later)* **trust-edge collection pipeline** — derive who-trusts-whom from real paid
   invocations / escrow settlements / audits → persistent reputation ledger with cross-time
   consistency proofs.

## 7. Acceptance criteria
- An external agent supplies a graph via MCP `get_reputation_scores`, pays USDC, gets scores **+ a
  proof**, and `verify_reputation` confirms them — no human steps, routing fee lands in the commons.
- The lottery's existing LUMEN weighting is unchanged (back-compat with `lumen.reputation@v1`).

## 8. Out of scope / honest notes
- Shape (B) ecosystem trust ledger is **not** in the launch scope — it depends on the edge pipeline.
- Sybil/whale resistance: PageRank damping + the lottery's existing rep-bonus cap (+50%) limit
  manipulation, but a public reputation product needs an explicit **anti-sybil** section before
  external trust decisions rely on it — flagged for a follow-up security pass.
