# Spec 04 — Further oracles (Lattice · Murmuration · Colony · Turing · Fermat · Ablation · Landauer · Percola)

**Status:** implemented in `aimarket-oracle-gateway` v0.2.0 · **Owner:** ecosystem · **Depends on:** oracle-core, the Oracle Gateway, AIMarket Hub

The remaining four oracles, productized the same way as Platon/Chronos/LUMEN: agent-native,
pay-per-call, MCP-discoverable, with a **verifiability story** for each. All are live oracle-core
capabilities (signed receipts) today; the work is exposing them as MCP tools + closing small gaps.
(No ZK oracle — see [README.md](README.md).)

## Capabilities (grounded in the live oracles)
| capabilityId | price | what it does | input → output | proposed MCP tool |
|---|---|---|---|---|
| `lattice.sequence@v1` | $0.002 | **Halton low-discrepancy (quasi-random) sequence** — fills space more evenly than RNG, so quasi-Monte-Carlo estimators converge faster. | `{count, dim, skip}` → `{sequence, points, dim, count, skip, bases}` | `get_quasirandom_sequence` |
| `murmuration.aggregate@v1` | $0.002 | **Robust consensus aggregation** of agent-submitted values — median, trimmed mean, Tukey biweight, DeGroot consensus. Outlier-/Byzantine-resistant. | `{values, trim}` → `{n, median, trimmed_mean, biweight, converged_value, iterations}` | `aggregate_values` |
| `colony.optimize@v1` | $0.005 | **TSP route optimization** (nearest-neighbour + 2-opt) with an **admissible lower bound + gap certificate** (how far from optimal the tour can be). | `{points, iterations}` → `{tour, length, lower_bound, gap, n, nn_length}` | `optimize_route` |
| `turing.bluenoise@v1` | $0.002 | **Blue-noise point set** (Mitchell best-candidate) — evenly spaced, no clumping; reproducible via `seed`. | `{count, candidates, seed}` → `{points, count, min_distance, candidates, seed, seed_source}` | `get_blue_noise` |

## Why an agent pays for these
- **Lattice** — unbiased even sampling for quasi-Monte-Carlo (pricing, integration, search) that
  converges faster than RNG; an agent that needs reproducible space-filling samples.
- **Murmuration** — combine many agents' estimates/votes into one trustworthy number that resists a
  few lying/outlier agents — the aggregation primitive for multi-agent consensus.
- **Colony** — routing/ordering/scheduling with a **proof of near-optimality** (the gap), so the
  caller knows how good the answer is without solving it themselves.
- **Turing** — evenly-distributed points (spawn placement, sampling, dithering, sensor layout)
  with no clustering.

## Verifiability (the differentiator, per oracle)
- **Lattice** — *fully deterministic*: re-derive the Halton sequence from `(count, dim, skip)` + the
  returned prime `bases`; bit-for-bit reproducible. Add `lattice.verify@v1` (recompute + compare).
- **Murmuration** — *deterministic from the input set*: re-aggregate `values` and confirm the
  statistics; the receipt should commit to the input `values` (same gap as LUMEN's graph commitment).
- **Colony** — *classical certificate*: recompute the admissible `lower_bound` (Σ cheapest incident
  edge / 2) and the tour `length`; the `gap` bounds optimality — verify without re-solving. (This is
  a quality certificate, **not** a ZK proof.)
- **Turing** — *reproducible*: re-run from the reported `seed` to reproduce the points; `min_distance`
  is independently measurable.

## Engineering backlog (gap → task)
1. ~~**Expose as MCP tools** in the gateway~~ — **done** in `plugins/aimarket-oracle-gateway` v0.2.0 (`aggregate_values`, `get_quasirandom_sequence`, `optimize_route`, `get_blue_noise`, plus Fermat/Landauer/Ablation/Percola).
2. **Input commitment in the receipt** for `murmuration.aggregate` (and `colony.optimize`) so the output binds to the exact input set/points (mirror the LUMEN graph-commitment fix).
3. **`lattice.verify@v1`** (and optionally `colony.verify@v1`) — one-call re-derivation/cert check.
4. Tiered pricing / guardrails for large `count` / `points` (bound compute + latency).

## Acceptance criteria
- Each capability is callable via the gateway as an MCP tool, priced, paid through a channel, with a
  result an external agent can independently re-derive or certify (per the verifiability column).

## Out of scope / honest notes
- These are lower-demand than VRF/time/reputation — productize after phases 1–3 prove external demand.
- No ZK oracle exists; the Colony "certificate" is a classical optimality bound, not zero-knowledge.
