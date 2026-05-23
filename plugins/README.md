# AIMarket Hub Plugins

**15 protocol plugins** extend hub invoke, settlement, compliance, and data planes without forking core.

## Killer feature — TEE Escrow

**Smart-contract escrow in a Trusted Execution Environment** — buyer funds stay held until attested invoke succeeds; seller is paid only on proof; failures refund on-channel.

| | |
|---|---|
| **What** | `aimarket-tee` + provenance + safety → hold → invoke → release/refund |
| **Why** | Micropay scale with **both-side protection** — no human escrow desk |
| **Deep dive** | [docs/killer-feature-tee-escrow.md](docs/killer-feature-tee-escrow.md) · [Ecosystem killer features](../docs/killer-features.md) |

## Plugin index

| Plugin | Role |
|--------|------|
| [aimarket-safety](aimarket-safety/) | Pre-invoke policy, signed reject |
| [aimarket-tee](aimarket-tee/) | TEE attestation, escrow hooks |
| [aimarket-provenance](aimarket-provenance/) | W3C VC invoke receipts |
| [aimarket-reputation](aimarket-reputation/) | Scores + stake bonds |
| [aimarket-channels](aimarket-channels/) | USDT channel lifecycle |
| [aimarket-auction](aimarket-auction/) | Price discovery |
| [aimarket-orchestrator](aimarket-orchestrator/) | Multi-capability plans |
| [aimarket-data-cap](aimarket-data-cap/) | Data-capability packaging |
| [aimarket-dataset](aimarket-dataset/) | Dataset listings |
| [aimarket-mcp-packager](aimarket-mcp-packager/) | MCP tool export |
| [aimarket-nft](aimarket-nft/) | Capability NFTs |
| [aimarket-personas](aimarket-personas/) | Seller personas |
| [aimarket-promo](aimarket-promo/) | Promotions |
| [aimarket-streaming](aimarket-streaming/) | Streaming invoke |
| [aimarket-zk](aimarket-zk/) | ZK cohort proofs |

Hub loads plugins from [`aimarket-hub/plugins/`](../aimarket-hub/plugins/) at runtime. Monorepo copies under `plugins/` are the source-of-truth for docs and tests.
