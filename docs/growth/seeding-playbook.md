# Seeding playbook — MCP registries & AI-agent awesome lists

Single brief for teammates: **honest GitHub stars/forks only** — no purchased or fake engagement. Use the copy below verbatim; do not invent install steps, prices, or features not in the repo.

**Canonical CTA link:** the target repository, or the ecosystem landing [https://alexar76.github.io/aicom/](https://alexar76.github.io/aicom/) (Star on GitHub button).

**Before every PR:** read the target list's CONTRIBUTING / format rules; keep alphabetical order within category; do not spam five lists in one day with identical low-effort text.

Related patch drafts: [`docs/awesome-submissions/`](../awesome-submissions/).

---

## 0. Metrics & rules

| Rule | Detail |
|------|--------|
| Success metric | Real ⭐ and forks on GitHub — track weekly |
| CTA | Repo URL or `alexar76.github.io/aicom` |
| Copy | Use sections below only — verified against code |
| PR hygiene | One quality PR per list; alphabetize; match category |
| Anti-spam | Space submissions; vary angle per list |

**Baseline stars (fill before Phase 1, update at +7 days):**

| Repo | Stars @ start | Stars @ +7d |
|------|---------------|-------------|
| [aicom](https://github.com/alexar76/aicom) | | |
| [oracles](https://github.com/alexar76/oracles) | | |
| [aimarket-oracle-gateway](https://github.com/alexar76/aimarket-oracle-gateway) | | |
| [acex](https://github.com/alexar76/acex) | | |
| [ai-service-mesh](https://github.com/alexar76/ai-service-mesh) | | |

---

## 1. Ready assets — Oracle Gateway

**Canonical facts**

| Field | Value |
|-------|--------|
| Repo | https://github.com/alexar76/aimarket-oracle-gateway |
| License | MIT |
| Runtime | Python · stdio (FastMCP) |
| Hosts | Claude Desktop, Cursor, Glama, any stdio MCP client |
| Install | `python mcp_stdio_server.py` (from repo or Docker; check PyPI — if 404, use source/Docker) |
| Glama | https://glama.ai/mcp/servers/alexar76/aimarket-oracle-gateway |

**Client config (`mcp.json`):**

```json
{
  "mcpServers": {
    "aimarket-oracle-gateway": {
      "command": "python",
      "args": ["mcp_stdio_server.py"],
      "env": {
        "AIMARKET_ORACLE_URL": "<oracle-family URL for free/demo path>"
      }
    }
  }
}
```

**Short (1 line):**

> Verifiable oracle tools for AI agents — VRF randomness, VDF delay & reputation, pay-per-call, every result independently verifiable.

**Medium:**

> An MCP (stdio) server exposing the AIMarket ecosystem's verifiable oracles: Platon VRF (Ed25519-signed unbiasable randomness), Chronos VDF (verifiable delay / proof-of-elapsed-time), and LUMEN reputation (PageRank/EigenTrust trust scores). Pay-per-call over the AIMarket protocol, no signup; every result is independently verifiable. Tools: `get_random`, `get_randomness_beacon`, `ask_oracle`, `compute_vdf`, `verify_vdf`, `get_reputation_scores`, `list_oracle_capabilities`. Fail-closed spend caps, MIT.

**Tags:** `mcp`, `model-context-protocol`, `oracle`, `randomness`, `vrf`, `vdf`, `verifiable-delay-function`, `reputation`, `pagerank`, `eigentrust`, `ai-agents`, `agent-economy`, `ed25519`, `cryptography`, `pay-per-call`, `python`, `stdio`

---

## 2. PHASE 1 — catalogs (do now)

### A. MCP registries

| ID | Target | Status | Action |
|----|--------|--------|--------|
| A1 | [Official MCP Registry](https://registry.modelcontextprotocol.io) | ✅ | **5 servers** (incl. warden) — `docs/mcp-registries/` + `./scripts/publish_mcp_registry.sh` |
| A2 | [punkpeye/awesome-mcp-servers](https://github.com/punkpeye/awesome-mcp-servers) | 🔄 | **PR [#9910](https://github.com/punkpeye/awesome-mcp-servers/pull/9910)** — oracle-gateway in Security (from **alexar76**; replaces closed #8422). `aimarket-plugins` already in Aggregators (#7193). **Always PR from alexar76**, not personal forks — maintainers expect org account. |
| A3 | [mcp.so](https://mcp.so) | ☐ | Submit form: repo + medium description + tags |
| A4 | [Smithery](https://smithery.ai) | ☐ | Connect GitHub repo; add `smithery.yaml` if required (dev task) |
| A5 | [PulseMCP](https://pulsemcp.com) | ☐ | Submit form: repo + medium description |
| A6 | (opt.) Cline MCP Marketplace | ☐ | PR to `cline/mcp-marketplace` |
| A7 | (opt.) mcpservers.org | ☐ | Submit |
| A8 | (opt.) aimarket-mcp-packager | ☐ | Second server where aggregators fit — see [`docs/awesome-submissions/punkpeye-awesome-mcp-servers.patch.md`](../awesome-submissions/punkpeye-awesome-mcp-servers.patch.md) |

**A2 — PR line (exact format, add 🐍 marker):**

```markdown
- [alexar76/aimarket-oracle-gateway](https://github.com/alexar76/aimarket-oracle-gateway) 🎖️ 🐍 🏠 ☁️ - Verifiable oracle tools for AI agents — Platon VRF randomness, Chronos VDF delay, and LUMEN reputation; pay-per-call over the AIMarket protocol, every result independently verifiable.
```

**A2 — PR title:** `Add aimarket-oracle-gateway (verifiable oracle MCP server)`

**A2 — PR body:** One paragraph — MIT stdio server, link Glama listing (score integration), list 7 tools.

---

### B. AI-agent awesome lists

| ID | Target | Status | Entries |
|----|--------|--------|---------|
| B1 | [caramaschiHG/awesome-ai-agents-2026](https://github.com/caramaschiHG/awesome-ai-agents-2026) | ☐ | Three rows in three categories (markdown tables) |
| B2 | [e2b-dev/awesome-ai-agents](https://github.com/e2b-dev/awesome-ai-agents) | ☐ | Google Form — **aicom only** (flagship) |
| B3 | [taiyangc/awesome-web3-ai-agents](https://github.com/taiyangc/awesome-web3-ai-agents) | ☐ | ACEX + ai-service-mesh |
| B4 | (opt.) awesome-selfhosted / awesome-mcp-servers | ☐ | aicom self-hosted angle |

**B1 — copy:**

| Category | Name | Blurb | URL |
|----------|------|-------|-----|
| Multi-Agent Orchestration | aicom | AI-Factory — autonomous multi-agent pipeline (research→design→code→QA→deploy), 5 quality gates + AI Director, self-hosted, MIT. | https://github.com/alexar76/aicom |
| Protocols and Standards | AIMarket / ACEX | Open protocol + schemas + test vectors for an agent capability marketplace and an agent capital market (Solidity). | https://github.com/alexar76/aimarket-protocol |
| Observability and Evaluation | Alien Monitor | Real-time 3D visualization of an AI-agent economy — hub, factory, agents, contracts, on-chain metrics in one live graph. | https://github.com/alexar76/alien-monitor |

**B3 — copy:**

| Name | Blurb | URL |
|------|-------|-----|
| ACEX | Agent Capital Exchange — on-chain listings, CapShares, lending, AMM for AI agents (Solidity, Base). | https://github.com/alexar76/acex |
| ai-service-mesh | Autonomous agent discovery, verification, escrow, and on-chain payments. | https://github.com/alexar76/ai-service-mesh |

---

## 3. PHASE 2 — curator submissions (after ~50–100 ⭐ from Phase 1)

Curators (Console.dev, Changelog) weight stars. Texts ready — submit when signal exists.

| ID | Target | Status | Copy |
|----|--------|--------|------|
| C1 | [Console.dev](https://console.dev) submit a tool | ☐ | See blurb below |
| C2 | [Changelog News](https://changelog.com/news) | ☐ | Same blurb; title: *An entire autonomous AI-agent economy, open-sourced (MIT)* |
| C3 | TLDR / TLDR AI | ☐ | One-liner + link |

**Console / Changelog blurb:**

> AICOM — self-hosted AI agent factory. One prompt → a multi-agent pipeline (research, design, code, QA, deploy) ships a real web product in ~30 min. Runs on your box with your LLM keys. MIT. Part of an open AI-agent economy with verifiable oracles and on-chain pay-per-call. https://github.com/alexar76/aicom

**TLDR one-liner:**

> Self-hosted, MIT alternative to hosted app-builders — one prompt → a shipped web product, with an on-chain agent economy behind it. https://github.com/alexar76/aicom

---

## 4. Delivery checklist (report back)

For each submission record:

- [ ] Link to PR or form submission (even if pending)
- [ ] Accepted / changes requested / rejected
- [ ] Which catalog drove measurable ⭐ (compare baseline vs +7d table above)

---

## Appendix — why we are not restructuring repos now

- Satellites already mirror cleanly via `scripts/publish_all_repos.sh` / `satellite-map.yaml`.
- Glama, PyPI, and GHCR targets are per-repo — splitting further delays catalog submissions.
- Awesome-list PRs reference **stable public URLs**; mass moves break inbound links and open PRs.
- Focus Phase 1 on **discovery surfaces**; repo layout changes only when a concrete blocker appears (not preemptively).

---

## Internal links

- Awesome PR drafts: [`docs/awesome-submissions/`](../awesome-submissions/)
- Oracle quickstart spec: [`docs/specs/quickstart-call-an-oracle.md`](../specs/quickstart-call-an-oracle.md)
- Ecosystem landing: [modeldev.modelmarket.dev](https://modeldev.modelmarket.dev)
- Full deploy runbook: [`docs/quickstart-ecosystem-deploy.md`](../quickstart-ecosystem-deploy.md)
