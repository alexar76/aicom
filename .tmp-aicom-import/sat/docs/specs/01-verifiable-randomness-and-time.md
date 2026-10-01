# Spec 01 — Agent-Native Verifiable Randomness & Time

**Status:** draft · **Owner:** ecosystem · **Depends on:** oracle-core, AIMarket Hub v2, AIMarketEscrow (Base)

## 0. Positioning — focus area
Sell two things autonomous agents constantly need and **cannot fake themselves**:
- **Verifiable randomness** (Platon) — unbiasable, signed entropy for fair selection, commit-reveal,
  leader election, sampling, raffles, anti-MEV ordering.
- **Verifiable time / delay** (Chronos) — a Verifiable Delay Function (VDF): a proof that real
  sequential work (≈ wall-clock time) elapsed, for fair ordering, timed reveals, proof-of-elapsed-time.

**Wedge vs incumbents (e.g. Chainlink VRF):** *agent-native* — pay-per-call in USDC, **no signup, no
KYC, no dashboard**, discovered + called over **MCP** by an autonomous agent, and **cheaper** (L2
gas). The output is **independently verifiable**, so the pitch is "verify it yourself," not "trust us."

## 1. Capabilities (grounded in the live oracles)
| capabilityId | price (USD) | input | output | status |
|---|---|---|---|---|
| `platon.random@v1` | 0.004 | `{num_bytes, client_seed?}` | `{random_hex, proof{state_hash,tick,timestamp,entropy_commitment}, signature}` (Ed25519) | **live** |
| `platon.beacon@v1` | 0.004 | `{}` | public round beacon (same proof/sig shape) | **live** |
| `platon.commit@v1` | 0.004 | `{}` | commit half of a commit-reveal | **live** |
| `platon.ask@v1` | 0.003 | `{question}` | entropy-derived answer | **live** |
| `chronos.eval@v1` | 0.010 | `{seed, difficulty T (1..1e6)}` | `{scheme, g, y=g^(2^T), proof{pi,l}, modulus}` (Wesolowski VDF, RSA-2048) | **live** |
| `chronos.verify@v1` | 0.001 | `{g, y, T, proof}` | `{valid}` | **live** |
| **`platon.verify@v1`** | ~0.001 | `{random_hex, proof, signature}` | `{valid}` | **TO BUILD** (gap §6) |

Source of truth: `oracles/oracles/platon`, `oracles/oracles/chronos`, declared via
`oracle-core` `OracleSpec`/`Capability`; invoked today by the relayer
(`lottery/relayer/ailottery_relayer/oracles.py`).

## 2. Verifiability — the actual differentiator
**Platon randomness** is authenticated by an **Ed25519 signature** over `(random_hex ‖ proof)` by the
oracle signer; the consumer verifies it against the **signer public key published in the signed Hub
manifest**. The `entropy_commitment` + `state_hash` bind the value to the oracle's chaotic state at
`tick`/`timestamp` (commit-reveal-safe).

**Chronos VDF** output satisfies `y = g^(2^T) mod N` with a Wesolowski proof `(π, l)` checkable in **one
exponentiation** — via `chronos.verify@v1` (off-chain) **or on-chain** (`lottery/contracts/src/ChronosVDF.sol`,
already used by the lottery). The delay is *unforgeable*: producing `y` requires `T` sequential
squarings (no GPU shortcut), so a valid proof attests that real time/work elapsed.

> The product promise: **outputs are checkable without trusting the oracle** — off-chain in one call,
> and (Chronos) on-chain in one `verifyEquation`.

## 3. Discovery — how an external agent FINDS it
Two surfaces, same capability:

1. **Federated Hub manifest** (exists): `GET /ai-market/v2/manifest` (Ed25519-signed) lists
   `platon.random@v1`, `chronos.eval@v1`, … with `input_schema`, `output_schema`,
   `price_per_call_usd`, `trust_score`; searchable by `intent="verifiable randomness"`.
2. **MCP server** (to build, §6): a FastMCP passthrough exposing the capabilities as **MCP tools**,
   listed on **Glama** + MCP registries. This is the agent-native discovery channel — an agent adds
   the server and immediately sees the tools.

