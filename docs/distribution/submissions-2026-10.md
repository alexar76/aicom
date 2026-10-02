# Directory submissions — October 2026

Ready-to-file entries for four public lists. Every fact below was checked on 2026-10-01; re-run
the checks at the end before opening a PR, because the lists move daily. All four are pull requests
on GitHub, filed from the owner's account.

| # | Where | What | PRs |
|---|---|---|---|
| 1 | [xpaysh/awesome-x402](https://github.com/xpaysh/awesome-x402) | AIMarket Hub | 1 |
| 2 | [sudeepb02/awesome-erc8004](https://github.com/sudeepb02/awesome-erc8004) | AIMarket Hub, HISTOR, WARDEN | 1 |
| 3 | [docker/mcp-registry](https://github.com/docker/mcp-registry) | WARDEN (local, Docker-built image) and AIMarket Hub (remote) | 2 |
| 4 | [punkpeye/awesome-mcp-servers](https://github.com/punkpeye/awesome-mcp-servers) | nothing to file: WARDEN is already listed | 0 |

Already listed and not to be re-submitted: punkpeye/awesome-mcp-servers has `alexar76/aimarket-plugins`,
`alexar76/aimarket-mcp`, `alexar76/aimarket-oracle-gateway`, `alexar76/argus` and `alexar76/warden`
(merged in PR #12774). PulseMCP, mcp.so and Glama index us already.

PRs 1 and 2 were filed on 2026-10-01 (xpaysh/awesome-x402#1680, sudeepb02/awesome-erc8004#120). Their
bodies end with a "Made with Cursor" footer that is not part of the text below; edit it out of both
from the owner's account.

---

## 1. awesome-x402 — AIMarket Hub

Their rules ([CONTRIBUTING](https://github.com/xpaysh/awesome-x402/blob/main/CONTRIBUTING.md)): one
change per PR, exact format `- [Name](link) - Description.`, working links.

**Section:** `## 🤖 AI Agent Integration` (where the other agent marketplaces sit — MAXIA,
WorkProtocol). Append at the end of that section's list.

**Line to add:**

```markdown
- [AIMarket Hub](https://modelmarket.dev) - Federated market of agent capabilities (signed weather, air-quality and sensor data, verifiable randomness and oracles) sold per call over MCP (`https://modelmarket.dev/mcp`), A2A and HTTP 402. Every 402 carries the x402 V2 `PAYMENT-REQUIRED` header plus V1 `accepts`, USDC on Base, `payTo` is the seller (no custody) and the EIP-3009 nonce is bound to the call; results come with signed receipts. ERC-8004 agent [#96682](https://8004scan.io/agents/base/96682). ([Discovery](https://modelmarket.dev/.well-known/ai-market.json))
```

**PR title:** `Add AIMarket Hub (x402 V2, seller-direct, MCP + A2A)`

**PR body:**

```markdown
Adds AIMarket Hub to AI Agent Integration.

- What: a federated market where agents buy capabilities per call; MCP endpoint https://modelmarket.dev/mcp
- x402: every 402 response carries the V2 `PAYMENT-REQUIRED` header and the V1 `accepts` body;
  USDC on Base; `payTo` is the selling provider, not the platform; the EIP-3009 nonce commits to the call
- Discovery: https://modelmarket.dev/.well-known/ai-market.json (signed), ERC-8004 agent #96682 on Base
- Source: https://github.com/alexar76/aimarket-hub (Apache-2.0)
```

Do **not** claim a CDP Bazaar listing for the hub — the hub itself is not in the Bazaar. What is
there since 2026-10-02 are two separate x402 routes, `https://modelmarket.dev/x402/histor-check`
and `/x402/warden-scan` ($0.001, service name "AIMarket"); mention them only as those two
services, not as the hub's listing.

---

## 2. awesome-erc8004 — three registered agents

Their rules ([CONTRIBUTING](https://github.com/sudeepb02/awesome-erc8004/blob/main/CONTRIBUTING.md)):
directly related to ERC-8004, working links, no dead projects. All three are live agents on Base.

**Section:** `## Builder Projects` → `### Infrastructure & SDKs` (HISTOR, WARDEN) and
`### Commerce & Escrow` (AIMarket Hub). Append to each list.

**Under `### Commerce & Escrow`:**

```markdown
- [AIMarket Hub](https://modelmarket.dev) - Federated agent-capability market registered as ERC-8004 agent [#96682 on Base](https://8004scan.io/agents/base/96682). Declares that identity inside its signed `/.well-known/ai-market.json` and marks it self-declared, so a reader confirms it against the IdentityRegistry; sells per call over MCP, A2A and x402 with escrow channels and signed receipts. Apache-2.0.
```

**Under `### Infrastructure & SDKs`:**

```markdown
- [HISTOR](https://histor.modelmarket.dev) - Transparency log for MCP servers, ERC-8004 agent [#96683 on Base](https://8004scan.io/agents/base/96683). Observes the official MCP registry daily, pins each server's tool set in an append-only Merkle log and issues signed labels when definitions change — a pre-connect trust signal an agent can query (`POST /api/v1/check`). MIT.
- [WARDEN](https://github.com/alexar76/warden) - Open-source MCP firewall, ERC-8004 agent [#96684 on Base](https://8004scan.io/agents/base/96684). Scans tool definitions for prompt injection, secret requests, exfiltration and hidden Unicode before a host exposes them to a model; deterministic published rules and a reproducible false-positive survey. MIT, `npm i @aimarket/warden`.
```

**PR title:** `Add AIMarket Hub, HISTOR and WARDEN (ERC-8004 agents on Base)`

**PR body:**

```markdown
Three live agents registered on the canonical IdentityRegistry on Base (0x8004A169…a432),
all owned by the operator wallet 0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a:

| agent | agentId | registration file |
|---|---|---|
| AIMarket Hub | 96682 | https://modelmarket.dev/.well-known/erc-8004/aimarket-hub.json |
| HISTOR | 96683 | https://modelmarket.dev/.well-known/erc-8004/histor.json |
| WARDEN | 96684 | https://modelmarket.dev/.well-known/erc-8004/warden.json |

Domain proof: https://modelmarket.dev/.well-known/agent-registration.json lists all three.
Registration txs: see https://8004scan.io/agents/base/96682 (block 52046664).
```

---

## 3. Docker MCP Catalog — two PRs

Rules: [CONTRIBUTING](https://github.com/docker/mcp-registry/blob/main/CONTRIBUTING.md). Fork, add a
folder under `servers/`, CI must pass, a Docker reviewer approves, commits are squashed. Tooling:
Go 1.24+, Docker Desktop, [Task](https://taskfile.dev/). One server per PR.

### 3a. WARDEN — local server, Docker builds and signs the image

Source repo `https://github.com/alexar76/warden` has a root `Dockerfile` (node:22-slim, `npm ci`,
entrypoint `node dist/mcp-server.js`, stdio, **no env or secrets required**), `package-lock.json`
and an MIT `LICENSE`. Tools the server lists (nine): `vet_mcp_server`, `static_scan_tools`,
`classify_sensitive_tools`, `check_egress_url`, `canonicalize_json`, `list_scan_rules`,
`status_mcp_server`, `approve_mcp_server`, `revoke_mcp_server` (the last two change pins only with
`WARDEN_ALLOW_PIN_CHANGES=1`).

```bash
git clone https://github.com/<you>/mcp-registry && cd mcp-registry
task create -- --category security https://github.com/alexar76/warden
# builds the image from the Dockerfile, runs it, checks tools/list, writes servers/warden/server.yaml
```

**File this one only after WARDEN 0.8.2 is on npm and on `alexar76/warden`:** 0.8.0/0.8.1 have a wrap
bypass (see the WARDEN CHANGELOG), and the catalog builds the image from the pinned commit.

Then make `servers/warden/server.yaml` read (use the commit of the 0.8.2 release on `alexar76/warden`;
the one below, from 2026-10-01, is 0.8.1 and must be replaced):

```yaml
name: warden
image: mcp/warden
type: server
meta:
  category: security
  tags:
    - security
    - mcp
    - firewall
    - prompt-injection
    - tool-poisoning
about:
  title: WARDEN
  description: MCP security firewall. Scans tool definitions for prompt injection, secret requests, exfiltration and hidden Unicode before a host exposes them to a model. Deterministic published rules (version and digest in every verdict); no network calls, no secrets.
  icon: https://modelmarket.dev/.well-known/erc-8004/warden.png
source:
  project: https://github.com/alexar76/warden
  commit: b06a80a91a5dadd20819bf2a4b537cfb49bc01b4
```

No `config:` block — the server needs nothing configured. Test before the PR:

```bash
task build -- --tools warden
task catalog -- warden
docker mcp catalog import $PWD/catalogs/warden/catalog.yaml
# Docker Desktop → MCP Toolkit → enable WARDEN, call list_scan_rules from a client
docker mcp catalog reset
```

**PR title:** `Add WARDEN (MCP security firewall)`
**PR body:** what it does (one paragraph from `about.description`), MIT, no credentials needed,
link to the reproducible survey `https://github.com/alexar76/warden/blob/main/docs/mcp-survey.md`.

### 3b. AIMarket Hub — remote server

No Dockerfile needed; it is already hosted.

```bash
task remote-wizard
# name: aimarket-hub · category: search · transport: streamable-http
# url: https://modelmarket.dev/mcp · OAuth: no
```

Expected `servers/aimarket-hub/server.yaml`:

```yaml
name: aimarket-hub
type: remote
dynamic:
  tools: true
meta:
  category: search
  tags:
    - search
    - data
    - weather
    - remote
about:
  title: AIMarket Hub
  description: Live, signed real-world data and verifiable computation sold per call by independent providers — weather, air quality, nearby sensors, fair randomness and a searchable market of more. The first calls per caller are free; every result carries a signed receipt.
  icon: https://modelmarket.dev/.well-known/erc-8004/aimarket-hub.png
remote:
  transport_type: streamable-http
  url: https://modelmarket.dev/mcp
```

plus `tools.json` = `[]` and `readme.md` with the documentation link `https://modelmarket.dev/`.

**PR title:** `Add AIMarket Hub (remote, streamable-http)`
**PR body:** endpoint, no auth, tools discovered dynamically (direct tools `weather_now`,
`air_quality_now`, `nearby_sensors`, `fair_random` plus `market_search` / `market_invoke`), the free
per-caller trial and what happens after it (HTTP 402 with x402 terms), Apache-2.0 source link.

---

## 4. awesome-mcp-servers — already done

`alexar76/warden` has its own line under Security (PR #12774, merged). Nothing to file.

---

## Checks to re-run before filing

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://modelmarket.dev/mcp -X POST \
  -H 'content-type: application/json' -H 'accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"check","version":"0"}}}'   # 200
for id in 96682 96683 96684; do curl -s https://8004scan.io/agents/base/$id | grep -o '<title>[^<]*'; done
curl -s https://modelmarket.dev/.well-known/agent-registration.json      # three registrations
git ls-remote https://github.com/alexar76/warden HEAD                     # commit for 3a
npm view @aimarket/warden version                                         # 0.8.1
```
