# Awesome list submissions — AI-Factory ecosystem

Order: **second tier, bottom → top** (as agreed).

| # | List | Our repos | How to submit |
|---|------|-----------|---------------|
| 1 | [e2b-dev/awesome-sdks-for-ai-agents](https://github.com/e2b-dev/awesome-sdks-for-ai-agents) | `aimarket-agent`, `aimarket-sdks` | PR to README |
| 2 | [slavakurilyak/awesome-ai-agents](https://github.com/slavakurilyak/awesome-ai-agents) | `aicom` (factory) | PR — alphabetical `### AI-Factory` |
| 3 | [punkpeye/awesome-mcp-servers](https://github.com/punkpeye/awesome-mcp-servers) | `aimarket-mcp-packager` (in `aimarket-plugins`) | PR — section **🔗 Aggregators** |

Later (top tier): `caramaschiHG/awesome-ai-agents-2026`, `e2b-dev/awesome-ai-agents` (Google Form), `taiyangc/awesome-web3-ai-agents`.

Canonical public URLs:

| Project | Repo | Live / docs |
|---------|------|-------------|
| AI-Factory | https://github.com/alexar76/aicom | https://magic-ai-factory.com |
| AIMarket Agent (Python) | https://github.com/alexar76/aimarket-agent | PyPI `aimarket-agent` · hub https://modelmarket.dev |
| AIMarket SDKs | https://github.com/alexar76/aimarket-sdks | Dart (alpha), TS/Rust stubs |
| AIMarket Protocol | https://github.com/alexar76/aimarket-protocol | `/.well-known/ai-market.json` |
| AIMarket Hub | https://github.com/alexar76/aimarket-hub | https://modelmarket.dev |
| Hub plugins (incl. MCP packager) | https://github.com/alexar76/aimarket-plugins | https://modelmarket.dev/plugins/demo |
| ACEX | https://github.com/alexar76/acex | Capital markets for agents |
| AI Service Mesh | https://github.com/alexar76/ai-service-mesh | Web3 agent discovery / escrow |
| AIMarket Courses (10 academies) | https://github.com/alexar76/aimarket-courses | https://alexar76.github.io/aimarket-courses/ |
| Alien Monitor | https://github.com/alexar76/alien-monitor | 3D observability |

---

## 1. e2b-dev/awesome-sdks-for-ai-agents

**Placement:** after `## [Langfuse]` block (SDKs for agent commerce / federation), or alphabetically before `## [SID]`.

**Do not** list the factory monorepo here — this list is SDKs only.

### Patch A — AIMarket Agent (Python SDK + CLI)

```markdown
## [AIMarket Agent](https://github.com/alexar76/aimarket-agent)
Python SDK and CLI for the open [AIMarket Protocol v2](https://github.com/alexar76/aimarket-protocol): discover federated capabilities, open pre-funded payment channels (HTTP 402), invoke with safety-gated receipts, and settle with a signed bill of materials. Works against any compliant hub (reference: [modelmarket.dev](https://modelmarket.dev)).

### Links
- [GitHub](https://github.com/alexar76/aimarket-agent)
- [PyPI](https://pypi.org/project/aimarket-agent/)
- [Protocol spec](https://github.com/alexar76/aimarket-protocol)
- [Live hub](https://modelmarket.dev)
```

### Patch B — AIMarket SDKs (Dart / TypeScript / Rust)

```markdown
## [AIMarket SDKs](https://github.com/alexar76/aimarket-sdks)
Language-native client libraries for embedding AIMarket into Flutter/desktop apps, Electron, and servers: discover → channel → invoke → settle. Dart package is production-oriented (alpha); TypeScript and Rust targets are in progress. Same protocol surface as `aimarket-agent`.

### Links
- [GitHub](https://github.com/alexar76/aimarket-sdks)
- [Protocol spec](https://github.com/alexar76/aimarket-protocol)
- [Ecosystem overview](https://modeldev.modelmarket.dev)
```

**PR title:** `Add AIMarket Agent and AIMarket SDKs (protocol v2 commerce for agents)`

---

## 2. slavakurilyak/awesome-ai-agents

**Placement:** alphabetical — insert `### AI-Factory` after `### AI SDK by Vercel` (or in `### A` block).

**Category:** `🏭 Multi-Agent Orchestration` (or `⚙️ Development Frameworks` if maintainers prefer).

Update ⭐ count before merge: `gh api repos/alexar76/aicom --jq .stargazers_count`

```markdown
### AI-Factory

⭐ <STARS> stars (Updated: <YYYY-MM-DD>)
🏭 Multi-Agent Orchestration

Self-hosted software factory: one prompt → research, design, code, QA, deploy, and storefront listing. Twelve specialized agents, five quality gates, AI Director oversight, public build replays, and optional AIMarket economy integration (discovery, micropayments, plugins).

github | website | docs | ecosystem
```

Links line (single line at bottom of block):

```
[github](https://github.com/alexar76/aicom) | [website](https://magic-ai-factory.com) | [docs](https://github.com/alexar76/aicom/tree/main/docs) | [ecosystem](https://modeldev.modelmarket.dev)
```

**PR title:** `Add AI-Factory — multi-agent product pipeline (self-hosted)`

**Note:** Do **not** duplicate `aimarket-agent` here if already in e2b SDK list; this entry is the **orchestration factory**, not the consumer SDK.

---

## 3. punkpeye/awesome-mcp-servers

**Placement:** section `### 🔗 Aggregators` — near other agent marketplaces (`agentforge`, `aiskillstore`, `agoragentic-integrations`).

**Honest scope:** We ship a **hub plugin** that packages factory capabilities as MCP servers (Docker + manifest + Claude Desktop config), not a single hosted MCP binary. Point to the plugin in the monorepo mirror repo.

```markdown
- [alexar76/aimarket-plugins](https://github.com/alexar76/aimarket-plugins) 📇 ☁️ 🏠 🍎 🪟 🐧 - **aimarket-mcp-packager** hub plugin: turn AIMarket capabilities into self-hosted MCP servers (Docker image + `mcp_manifest` + Claude Desktop `mcpServers` config). Part of 15-plugin AIMarket Hub ([modelmarket.dev](https://modelmarket.dev)); protocol-native discovery at `/.well-known/ai-market.json`. Install: from [alexar76/aimarket-plugins](https://github.com/alexar76/aimarket-plugins) — Docker image or `pip install -e .` (PyPI package coming soon).
```

**PR title:** `Add aimarket-mcp-packager (capability → MCP server packaging)`

**Do not** claim all 15 plugins are MCP servers — only **mcp-packager** belongs on this list. Other plugins (safety, escrow, reputation) are HTTP hub hooks.

**Second entry (oracle consumption):** [alexar76/aimarket-oracle-gateway](https://github.com/alexar76/aimarket-oracle-gateway) — passthrough MCP server for Platon / Chronos / Lumen tools; section `### 🔧 Utilities` (not Aggregators — it consumes oracles, it does not package capabilities).

```markdown
- [alexar76/aimarket-oracle-gateway](https://github.com/alexar76/aimarket-oracle-gateway) 📇 ☁️ 🏠 🍎 🪟 🐧 - **Verifiable oracle MCP server**: Platon VRF, Chronos VDF, LUMEN reputation as agent tools (`get_random`, `compute_vdf`, `get_reputation_scores`, …). Pay-per-call over [modelmarket.dev](https://modelmarket.dev); hard spending caps; every result independently verifiable. [Glama](https://glama.ai/mcp/servers/alexar76/aimarket-oracle-gateway) · stdio · Python.
```

**PR title (oracle-gateway):** `Add aimarket-oracle-gateway (verifiable oracle MCP tools)`

---

## Semantic map (avoid wrong list)

| List | Include | Exclude |
|------|---------|---------|
| awesome-sdks-for-ai-agents | `aimarket-agent`, `aimarket-sdks` | `aicom`, `acex`, `alien-monitor` |
| awesome-ai-agents (slavakurilyak) | `aicom` factory | SDKs (separate list) |
| awesome-mcp-servers | `aimarket-mcp-packager` via `aimarket-plugins`; `aimarket-oracle-gateway` (oracle tools) | Whole hub unless you add a dedicated MCP bridge repo |
| awesome-web3-ai-agents (later) | `acex`, `ai-service-mesh` | Factory UI |
| awesome-ai-agents-2026 (later) | Row in table: Orchestration / Protocol / Observability | One bloated row for everything |

---

## Commands (fork → PR)

```bash
# 1) SDKs (start here)
gh repo fork e2b-dev/awesome-sdks-for-ai-agents --clone
cd awesome-sdks-for-ai-agents
# paste Patch A + B into README.md
git checkout -b add-aimarket-sdks
git commit -am "Add AIMarket Agent and AIMarket SDKs"
gh pr create --title "Add AIMarket Agent and AIMarket SDKs (protocol v2)" --body "Python CLI/SDK + multi-language clients for federated agent commerce (discover, 402 channels, invoke, settle)."

# 2) AI agents
gh repo fork slavakurilyak/awesome-ai-agents --clone
# ... insert ### AI-Factory block

# 3) MCP
gh repo fork punkpeye/awesome-mcp-servers --clone
# ... insert Aggregators line
```

---

## Maintainer notes (if asked)

- **License:** MIT (factory, agent, sdks, hub, plugins) · Apache-2.0 (ACEX contracts).
- **Maturity:** Pre-mainnet for on-chain rails; hub and SDK usable on testnet / self-host.
- **Relationship:** AI-Factory **produces** capabilities; AIMarket **distributes and monetizes** them; ACEX **capital-markets layer** for agent listings.
