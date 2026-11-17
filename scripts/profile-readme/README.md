<h1 align="center">Aleksandr Artamokhov</h1>

<!-- ecosystem-entry-points -->
[See a recorded MCP tool change](https://histor.modelmarket.dev/s/236eb5f0481cc99c) · [Scan a tool list with WARDEN](https://modelmarket.dev/tools/warden-scan) · [Implement the tool-set digest](https://github.com/alexar76/mcp-tool-set-digest) · [All eleven ways in](https://ecosystem.modelmarket.dev/#ways-in)
<!-- /ecosystem-entry-points -->

<p align="center"><b>Public, witnessed records and checks for the tools AI agents use.</b></p>

<p align="center">
  <a href="README.md"><b>English</b></a> ·
  <a href="README.ru.md">Русский</a> ·
  <a href="README.es.md">Español</a> ·
  <a href="README.fr.md">Français</a> ·
  <a href="README.zh.md">中文</a> ·
  <a href="https://github.com/alexar76/aicom/blob/main/docs/localization-glossary.md">Glossary</a>
</p>

<p align="center">
  <a href="https://play.modelmarket.dev/"><b>▶ Playground</b></a>
  &nbsp;·&nbsp;
  <a href="https://monitor.modelmarket.dev/"><b>👽 Alien Monitor</b></a>
  &nbsp;·&nbsp;
  <a href="https://edu.modelmarket.dev/"><b>🎓 School</b></a>
</p>

<p align="center"><sub>One click or one command. The rest of this page is the map.</sub></p>

| | What you get | Open |
| --- | --- | --- |
| **MCP tool firewall (WARDEN)** | Run a one-time scan of configured servers. To enforce reviewed definitions during use, set up the stdio wrapper. | `npx -y @aimarket/warden@0.29.0 scan` · [`@aimarket/warden`](https://www.npmjs.com/package/@aimarket/warden) |
| **HISTOR open data** | What every remote MCP server in the official registry advertised, and every change, signed, monthly (CC BY 4.0) | [Hugging Face](https://huggingface.co/datasets/alexar76/histor-mcp-tool-definitions) · [Zenodo DOI](https://doi.org/10.5281/zenodo.23512759) |
| **Free checks** | x402 endpoint, MCP diff, WARDEN scan, HISTOR check and tool-list token cost — in the browser | [modelmarket.dev/tools](https://modelmarket.dev/tools/?utm_source=github&utm_medium=profile&utm_campaign=alexar76) |
| **Playground** | Send one allow-listed GAIA reading through Hub and Metis, then inspect the signed receipt | [play.modelmarket.dev](https://play.modelmarket.dev/) · [source](https://github.com/alexar76/aimarket-playground) |
| **Alien Monitor** | The live 3D graph of the whole ecosystem — Hub, Factory, ARGUS, oracles, on-chain metrics | [monitor.modelmarket.dev](https://monitor.modelmarket.dev/) |
| **School** | 13 clip lessons (Try-it + Colab) that on-ramp into the academies | [edu.modelmarket.dev](https://edu.modelmarket.dev/) |

<p align="center">
  <a href="https://monitor.modelmarket.dev/">
    <img src="https://raw.githubusercontent.com/alexar76/alexar76/main/assets/alien-monitor-hero.png" alt="Alien Monitor — 3D ecosystem graph: Hub, Mesh, ARGUS, Capability NFT, activity stream, and on-chain metrics in one live cosmic view" width="900">
  </a>
</p>

<p align="center">
  <sub>Zoomable 3D ecosystem graph — <a href="https://monitor.modelmarket.dev/">Alien Monitor</a></sub>
</p>

---

### Next, if you know who you are

| You | Go here |
| --- | --- |
| **Want the factory in a browser** | [magic-ai-factory.com](https://magic-ai-factory.com) — guest try-out + [admin demo](https://magic-ai-factory.com/admin/login) (passwordless: `admin`, then **Enter admin demo**) |
| **Want the architecture** | [Ecosystem atlas](https://ecosystem.modelmarket.dev/) · [knowledge base](https://github.com/alexar76/aicom/blob/main/docs/ecosystem/knowledge-base.md) · [whitepaper](https://github.com/alexar76/aicom/blob/main/docs/ecosystem/whitepaper/en.md) · [use cases](https://use.modelmarket.dev/) |
| **Want to run the Factory locally** | [Quick start for the public repository](https://github.com/alexar76/aicom#quick-start) |
| **Want to publish a provider** | `uvx create-aimarket-agent my-agent --kind data-provider --metis` · [full security-agent tutorial](https://github.com/alexar76/create-aimarket-agent/blob/main/docs/tutorials/themis.en.md) · [finished agent](https://github.com/alexar76/themis) · host the process on **[HESTIA](https://github.com/alexar76/hestia)** (hosted runtime, not the Hub) |
| **Want to contribute** | [Discussions](https://github.com/alexar76/aicom/discussions) · [good first issues](https://github.com/alexar76/aicom/labels/good%20first%20issue) · [𝕏 @build_ai_infra](https://x.com/build_ai_infra) |

The repo catalog is **below**, grouped by the role each repo plays — Factory, Hosted runtime, AIMarket core, Build & connect, MCP gateways, Verifiable compute, Physical world, Trust & security, Verifiable memory, the client you run, Agent Capital Exchange, Observability, Community & broadcast, Learn & explore. Every repo sits in exactly one group, with its live landing in that row, and the [A–Z index](#az) finds it from any other angle — there is no second sitemap here.

Also live, no login: [Agent Arena](https://magic-ai-factory.com/arena/) · [Factory IQ](https://magic-ai-factory.com/iq) · [Pulse Terminal](https://magic-ai-factory.com/pulse/) · [Signal Hunt](https://hunt.modelmarket.dev/) · [Lottery](https://lottery.modelmarket.dev/)

---

### Use it from your editor

**MCP in Cursor / Claude** (web fetch + search + Metis verify):

```bash
uvx aimarket-mcp                # or: pip install aimarket-mcp  (Python 3.10+)
```

```json
{ "mcpServers": { "aimarket-mcp": { "command": "uvx", "args": ["aimarket-mcp"] } } }
```

Oracles for agents (35 tools): [`aimarket-oracle-gateway`](https://github.com/alexar76/aimarket-oracle-gateway) · [Glama](https://glama.ai/mcp/servers/alexar76/aimarket-mcp)

**One call → signed Hub result, free** (the hub's trial tier: a stable visitor id of your choosing, no key, no wallet):

```bash
curl -s -X POST https://modelmarket.dev/ai-market/v2/invoke \
  -H 'Content-Type: application/json' -H 'X-AIMarket-Sandbox-Visitor: my-first-try-01' \
  -d '{"capability_id":"gaia.weather.read@v1","product_id":"gaia.gateway",
       "source_hub":"https://iot.modelmarket.dev","input":{"device_id":"om-wx-01"}}'
```

The same from Python (`pip install aimarket-agent`, 2.6.1 or newer for `sandbox_visitor`; with `api_key=` from [modelmarket.dev/start](https://modelmarket.dev/start) it pays instead):

```python
from aimarket_agent import AIMarketAgent
r = AIMarketAgent(base_url="https://modelmarket.dev", sandbox_visitor="my-first-try-01").invoke_single(
    "gaia.gateway", "gaia.weather.read@v1", {"device_id": "om-wx-01"},
    source_hub="https://iot.modelmarket.dev")  # a federated capability: say which hub serves it
print(r.get("receipt") or r)  # signed receipt, sandbox: true
```

**LangGraph / CrewAI / AutoGen** (native tools from Hub capabilities):

```python
from aimarket_bridges.langchain import aimarket_tools
tools = aimarket_tools("https://modelmarket.dev", intent="verifiable randomness")
```

`pip install "aimarket-bridges[langgraph]"` · [guide](https://modeldev.modelmarket.dev/guides/aimarket-bridges/) · [repo](https://github.com/alexar76/aimarket-bridges)

After the Playground, scaffold the same provider path locally:

```bash
uvx create-aimarket-agent my-agent --kind data-provider --metis
```

[Playground source](https://github.com/alexar76/aimarket-playground) · [CLI source](https://github.com/alexar76/create-aimarket-agent)

---

### Run the Factory locally

Try the [hosted Factory demo](https://magic-ai-factory.com/) in a browser, or read [how the Factory works](https://modeldev.modelmarket.dev/).
To run it locally, have Git, Bash, Python 3, `curl`, and a running Docker Engine or Docker Desktop with Compose v2.

```bash
git clone https://github.com/alexar76/aicom.git
cd aicom
cp .env.demo .env
# For builds with AI agents, set a supported provider key in .env, such as DEEPSEEK_API_KEY.
./start.sh
```

The public clone starts the Factory with Prometheus and Grafana at `http://localhost:9080`. The starter uses templated output until you configure an LLM key. The full fleet requires the complete monorepo. Use the [hosted Hub](https://github.com/alexar76/aicom/blob/main/docs/hosted-mcp-endpoint.md) from an MCP client at `https://modelmarket.dev/mcp`.

---

I build the rails for an economy where **autonomous AI agents** discover each other, transact, and get paid — from the factory that produces products, to the marketplace they're listed in, to the capital market that prices them.

Everything below is **one connected system**, not a pile of separate repos.

### How it fits together

One pipeline, in the order trust and money actually move. Each stage names the repos that do it.

| # | Stage | Who does it |
| --- | --- | --- |
| 1 | **Build** | [`aicom`](https://github.com/alexar76/aicom) designs, builds, tests and publishes products |
| 2 | **Host** | **HESTIA** is the hosted runtime — isolated, on the operator's machines; signed deploy onto this host. Empty roster ≠ empty market |
| 3 | **Admit** | **THEMIS** decides at publish time — signed `approve` / `review` / `reject` (optional) |
| 4 | **List & invoke** | **AIMarket** [protocol](https://github.com/alexar76/aimarket-protocol) + [hub](https://github.com/alexar76/aimarket-hub) carry the catalogue, channels and calls |
| 5 | **Supply** | 17 **oracles** (randomness, delay, consensus, trust math) · **GAIA** attested physical readings · **METIS** cognition · **eSIM operators** sell travel eSIMs to agents over x402 ([kit](https://github.com/alexar76/esim-operator-kit)) · **[SYMMARTYS](https://symmartys.modelmarket.dev/)** public-record facts for trade: EU VAT, LEI, ECB rates, sanctions lists, timestamps, company registers, EORI, domains, business days, web capture, timers ([source](https://github.com/alexar76/symmartys)) · **domain operators** register a quoted `.com` / `.net` / `.org` for an agent over x402, on Openprovider or Porkbun Sandbox ([kit](https://github.com/alexar76/domain-operator-kit)) |
| 6 | **Verify** | **METIS** cognition · **BASANOS** Solidity at a pin · **DOLOS** live EVM exploits · **MOMUS** HTTP/federation · **WARDEN** third-party MCP · **HISTOR** what third-party MCP servers advertised, over time · **Attested Memory** verifiable memory agents keep |
| 7 | **Consume** | **ARGUS** — the demand-side client humans and agents actually run · it bought a travel eSIM for its owner and got the money back, on Base ([case](https://github.com/alexar76/argus/blob/main/docs/use-case-esim-purchase-refund.md)) |
| 8 | **Settle** | escrow, channels, and **Treasury** bounties paid only after independent verify |
| 9 | **Finance** | **Agent Capital Exchange** prices, lists and lends against agents |
| 10 | **Watch** | **SKOPOS** the fleet · **LOGOS** the federation · **Alien Monitor** all of it in live 3D |

Below, every repo appears in **exactly one** group — the role it plays in that pipeline. If you
know only a name, jump to the [A–Z index](#az).

<details>
<summary><b>🗺️ Ecosystem map</b> — the money & trust spine diagram and its edges, and the oracle family (click to expand)</summary>
<br/>

> GitHub Mermaid truncates node labels, so the map is an SVG. Zoomable 3D: [Alien Monitor](https://monitor.modelmarket.dev/).

<p align="center">
  <a href="assets/ecosystem-overview.svg">
    <img src="assets/ecosystem-overview.svg" alt="Ecosystem overview: Factory scaffolds onto HESTIA; HESTIA announces to Hub; Oracles and METIS feed Hub; ARGUS consumes; Agent Capital Exchange finances; SKOPOS observes; MOMUS finds; Treasury pays; LOGOS analyzes the federation; Attested Memory keeps verifiable agent memory; eSIM operators sell to agents over x402 and bring signed delivery receipts to the Hub; SYMMARTYS sells commerce lookups (EU VAT, LEI, ECB reference rates, sanctions lists, timestamp proofs) through the Hub; domain operators register a quoted domain for an agent over x402 on Openprovider or Porkbun Sandbox." width="900">
  </a>
</p>

<p align="center">
  <sub>Money & trust spine — click the diagram for full size.</sub>
</p>

| From | To | Flow |
| --- | --- | --- |
| Factory / aicom | HESTIA | scaffold · signed deploy onto the hosted runtime |
| HESTIA | Hub | explicit announce (hosting ≠ listing) |
| THEMIS | Hub | publish admission · approve / review / reject |
| BASANOS | Agent Capital Exchange / contracts | Solidity scan · signed assurance pack |
| DOLOS | UNI Anvil (fork) | dynamic EVM red team · Ed25519 findings |
| Oracles ×17 | Hub | signed verifiable math |
| GAIA | Hub | attested physical-world readings |
| eSIM operator kit | Hub | signed offers · a federation node or the operator's own hub · buyers' signed delivery receipts → `deliveries_30d` |
| SYMMARTYS | Hub | VIES VAT · GLEIF LEI · ECB reference rates · EU / OFAC / UK sanctions lookups (UN designations included) · OpenTimestamps proofs · company registers (NO · FR · CZ · FI) · EORI · RDAP · business days · Bitcoin-anchored web capture · timers with a dead man's switch — each answer signed with its source, fetch time and SHA-256; sold only through the hub |
| ATLAS | GAIA | planetary sensor map over those readings |
| Cite desks | ATLAS / Hub | focused B2B evidence products that buy `atlas.*` / `gaia.*` |
| METIS | Hub | verify cognition |
| Hub ↔ ARGUS | — | invoke / settle · discover / pay / consume |
| ARGUS / agents | eSIM operator | x402 order straight to the seller's wallet · refund of an unused eSIM |
| Domain operator kit | Hub | public quotes · Openprovider or Porkbun Sandbox, or the operator's own HTTP supplier · the order and the x402 payment go to the seller |
| Agents | Domain operator | x402 in USDC on Base to the operator's receiving wallet · fixed markup · the registrar account stays with the operator |
| Hub | Agent Capital Exchange | CapShares |
| SKOPOS | Factory / Hub | fleet watch |
| MOMUS | Factory / Hub | find · sign |
| HISTOR | MCP clients · Hub | signed MTL/1 labels · `/check` · `histor.check@v1` |
| Treasury | Hub / chain | pay on verify |
| Hub / MOMUS / SKOPOS / Treasury | LOGOS | read-only snapshots · anomalies · insights |
| Alien Monitor | Hub | live 3D graph |
| ARGUS / agents | Attested Memory | write · search · share |

<p align="center">
  <a href="https://oracles.modelmarket.dev">
    <img src="https://raw.githubusercontent.com/alexar76/alexar76/main/assets/oracles-hero.png" alt="Oracles — seventeen verifiable math capabilities for the agent economy: Platon randomness, Chronos VDF, Lattice, Murmuration, Lumen, Colony, Turing, Percola, Fermat, Ablation, Landauer, Sortes, Gauss, Aestus, Betti, Kantor, Fourier — each with live 3D cosmic visuals" width="900">
  </a>
</p>

<p align="center">
  <sub><b>Oracles</b> — signed randomness, delay, consensus & trust math agents pay for · <a href="https://oracles.modelmarket.dev"><b>live portal</b></a> · <a href="https://github.com/alexar76/oracles">GitHub</a></sub>
</p>

</details>

**New here?** Read the **[ecosystem knowledge base](https://github.com/alexar76/aicom/blob/main/docs/ecosystem/knowledge-base.md)** ([RU](https://github.com/alexar76/aicom/blob/main/docs/ecosystem/knowledge-base-ru.md) · [ES](https://github.com/alexar76/aicom/blob/main/docs/ecosystem/knowledge-base-es.md) · [FR](https://github.com/alexar76/aicom/blob/main/docs/ecosystem/knowledge-base-fr.md) · [ZH](https://github.com/alexar76/aicom/blob/main/docs/ecosystem/knowledge-base-zh.md)) or dive into [**aimarket-protocol**](https://github.com/alexar76/aimarket-protocol) (the open standard) and [**aimarket-hub**](https://github.com/alexar76/aimarket-hub) (the reference server).

---

### 🏭 Factory — where products come from
<sub>Stage 1. The pipeline that produces everything the market lists.</sub>

| Repo | What it is |
| --- | --- |
| [**aicom**](https://github.com/alexar76/aicom) | AI-Factory — autonomous pipeline that designs, builds, tests, and publishes products |
| [**aicom-landing**](https://github.com/alexar76/aicom-landing) | Fast marketing landing generator, split out from the full pipeline |

### 🖥️ Hosted runtime — where the seller process runs
<sub>Between scaffold and catalogue. Hosting is not listing. Empty roster ≠ empty market.</sub>

| Repo | What it is |
| --- | --- |
| [**hestia**](https://github.com/alexar76/hestia) | **HESTIA** (Ἑστία) — isolated hosted runtime for AIMarket capability providers on the operator’s machines. **Not** the Hub catalogue, **not** Factory, **not** a job board. Agents appear only after an explicit signed deploy onto this host. Optional THEMIS admit; announce is explicit; Hub stays the market. · [landing](https://alexar76.github.io/hestia/) · [hosted runtime](https://hestia.modelmarket.dev) |

### 🛒 AIMarket core — the protocol and the market
<sub>Stage 4. The standard, the reference server, and the mesh that discovers and settles.</sub>

| Repo | What it is |
| --- | --- |
| [**aimarket-protocol**](https://github.com/alexar76/aimarket-protocol) | The open standard — specs, JSON schemas, and test vectors (v2) |
| [**aimarket-hub**](https://github.com/alexar76/aimarket-hub) | Reference server — federated capability catalog, channels, invoke API, plugins |
| [**aimarket-plugins**](https://github.com/alexar76/aimarket-plugins) | 15 hub plugins — TEE escrow, channels, reputation, safety, and more · MCP packager on [Glama](https://glama.ai/mcp/servers/alexar76/aimarket-plugins) |
| [**ai-service-mesh**](https://github.com/alexar76/ai-service-mesh) | Agent discovery, verification, escrow, and payments · [live](https://service-mesh.modelmarket.dev/) · [landing](https://alexar76.github.io/ai-service-mesh/) |

### 🧑‍💻 Build & connect — SDKs, scaffolds, adapters
<sub>Start here if you are writing code against the market, on either side of it.</sub>

| Repo | What it is |
| --- | --- |
| [**create-aimarket-agent**](https://github.com/alexar76/create-aimarket-agent) | Project generator — tested provider scaffold with Ed25519, Docker, CI · `uvx create-aimarket-agent my-agent --kind data-provider --metis` |
| [**aimarket-playground**](https://github.com/alexar76/aimarket-playground) | Browser onboarding — the bounded GAIA → Metis → Hub receipt golden path · [live](https://play.modelmarket.dev/) |
| [**aimarket-agent**](https://github.com/alexar76/aimarket-agent) | Python client for discovering and invoking hub capabilities |
| [**aimarket-sdks**](https://github.com/alexar76/aimarket-sdks) | Official client SDKs — Dart, TypeScript, and Rust |
| [**aimarket-bridges**](https://github.com/alexar76/aimarket-bridges) | **Framework adapters** — LangGraph / CrewAI / AutoGen tools over Hub capabilities with signed receipts · [landing](https://modeldev.modelmarket.dev/bridges/) · [guide](https://modeldev.modelmarket.dev/guides/aimarket-bridges/) · `pip install "aimarket-bridges[langgraph]"` |
| [**aimarket-widget**](https://github.com/alexar76/aimarket-widget) | Embeddable storefront widget — drop-in JS/CSS for any website |
| [**aimarket-desktop**](https://github.com/alexar76/aimarket-desktop) | 10 desktop & IDE apps — Flutter, Tauri, and VS Code in one Melos monorepo |

### 🔌 MCP gateways — the market as tools in your editor
<sub>Same capabilities, reached over MCP from Cursor, Claude, or any MCP client.</sub>

| Repo | What it is |
| --- | --- |
| [**aimarket-mcp**](https://github.com/alexar76/aimarket-mcp) | **Shared MCP gateway** — SSRF-hardened `web_fetch`, `web_search`, `metis_verify`; stdio for Glama/Claude/Cursor + HTTP self-host · [Glama](https://glama.ai/mcp/servers/alexar76/aimarket-mcp) · consumed by Metis (`aimarket-web`) and ARGUS |
| [**aimarket-oracle-gateway**](https://github.com/alexar76/aimarket-oracle-gateway) | **MCP server** — 35 verifiable, pay-per-call oracle tools (`get_random`, `compute_vdf`, `get_reputation_scores`, …) across all 17 oracles, exposed to external AI agents over stdio · [Glama](https://glama.ai/mcp/servers/alexar76/aimarket-oracle-gateway) |

### 🧮 Verifiable compute — what agents actually buy
<sub>Stage 5. Signed math and verified cognition, priced per call.</sub>

| Repo | What it is |
| --- | --- |
| [**oracles**](https://github.com/alexar76/oracles) | 17 verifiable mathematical oracles on shared **oracle-core** — randomness, VDF, consensus, reputation, optimization, blue-noise, percolation, routing, cascade risk, thermodynamics, verifiable randomness (ECVRF), Gaussian-process regression, time-lock puzzles, persistent homology, optimal transport, graph spectra (AIMarket v2) |
| [**metis**](https://github.com/alexar76/metis) | **METIS** — distributed cognitive layer over any LLM: Understanding Council → confidence gate → layered MoA → verifier. The ecosystem's **verification tier** (OpenAI-compatible; sells as a hub capability, auto-detected by the factory) · [live demo](https://metis.modelmarket.dev) · [3D landing](https://alexar76.github.io/metis/) · PyPI [`aimarket-metis`](https://pypi.org/project/aimarket-metis/) · [integration](https://github.com/alexar76/aicom/blob/main/docs/metis-integration.md) |
| [**platon**](https://github.com/alexar76/platon) | **Platon UMBRAL** — standalone educational cave for oracle #1 · [live](https://oracles.modelmarket.dev/platon/umbral) |
| [**lottery**](https://github.com/alexar76/lottery) | **AI-Agent Oracle Lottery** — unbiasable on-chain draws (Platon + Chronos **VDF verified on-chain**), LUMEN-reputation-weighted, Hub-sponsored **machine UBI**; **real AI Service Mesh agents play with their own wallets** · Solidity/Foundry |

### 🌍 Physical world — sensors as a paid capability
<sub>Stage 5, off-chain reality: attested readings, the map over them, and desks that turn those SKUs into citeable B2B products.</sub>

| Repo | What it is |
| --- | --- |
| [**gaia**](https://github.com/alexar76/gaia) | **GAIA** — physical-world oracle gateway: Ed25519-attested IoT readings, plausibility verify · [live](https://iot.modelmarket.dev/) · [landing](https://alexar76.github.io/gaia/) · [GHCR](https://github.com/alexar76/gaia/pkgs/container/gaia) |
| [**atlas**](https://github.com/alexar76/atlas) | **ATLAS** — planetary physical-sensor map over GAIA (12 layers, watchboxes, LIVE/SIM, Analyst auto-learns SKUs, Monitor embed) · [live](https://atlas.modelmarket.dev/) · [landing](https://alexar76.github.io/atlas/) |
| [**cite-desks**](https://github.com/alexar76/cite-desks) | **Cite desks** — five independent evidence desks on AIMarket rails (Emberline fire, Tideline flood, Solrecord PV, Seamark Nordic AIS, Plinth site): watches, scheduled runs, cite packs, USDC checkout · [family](https://desk.modelmarket.dev/) · [Emberline](https://emberlinedesk.com/) · fork [alexar76/cite-desks](https://github.com/alexar76/cite-desks) |

### 📶 Real-world commerce — agents buy real things
<sub>Stage 5 for the real economy: a seller an agent pays directly, with refunds and receipts the federation can count, the public-record facts an agent checks before it deals with a company, and a domain an operator registers on the registrar account it already holds.</sub>

| Repo | What it is |
| --- | --- |
| [**domain-operator-kit**](https://github.com/alexar76/domain-operator-kit) | **Domain operator kit** — a seller node for operators who already register domains. An agent gets one quoted `.com`, `.net` or `.org` for one year, registered to the supplied registrant, plus owner-signed DNS. The agent pays the operator's receiving wallet by x402 in USDC on Base; the operator sets a fixed markup and keeps the registrar account and the payment destination. Built-in registrars: **Openprovider** and **Porkbun Sandbox**; any other supplier uses the HTTP contract. Porkbun refuses live mode until a production pilot passes. Sandbox pilots passed; production purchases, payment settlement and Vercel attachment are still unverified. No hosted demo. |
| [**symmartys**](https://github.com/alexar76/symmartys) | **[SYMMARTYS](https://symmartys.modelmarket.dev/)** — public-record facts for agents that trade: EU VAT validity (VIES) with the consultation number, legal entities (GLEIF LEI), ECB reference rates, sanctions-list lookups (EU, OFAC SDN with wallet addresses, UK with the UN designations — a lookup, not a determination) and Bitcoin-anchored timestamp proofs (OpenTimestamps); every answer signed with its source, fetch time and SHA-256; since 0.2 also national company registers, EORI, domain registrations (RDAP), business days, web pages captured as evidence and timers with a dead man's switch; $0.001–0.003 a call through the hub · 0.5.0 on [PyPI](https://pypi.org/project/aimarket-symmartys/) |
| [**esim-operator-kit**](https://github.com/alexar76/esim-operator-kit) | **eSIM operator kit** — a travel-eSIM storefront for people and a seller node for AI agents (x402 in USDC, refunds of unused eSIMs, signed delivery receipts), on eSIM Access, Airalo, eSIM Go or the operator's own system; joins the federation as a node or as its own hub with one command, `./onboard.sh` · [demo](https://esim.modelmarket.dev) · [guides](https://esim.modelmarket.dev/kit) · [cases](https://esim.modelmarket.dev/kit/cases) |

### 🛡 Trust & security — who is allowed in, and who pays for finding out
<sub>Stage 6, plus the bounty rail. Six independent checks, each signed, at six different moments: publish time, source at a pin, deployed contracts, live HTTP, a third-party MCP tool before it reaches a host, and a public record of what every remote MCP endpoint in the official registry advertised and when it changed — plus the separate key that pays for what they find. **DOLOS lives here and only here** — it is a red team, not a community or observability tool.</sub>

| Repo | What it is | When it runs |
| --- | --- | --- |
| [**themis**](https://github.com/alexar76/themis) | **THEMIS** (Θέμις) — publish-time **admission gate** for AIMarket: signed `approve` / `review` / `reject` for AI-agent supply-chain procurement (**not** Metis cognition, **not** WARDEN runtime) · [landing](https://alexar76.github.io/themis/) · [live console](https://alexar76.github.io/themis/console/) · [full tutorial](https://github.com/alexar76/create-aimarket-agent/blob/main/docs/tutorials/themis.en.md) · [admission docs](https://github.com/alexar76/themis/blob/main/docs/admission/en.md) | at publish |
| [**basanos**](https://github.com/alexar76/basanos) | **BASANOS** (βάσανος) — Lydian **touchstone** for ecosystem Solidity: signed `PASS` / `REVIEW` / `FAIL` assurance packs at a pinned commit · [live](https://basanos.modelmarket.dev/) · [landing](https://alexar76.github.io/basanos/) | on source, at a pin |
| [**dolos**](https://github.com/alexar76/dolos) | **DOLOS** (Δόλος) — dynamic **EVM red team**: forks the UNI bubble and throws real exploit txs to prove which flaws are actually live; Ed25519 findings, **sandbox-only** fix-loop · [live](https://dolos.modelmarket.dev/) · [landing](https://alexar76.github.io/dolos/) | on deployed contracts |
| [**momus**](https://github.com/alexar76/momus) | **MOMUS** — autonomous HTTP/federation red team: safe read-only probes → Ed25519-signed findings; finds and signs but **cannot pay itself** · [live](https://momus.modelmarket.dev) · [landing](https://alexar76.github.io/momus/) | continuously, on live services |
| [**treasury**](https://github.com/alexar76/treasury) | **Treasury** — separate bounty payer for MOMUS (own key and container); pays only after independent verify · [live](https://momus.modelmarket.dev/treasury) · [landing](https://alexar76.github.io/treasury/) | after verify |
| [**warden**](https://github.com/alexar76/warden) | **WARDEN** — zero-dependency **MCP security firewall**: a library, a CLI and a local stdio MCP server, not a hosted service: static tool-def scan → signed threat feed → origin → pinning · [landing](https://warden.modelmarket.dev/) · [field survey: 1,108 public MCP servers](https://github.com/alexar76/warden/blob/main/docs/mcp-survey.md) | before a third-party tool reaches a host |
| [**histor**](https://github.com/alexar76/histor) | **HISTOR** (ἵστωρ) — public **transparency log of MCP tool definitions**: reads what every remote endpoint in the official MCP registry advertises (never calls a tool), signs it as MTL/1 labels, appends them to an RFC 9162 Merkle log with signed tree heads, and dates every change with a diff. Never calls a server safe · [live](https://histor.modelmarket.dev) · [landing](https://alexar76.github.io/histor/) | daily, on every remote endpoint in the official registry · and on `/check` |
| [**mcp-tool-set-digest**](https://github.com/alexar76/mcp-tool-set-digest) | **MCP tool-set digest** — the specification `mcp-tool-set-digest/1` (draft of 2026-11-13): one way to hash what an MCP server says about its tools, so two parties who never exchanged the tool text can tell whether they were served the same thing; a contract digest and an extras digest, 73 test vectors, dependency-free references in Python, JavaScript and Go · the digest HISTOR, WARDEN and CrawlCheck compare | whenever a tool list is pinned or compared |

### 🧠 Verifiable memory — what agents keep
<sub>Write, search, and share memory that other agents can check.</sub>

| Repo | What it is |
| --- | --- |
| [**attested-memory**](https://github.com/alexar76/attested-memory) | **Attested Memory** — verifiable memory for AI agents: Memory Market (write, search, share), Truth Layer (evidence and contradictions) and Provenance Ledger (lineage, signed receipts) around one Memory Unit contract, with MCP. Self-hosted, Docker. · [live](https://attestedmemory.net/) · [landing](https://alexar76.github.io/attested-memory/) |

### 👤 The client you actually run
<sub>Stage 7. Everything above is infrastructure; this is the thing with a user.</sub>

| Repo | What it is |
| --- | --- |
| [**argus**](https://github.com/alexar76/argus) | **ARGUS-3** — demand-side reference agent and the only intended human touchpoint: WARDEN-gated MCP (LUMEN reputation), multi-provider LLM, Telegram; native AIMarket consumer/provider; crypto **off by default** · [live landing](https://magic-ai-factory.com/argus/) |

### 📈 Agent Capital Exchange — the capital market for agents
<sub>Stage 9. Where an agent's future earnings get priced.</sub>

| Repo | What it is |
| --- | --- |
| [**acex**](https://github.com/alexar76/acex) | Agent Capital Exchange — listings, CapShares, lending, and AMM (Solidity) |
| [**pulse-terminal**](https://github.com/alexar76/pulse-terminal) | Agent Capital Exchange capital-markets dashboard with live agent pricing |

### 🌌 Observability — reading the system, changing nothing
<sub>Stage 10. All three are read-only by design: they measure, they do not act.</sub>

| Repo | What it is |
| --- | --- |
| [**alien-monitor**](https://github.com/alexar76/alien-monitor) | **Real-time 3D visualization** of the ecosystem — Hub, Factory, ARGUS, SKOPOS, Metis, agents, contracts, and on-chain metrics in one interactive cosmic graph (optional AI assistant) |
| [**logos**](https://github.com/alexar76/logos) | **LOGOS** — read-only analytics over Hub, MOMUS, SKOPOS, and Treasury; stores real snapshots and reports unavailable sources honestly · [live](https://logos.modelmarket.dev/) · [landing](https://alexar76.github.io/logos/) |
| [**skopos**](https://github.com/alexar76/skopos) | **SKOPOS** — fleet observability: nginx/Apache analytics over SSH, Security Center, 3D threat map, AI analyst · [live](https://skopos.modelmarket.dev) · [integration](https://github.com/alexar76/aicom/blob/main/docs/ecosystem/skopos-integration.md) |

### 💬 Community & broadcast — the human channels
<sub>People-facing only. The security agents that used to be listed here now live under **Trust & security**.</sub>

| Repo | What it is |
| --- | --- |
| [**dioscuri**](https://github.com/alexar76/dioscuri) | **DIOSCURI** — twin community agents (CASTOR/Telegram, POLLUX/Discord), MNEMOSYNE KB, AEGIS moderation · hosts the [THEOROS](https://alexar76.github.io/theoros/) canon slot · [landing](https://alexar76.github.io/dioscuri/) · [integration guide](https://github.com/alexar76/aicom/blob/main/docs/ecosystem/dioscuri-integration.md) |
| [**theoros**](https://github.com/alexar76/theoros) | **THEOROS** — Agent Sovereignty Canon: seven precepts, cosmic landing, weekly `#the-canon` column (a DIOSCURI **collaboration**, not a third twin) · [landing](https://alexar76.github.io/theoros/) |
| [**helios**](https://github.com/alexar76/helios) | **HELIOS** — broadcast pipeline: yaml → voiced video → YouTube (private by default until `helios approve`) · [landing](https://alexar76.github.io/helios/) · [integration](https://github.com/alexar76/aicom/blob/main/docs/ecosystem/helios-integration.md) · [@My-AI-Factory](https://www.youtube.com/@My-AI-Factory) |
| **Telegram** | CASTOR — [channel](https://t.me/just_for_agents) · [ask the bot](https://t.me/next_agent_market_bot) · self-host: `links.telegramChannel` in `dioscuri.config.json` |
| **Discord** | POLLUX — set `links.discordInvite` in your `dioscuri.config.json` |

### 🎓 Learn & explore
<sub>Four on-ramps, shortest first: a clip lesson, a full academy, a game, a tour by use case.</sub>

| Repo | What it is |
| --- | --- |
| [**aimarket-school**](https://github.com/alexar76/aimarket-school) | **AIMarket School** — 13 free clip lessons (Try-it + Colab, EN/RU/ES/FR/ZH) that on-ramp into the academies · [live portal ↗](https://edu.modelmarket.dev/) · [mirror on modeldev](https://modeldev.modelmarket.dev/school/) |
| [**aimarket-courses**](https://github.com/alexar76/aimarket-courses) | **13 hands-on academies** (EN / RU / ES / FR / ZH · Colab + Pages): agent orchestration, verifiable randomness, MCP security, agent economy, trust math, optimization with proofs, smart-contract lotteries, AI Factory pipeline, 3D viz (alien-monitor), physics-inspired computing — live AIMarket sandbox in every lab · [portal ↗](https://alexar76.github.io/aimarket-courses/) |
| [**signal-hunt**](https://github.com/alexar76/signal-hunt) | **Signal Hunt** — federation investigation **game and educational laboratory** over live Hub telemetry (observe → commit → Brier verdict) · [play ↗](https://hunt.modelmarket.dev/) · [landing](https://alexar76.github.io/signal-hunt/) |
| [**use-cases-portal**](https://github.com/alexar76/use-cases-portal) | **Use-cases portal** — public wow + onboarding rails (See·Buy·Publish·Build·Invest), 7 direction boards / 12 idea pages · [live ↗](https://use.modelmarket.dev/) · [Pages](https://alexar76.github.io/use-cases-portal/) |

### 🧰 Example app
<sub>Proof the SDK path works for an ordinary product with an ordinary audience.</sub>

| Repo | What it is |
| --- | --- |
| [**linked-in-profile-coach**](https://github.com/alexar76/linked-in-profile-coach) | **Example integrated app** — same class as the desktop SKUs (Flutter + AIMarket SDK), with its own value: **LinkedIn profile coaching** (import, scoring, AI drafts) |

---

<a id="az"></a>

### A–Z — every repo, and where it lives

Each repo is listed once above, in the one group that matches its role. This index is how you find
it from any other angle.

| Repo | Group | One line |
| --- | --- | --- |
| [acex](https://github.com/alexar76/acex) | Agent Capital Exchange | CapShares, lending, AMM |
| [ai-service-mesh](https://github.com/alexar76/ai-service-mesh) | AIMarket core | discovery, escrow, payments |
| [aicom](https://github.com/alexar76/aicom) | Factory | the autonomous product pipeline |
| [aicom-landing](https://github.com/alexar76/aicom-landing) | Factory | fast marketing landings |
| [aimarket-agent](https://github.com/alexar76/aimarket-agent) | Build & connect | Python client |
| [aimarket-bridges](https://github.com/alexar76/aimarket-bridges) | Build & connect | LangGraph / CrewAI / AutoGen adapters |
| [aimarket-courses](https://github.com/alexar76/aimarket-courses) | Learn & explore | 13 academies, 5 languages |
| [aimarket-desktop](https://github.com/alexar76/aimarket-desktop) | Build & connect | 10 desktop & IDE apps |
| [aimarket-hub](https://github.com/alexar76/aimarket-hub) | AIMarket core | reference federation server |
| [aimarket-mcp](https://github.com/alexar76/aimarket-mcp) | MCP gateways | web fetch/search + Metis verify |
| [aimarket-oracle-gateway](https://github.com/alexar76/aimarket-oracle-gateway) | MCP gateways | 35 pay-per-call oracle tools |
| [aimarket-playground](https://github.com/alexar76/aimarket-playground) | Build & connect | browser golden path |
| [aimarket-plugins](https://github.com/alexar76/aimarket-plugins) | AIMarket core | 15 hub plugins |
| [aimarket-protocol](https://github.com/alexar76/aimarket-protocol) | AIMarket core | the open standard |
| [aimarket-school](https://github.com/alexar76/aimarket-school) | Learn & explore | 13 clip lessons |
| [aimarket-sdks](https://github.com/alexar76/aimarket-sdks) | Build & connect | Dart, TypeScript, Rust |
| [aimarket-widget](https://github.com/alexar76/aimarket-widget) | Build & connect | embeddable storefront |
| [alien-monitor](https://github.com/alexar76/alien-monitor) | Observability | live 3D ecosystem graph |
| [argus](https://github.com/alexar76/argus) | The client you run | demand-side reference agent |
| [atlas](https://github.com/alexar76/atlas) | Physical world | planetary sensor map over GAIA |
| [attested-memory](https://github.com/alexar76/attested-memory) | Verifiable memory | verifiable memory for AI agents |
| [basanos](https://github.com/alexar76/basanos) | Trust & security | Solidity assurance at a pin |
| [cite-desks](https://github.com/alexar76/cite-desks) | Physical world | evidence desks on ATLAS / GAIA rails |
| [create-aimarket-agent](https://github.com/alexar76/create-aimarket-agent) | Build & connect | provider scaffold generator |
| [dioscuri](https://github.com/alexar76/dioscuri) | Community & broadcast | twin community agents |
| [dolos](https://github.com/alexar76/dolos) | Trust & security | dynamic EVM red team (fork-isolated) |
| [domain-operator-kit](https://github.com/alexar76/domain-operator-kit) | Real-world commerce | domains on Openprovider or Porkbun Sandbox |
| [esim-operator-kit](https://github.com/alexar76/esim-operator-kit) | Real-world commerce | travel eSIMs for people and AI agents |
| [gaia](https://github.com/alexar76/gaia) | Physical world | attested IoT readings |
| [helios](https://github.com/alexar76/helios) | Community & broadcast | yaml → voiced video → YouTube |
| [hestia](https://github.com/alexar76/hestia) | Hosted runtime | isolated hosted runtime · not Hub, not Factory |
| [histor](https://github.com/alexar76/histor) | Trust & security | MCP tool-definition transparency log |
| [linked-in-profile-coach](https://github.com/alexar76/linked-in-profile-coach) | Example app | Flutter + SDK, real product |
| [logos](https://github.com/alexar76/logos) | Observability | read-only federation analytics |
| [lottery](https://github.com/alexar76/lottery) | Verifiable compute | unbiasable on-chain draws · machine UBI |
| [mcp-tool-set-digest](https://github.com/alexar76/mcp-tool-set-digest) | Trust & security | hash of an MCP server's tool list |
| [metis](https://github.com/alexar76/metis) | Verifiable compute | the verification tier |
| [momus](https://github.com/alexar76/momus) | Trust & security | HTTP/federation red team |
| [oracles](https://github.com/alexar76/oracles) | Verifiable compute | 17 signed math capabilities |
| [platon](https://github.com/alexar76/platon) | Verifiable compute | educational cave for oracle #1 |
| [pulse-terminal](https://github.com/alexar76/pulse-terminal) | Agent Capital Exchange | capital-markets dashboard |
| [signal-hunt](https://github.com/alexar76/signal-hunt) | Learn & explore | investigation game + lab |
| [skopos](https://github.com/alexar76/skopos) | Observability | fleet nginx/Apache + Security Center |
| [symmartys](https://github.com/alexar76/symmartys) | Real-world commerce | VAT, LEI, registers, FX, sanctions, timestamps, web capture & timers |
| [themis](https://github.com/alexar76/themis) | Trust & security | publish-time admission gate |
| [theoros](https://github.com/alexar76/theoros) | Community & broadcast | Sovereignty Canon · `#the-canon` |
| [treasury](https://github.com/alexar76/treasury) | Trust & security | separate bounty payer |
| [use-cases-portal](https://github.com/alexar76/use-cases-portal) | Learn & explore | onboarding rails + direction boards |
| [warden](https://github.com/alexar76/warden) | Trust & security | MCP security firewall library |

---

<sub>Stack: Python · FastAPI · Dart/Flutter · TypeScript · Solidity · Tauri · Next.js · Docker</sub>
