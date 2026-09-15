# Oracle-as-a-Service — productization specs

Turning the ecosystem's oracles into **agent-native, pay-per-call capabilities** that external
AI agents **discover and consume** — the external-revenue engine for the
[circular economy](../onchain-journal.md). Each spec defines the capability, its **verifiable**
output, the **MCP tool surface** (how agents find + call it), pricing, and **on-chain settlement**
(the escrow channel whose routing fee fuels the flywheel).

## Why this is the revenue engine
- **Discovery layer = MCP + the federated Hub manifest.** External agents (Claude, etc.) add our
  MCP server, see the tools, and call them — no human signup. Listed on Glama + MCP registries.
- **Settlement layer = on-chain escrow channels** (AIMarketEscrow on Base) + the Hub routing fee.
  Each external call → USDC → routing fee → commons (UBI / oracle pay / gas) → recirculation.
- **The product = verifiable oracle outputs.** Not "trust our API" — outputs are cryptographically
  verifiable (Ed25519 signatures, Wesolowski VDF proofs, PageRank certificates), unlike
  trust-me APIs from human-centric incumbents (e.g. Chainlink VRF).

## Program (priority order)
**New here? → [quickstart-call-an-oracle.md](quickstart-call-an-oracle.md)** (discover → call → verify in ~5 lines).

| # | Spec | Capabilities | Status |
|--:|---|---|---|
| 1 | [Verifiable Randomness & Time](01-verifiable-randomness-and-time.md) | **Platon** VRF + **Chronos** VDF | drafted · `platon.verify@v1` + `chronos modulus_hex` shipped |
| 2 | [Reputation & Trust](02-reputation-and-trust.md) | **LUMEN** PageRank/EigenTrust | drafted · `lumen.score@v1` + `lumen.verify@v1` + convergence/commitment shipped |
| 3 | [MCP Payment & Security](03-mcp-payment-and-security.md) | payment models + threat model | drafted · gateway spending-cap security core shipped |
| 4 | [Further oracles](04-further-oracles.md) | **Lattice / Murmuration / Colony / Turing** | drafted |

> **Decision (owner): no ZK oracle.** The `PlonkVerifier` deployed on Base stays a standalone
> on-chain contract (the hub's input-validity proofs) — it is **not** productized as a service.
> Phase 3 instead productizes the remaining existing oracles (Lattice / Murmuration / Colony / Turing).

## Shared architecture (applies to every spec)
1. **Capability** — declared in `oracle-core` (`OracleSpec` + `Capability`), priced, Ed25519-signed.
2. **Discovery** — federated Hub manifest (`/ai-market/v2/manifest`, signed) **+ passthrough MCP server**
   [`aimarket-oracle-gateway`](https://github.com/alexar76/aimarket-oracle-gateway) (stdio FastMCP → Hub
   invoke) → [Glama](https://glama.ai/mcp/servers/alexar76/aimarket-oracle-gateway) + MCP registries.
3. **Payment** — AIMarket v2 micropayment channel: `open → invoke (X-Payment-Channel) → signed
   receipt → on-chain debit (EIP-712)`; Hub routing fee (default 1%).
4. **Verifiability** — every output independently checkable (off-chain and, where relevant, on-chain).

## Cross-cutting gaps to close (tracked per spec)
- ~~**No passthrough MCP server**~~ — **shipped:** [`alexar76/aimarket-oracle-gateway`](https://github.com/alexar76/aimarket-oracle-gateway) ([Glama](https://glama.ai/mcp/servers/alexar76/aimarket-oracle-gateway)); see [quickstart](quickstart-call-an-oracle.md).
- `/.well-known/ai-market.json` is **unsigned** and does not advertise capabilities/prices or the
  MCP server. Add a signed well-known + a `/ai-market/v2/prices` bulk endpoint.
- **Wallet/onboarding UX** for external agents (key format per chain, USD↔token conversion).
- Confirm SDK publish status (PyPI/npm/crates/pub.dev) — install-from-source may still be canonical.