**Gaps to close (spec'd in §6):** advertise the capabilities + a `/ai-market/v2/prices` bulk endpoint
in a **signed** `/.well-known/ai-market.json`; advertise the MCP server there too.

## 4. MCP tool surface (the storefront)
The passthrough MCP server exposes (names chosen for agent legibility; rich param descriptions keep
the Glama TDQS score high — see [[glama-mcp-score-maintenance]]):

```jsonc
// tools (each maps 1:1 to an oracle capability via oracle_core.Protocol.invoke)
{ "name": "get_random",
  "description": "Unbiasable, Ed25519-signed verifiable randomness. Returns random bytes + a proof you can verify. Pay-per-call (~$0.004 USDC).",
  "input_schema": { "num_bytes": "int 1..1024", "client_seed": "optional hex (domain separation)" } }
{ "name": "get_randomness_beacon",
  "description": "Latest public randomness beacon (shared across callers in a round). ~$0.004." }
{ "name": "verify_random",
  "description": "Verify a Platon randomness output (random_hex+proof+signature) against the published signer key. ~$0.001.",
  "input_schema": { "random_hex": "hex", "proof": "object", "signature": "ed25519 sig" } }
{ "name": "compute_vdf",
  "description": "Verifiable Delay Function: proves T sequential squarings (≈ elapsed time) over RSA-2048. Returns y=g^(2^T) + Wesolowski proof. ~$0.01.",
  "input_schema": { "seed": "hex", "difficulty": "int 1..1000000 (T)" } }
{ "name": "verify_vdf",
  "description": "Verify a VDF proof in one exponentiation. ~$0.001.",
  "input_schema": { "g": "hex", "y": "hex", "T": "int", "proof": "object" } }
```

Payment is handled by the server under the hood (§5); the calling agent just invokes the tool.

## 5. Payment & settlement (the cash register → flywheel)
Per-call over the **AIMarket v2 micropayment channel** (USDC on Base; escrow
`AIMarketEscrow`):
1. `POST /ai-market/v2/channel/open {deposit_usd}` → `channelId` (+24h expiry).
2. `POST /ai-market/v2/invoke {capabilityId, input}` with `X-Payment-Channel: channelId`.
3. Hub returns a **signed Ed25519 receipt** + `price_usd`.
4. On-chain debit: `debitChannel(channelId, amount, receiptId, deadline, sig)` (EIP-712), the path
   we tested in [the journal](../onchain-journal.md).
5. `channel/close` → settle used to the hub, refund remainder to depositor.

**Routing fee** (`routing_fee_bps`, default 100 = 1%) is the slice that funds the commons (UBI /
oracle pay / gas) — the flywheel fuel. The MCP server opens/settles channels for the agent and must
expose its **wallet/onboarding** (key per chain, USD↔token conversion) — a tracked gap (§6).

**Pricing note (competitive):** at $0.004/random and $0.01/VDF on cheap L2 settlement, the agent-native
offer undercuts human-centric VRF on per-call cost while adding MCP discoverability and self-verify.

## 6. Engineering backlog to ship this (gap → task)
1. **Build `platon.verify@v1`** — so consumers verify Platon output in one call (currently only Chronos
   has `verify`). [oracle-core capability + handler]
2. **Publish Chronos canonical modulus `N` as hex** (not the label `"RSA-2048"`) so VDF verification is
   trustless without out-of-band knowledge of `N`.
3. ~~**Passthrough MCP server**~~ — **shipped:** [`alexar76/aimarket-oracle-gateway`](https://github.com/alexar76/aimarket-oracle-gateway) ([Glama](https://glama.ai/mcp/servers/alexar76/aimarket-oracle-gateway)); FastMCP tools from §4 → Hub invoke.
4. **Signed `/.well-known/ai-market.json`** that advertises capabilities + a `/ai-market/v2/prices`
   bulk endpoint + the MCP server URL.
5. **MCP consumer payment UX** — auto channel open/close, wallet bootstrap, USD↔USDC conversion.
6. **Signed per-receipt SLA** (p50 latency / success-rate attested in the receipt, not just the manifest).
7. **Quick-start docs** — "call verifiable randomness from your agent in 5 lines" (per SDK + raw MCP).

## 7. Acceptance criteria
- An external agent, with **only** the Glama listing, can: discover `get_random`, open a channel, call
  it, receive a signed result, and **verify it** — paying real USDC, with the routing fee landing in
  the commons. End-to-end, no human steps.
- Chronos `y` verifies on-chain via `ChronosVDF.verifyEquation` and off-chain via `verify_vdf`.

## 8. Out of scope / honest notes
- **Phase 3 (ZK)** has no oracle yet — see [specs/README.md](README.md).
- Real external **demand** is the true gate (cold-start): this spec makes us *consumable*; it does not
  by itself create buyers. Distribution (Glama, registries, target agent frameworks) is a separate track.
