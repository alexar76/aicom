# Deploy the whole ecosystem — greenfield quick-start

A tiered runbook for standing up the full public ecosystem on a bare Ubuntu VPS. It wraps
the existing deploy scripts — it does **not** introduce a new deploy engine. Start at the
level you need and stop there; each level builds on the one before it.

For the operations-grade reference (partial redeploys, the Hub-redeploy hazard, the exact
manual step order), see **[`deploy-ecosystem.md`](./deploy-ecosystem.md)**.

---

## 1. What "the ecosystem" is

| Component | What it does | Container / process |
|-----------|--------------|---------------------|
| **Factory** | Builds and ships AI products (the `aicom-app` Compose stack) | `aicom-app-1` |
| **Hub** | AIMarket Protocol v2 federation hub — discovery, channels, invoke, settle | `modelmarket-hub` |
| **Mesh** | Service-mesh API that wires products together | `aicom-mesh-api` |
| **ARGUS-3** | Personal agent + WARDEN MCP firewall (reference client) | `argus` / `:8787` |
| **Alien Monitor** | 3D ecosystem visualizer (UNIVERSE / TEST / REAL modes) + **Pulse** terminal | `alien-monitor`, Pulse |
| **Lottery relayer** | UNI-mode relayer for live Monitor feed (optional; step may WARN) | `:9195` |
| **Ecosystem landing** | Public map at [modeldev.modelmarket.dev](https://modeldev.modelmarket.dev) | nginx static / step 7 |
| **Oracles** | Seventeen verifiable-math oracles on [oracles.modelmarket.dev](https://oracles.modelmarket.dev) (+ Platon UMBRAL cave) | **separate host (L4)** |
| **On-chain** (optional) | Base-mainnet contracts: Escrow, capability NFT, Agent Lottery | Foundry deploy |

**Not in `deploy_ecosystem.sh`:** Metis, DIOSCURI, HELIOS — run separately if needed; see [§What one VPS does not include](#9-what-one-vps-does-not-include).

The onboarding levels:

| Level | Goal | One command |
|-------|------|-------------|
| **L1** | Try it locally (Factory only) | `./scripts/quickstart.sh` |
| **L2** | Self-host the **core fleet** on one VPS | `./scripts/quickstart_ecosystem.sh` (preflight wrapper) or `./scripts/deploy_ecosystem.sh` |
| **L3** | Production public (DNS + TLS + verify) | `./scripts/quickstart_ecosystem.sh --public-url https://…` |
| **L4** | Oracle host (**separate machine** by default) | `./scripts/setup-oracles-platon-on-host.sh` |

The auth model for *consuming* the Hub is **Ed25519** (the SDK signs each invoke; the wallet
key is a 32-byte Ed25519 seed, not an Ethereum key). secp256k1/EIP-712 is optional and only
used for on-chain channel debits. See the [AIMarket SDK docs](https://github.com/alexar76/aimarket-sdks/blob/main/docs/en.md) and
the [Python agent](https://github.com/alexar76/aimarket-agent/blob/main/docs/en.md) (stateless, no wallet) for the consumer side.

---

## 2. Prerequisites

On the target Ubuntu VPS, before any level:

- **Docker Engine + Compose v2** (`docker compose`, not the legacy `docker-compose`).
- **nginx** — TLS termination and reverse proxy (Levels 3–4).
- **DNS A/AAAA records** pointing at the host you run on (Level 3+):
  - `magic-ai-factory.com`, `www.magic-ai-factory.com` → Factory host
  - `modelmarket.dev`, `www.modelmarket.dev` → Factory host
  - `oracles.modelmarket.dev` → **Oracle host** (`78.17.126.214`), directly (no factory proxy)
- **A populated `.env`** in the repo root. Copy `.env.example` and set at least one LLM key:

```bash
cp .env.example .env
# then set, e.g.:
#   DEEPSEEK_API_KEY=...
#   ANTHROPIC_API_KEY=...
# optional port overrides:
#   AICOM_PORT_FRONTEND=9080
#   AICOM_PORT_API=9081
```

Prefer file secrets for LLM keys (`data/secrets/llm/<provider>_api_key` + the
`docker-compose.secrets.yml` overlay) over inline `environment:` entries — see the comments
in `.env.example`.

---

## 3. Level 1 — Try it locally

Factory only. Builds the image, runs the stack, and enqueues a demo product end to end:

```bash
./scripts/quickstart.sh                      # build + run + landing demo
./scripts/quickstart.sh --no-build           # reuse the existing image
./scripts/quickstart.sh "Your product idea"  # full_software profile from your idea
```

What it does: `./run.sh` (build) → run → `./demo.sh --no-open` (enqueue a demo product).
Watch progress in **Admin → Pipeline** at `http://localhost:9080`. A no-Docker sample build
replay lives at `docs/sample-output/build-replay-spliteasy.json`.

---

## 4. Level 2 — Self-host the core fleet (one VPS)

**Recommended wrapper** (Docker preflight + `.env` check + deploy + next steps):

```bash
./scripts/quickstart_ecosystem.sh
./scripts/quickstart_ecosystem.sh --skip-verify          # faster; not for prod
./scripts/quickstart_ecosystem.sh --public-url https://…   # forwarded to deploy engine
```

The wrapper calls **`scripts/deploy_ecosystem.sh`** — the source of truth. You can invoke it
directly:

```bash
./scripts/deploy_ecosystem.sh
```

The script runs, in this fixed order:

1. **Factory** — `./scripts/deploy.sh` (`aicom-app-1`)
2. **Hub** — `./scripts/deploy_hub.sh` (`modelmarket-hub`, **never** the subfolder Compose)
3. **Mesh** — `./scripts/deploy_mesh.sh` (`aicom-mesh-api`)
4. **ARGUS-3** — `./scripts/deploy_argus.sh` (`:8787`)
5. **Alien Monitor + Pulse** — `./scripts/deploy_alien_monitor.sh`
6. **UNI lottery relayer** — `./scripts/deploy_lottery_uni.sh` (non-fatal; logs a WARN if it fails)
7. **Ecosystem landing** — `./scripts/deploy_ecosystem_landing.sh` (non-fatal; `modeldev.modelmarket.dev`)

It then **warms** the Factory API (`/api/health`, `/api/products`) and runs
`./scripts/verify_ecosystem_full.sh` (**17+ smoke checks**) unless you pass `--skip-verify`.

### Ports (host)

| Service | Host port | Health / entry |
|---------|-----------|----------------|
| Factory API | `:9081` | `GET /api/health` |
| Factory UI (frontend) | `:9080` | `GET /` |
| Hub | `:9083` | `GET /.well-known/ai-market.json` |
| Mesh | `:8090` | `GET /v1/stats` |
| ARGUS | `:8787` | `GET /health` |
| Alien Monitor | `:9100` | `GET /api/health` |
| Pulse terminal | `:5199` | `GET /` |
| UNI lottery relayer | `:9195` | `GET /healthz` |
| Ecosystem landing | nginx vhost | `https://modeldev.modelmarket.dev/` (after L3 TLS) |

> **The public UI port is `:9080`, not the old `:8080`.** nginx proxies the public domain to
> `127.0.0.1:9080`.

Flags:

```bash
./scripts/deploy_ecosystem.sh --skip-verify   # faster; skips the smoke suite (not for prod)
```

---

## 5. Level 3 — Production public

### 5.1 Point DNS

A/AAAA records for `magic-ai-factory.com`, `www.magic-ai-factory.com`, `modelmarket.dev`,
and `www.modelmarket.dev` must resolve to this host **before** issuing certificates.

### 5.2 Deploy with the public URL baked in

```bash
./scripts/deploy_ecosystem.sh --public-url https://magic-ai-factory.com
```

`--public-url` is forwarded to `deploy.sh` so `NEXT_PUBLIC_SITE_URL` is set for the Next.js
build (Open Graph, sitemap, server-side metadata). If TLS is not live yet you may use
`http://magic-ai-factory.com` first, then rebuild the app image once HTTPS is up.

### 5.3 TLS one-shots (run as root)

**Hub vhost + AIMarket Hub + Let's Encrypt** for `modelmarket.dev`:

```bash
sudo CERTBOT_EMAIL=you@example.com ./scripts/setup-modelmarket-ssl.sh
```

This installs `deploy/nginx/modelmarket.dev.conf`, builds `modelmarket-hub:latest` from the
**repo root** context, runs the hub on `127.0.0.1:9083`, enables `certbot.timer`, and issues
the cert for `modelmarket.dev` + `www.modelmarket.dev`.

**Factory vhost** for `magic-ai-factory.com` (per [`production-domain.md`](./production-domain.md)):

```bash
sudo cp deploy/nginx/magic-ai-factory.com.conf /etc/nginx/sites-available/magic-ai-factory.com
sudo ln -sf /etc/nginx/sites-available/magic-ai-factory.com /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

sudo certbot --nginx \
  -d magic-ai-factory.com -d www.magic-ai-factory.com \
  --non-interactive --agree-tos --redirect \
  -m YOUR_EMAIL@example.com
```

After HTTPS is live, set `NEXT_PUBLIC_SITE_URL=https://magic-ai-factory.com` in `.env` and
rebuild so the bundle picks it up:

```bash
docker compose build app --no-cache
docker compose up -d
```

The public Alien Monitor is served at `https://magic-ai-factory.com/monitor/` (nginx proxies
`/monitor/` → `127.0.0.1:9100`; `deploy_alien_monitor.sh` patches the live Certbot vhost if
the block is missing).

### 5.4 Verify

```bash
./scripts/verify_ecosystem_full.sh
```

Expect **`17/17 PASS`**.

---

## 6. Level 4 — Oracle host

The oracles run on a **separate machine** (`78.17.126.214`). **`deploy_ecosystem.sh` does NOT
deploy oracles or Platon** — `oracles/` and `platon/` in this monorepo are archival mirrors of
the external stack. Set them up on the Platon host, then federate from the Factory host.

### 6.1 On the Platon host (`78.17.126.214`, as root)

The Platon app must already be listening on `127.0.0.1:8080` with
`PUBLIC_URL=https://oracles.modelmarket.dev`. Then:

```bash
sudo CERTBOT_EMAIL=you@example.com ./scripts/setup-oracles-platon-on-host.sh
```

This installs `deploy/nginx/oracles.modelmarket.dev.conf`, verifies Platon on
`127.0.0.1:8080/api/health`, and issues the cert for `oracles.modelmarket.dev`.

### 6.2 From the Factory host — federate

```bash
./scripts/announce-platon-oracles.sh
```

This reads the admin token (`data/secrets/aimarket_admin_token.txt`), POSTs
`/ai-market/v2/federation/announce` to the local hub (`:9083`) with Platon's well-known URL
and signer public key, then triggers a federation crawl.

Verify the oracle host:

```bash
curl -s https://oracles.modelmarket.dev/.well-known/ai-market.json | jq '{hub_url, manifest_url, capabilities_count}'
curl -s https://oracles.modelmarket.dev/api/health | jq '{status, kappa, order_parameter}'
```

The seventeen oracles (Platon, Chronos, Lattice, Murmuration, Lumen, Colony, Turing, Percola, Fermat, Ablation, Landauer, Sortes, Gauss, Aestus, Betti, Kantor, Fourier) and the
economy loop are documented in [`oracles/docs/en.md`](../oracles/docs/en.md).

---

## 7. Optional — On-chain (Base, chain 8453)

Kept **separate** from container orchestration. These deploy Solidity contracts to Base
mainnet with Foundry. Both default to a gas-free dry run; pass `broadcast` to spend real gas.

**Ecosystem core** — FakeUSDT + `AIMarketEscrow` + `AIMarketCapabilityNFT`
(ACEX is intentionally excluded — the audit flagged AuditPool TWAP + PulseAMM as HIGH):

```bash
./scripts/deploy_ecosystem_base.sh            # dry-run (no gas)
./scripts/deploy_ecosystem_base.sh broadcast  # real deploy
```

**Agent Lottery** — `AIAgentLottery` (native-ETH tickets, admin/governance/treasury set to
`OWNER` at deploy):

```bash
./scripts/deploy_lottery_base.sh              # dry-run (simulate, NO gas)
./scripts/deploy_lottery_base.sh broadcast    # real deploy
```

Both read the burner key from `$BURNER_KEYFILE` (default `~/.aicom-base-deployer.json`) and use `BASE_RPC` (default `https://mainnet.base.org`). The ecosystem-core script 2-step-transfers Escrow/NFT ownership to `OWNER` after a broadcast (`OWNER` must then call `acceptOwnership`); the lottery instead sets admin/governance/treasury to `OWNER` at deploy, with no post-deploy transfer. These are real funds — keep stakes minimal.

---

## 8. Multi-host topology

```
┌──────────────────────────────────────────────┐      ┌────────────────────────────────────┐
│  FACTORY FLEET — 5.129.212.122                │      │  ORACLE HOST — 78.17.126.214        │
│                                                │      │                                      │
│  Factory  aicom-app-1        :9081 API/:9080 UI│      │  Platon Shadow Oracle  127.0.0.1:8080│
│  Hub      modelmarket-hub    :9083             │ fed  │  Oracle family (17 oracles)          │
│  Mesh     aicom-mesh-api     :8090             │◄────►│                                      │
│  ARGUS    reference agent    :8787             │ announce-platon-oracles.sh (factory host)   │
│  Monitor  alien-monitor      :9100             │      │  oracles.modelmarket.dev (own nginx) │
│  Pulse    terminal           :5199             │      │  NOT in deploy_ecosystem.sh (L4)     │
│  Lottery relayer (UNI)       :9195             │      │                                      │
│  Landing  modeldev…          nginx             │      └────────────────────────────────────┘
│                                                │
│  magic-ai-factory.com  /  modelmarket.dev      │
└──────────────────────────────────────────────┘
```

`deploy_ecosystem.sh` / `quickstart_ecosystem.sh` cover the **left box** (steps 1–7). The oracle
host is provisioned with `setup-oracles-platon-on-host.sh` (Level 4 — **separate machine** by
default) and joined to the federation with `announce-platon-oracles.sh` (from the Factory host).

You *can* run oracles on the same VPS as the factory (single-machine lab) by pointing
`oracles.modelmarket.dev` at the same IP and running the L4 scripts there too — not the default
production topology.

---

## 9. What one VPS does **not** include

| Component | Why | How to add |
|-----------|-----|------------|
| **17 oracles + portal** | Level 4 — separate host in production docs | `setup-oracles-platon-on-host.sh` + `announce-platon-oracles.sh` |
| **Base on-chain contracts** | Optional; real gas | `deploy_ecosystem_base.sh broadcast`, `deploy_lottery_base.sh broadcast` |
| **Metis** | Cognition tier; not wired into fleet script | Deploy `metis/` separately; Factory can call `/v1/verify` |
| **DIOSCURI / HELIOS** | Community / broadcast satellites | Separate repos; not part of core fleet |
| **Prometheus** | Observability optional layer | `./scripts/deploy_observability.sh` (see ecosystem audit notes) |

---

## 10. Verify & operate

### Full smoke (17+ checks)

```bash
./scripts/verify_ecosystem_full.sh
```

Checks Factory core (`/api/health`, frontend `:9080`, `/api/products`, trust-metrics, security
store, funnel lead, admin dashboard, product P&L), Hub (`.well-known`, `stats/live`, capital
pricing), Mesh (`/v1/stats`), Pulse (`:5199`), Alien Monitor (UNIVERSE health + TEST/REAL/
UNIVERSE in-process probes), and the UNI lottery (deployed `evm_lottery`, relayer `/healthz`,
live lottery metrics). Override targets with `FACTORY_URL`, `HUB_URL`, `MESH_URL`,
`MONITOR_URL`, `PULSE_URL`, `LOTTERY_RELAYER_URL`.

### Partial redeploys

| Goal | Command |
|------|---------|
| Factory only | `./scripts/deploy.sh` |
| Hub only | `./scripts/deploy_hub.sh` |
| Mesh + Monitor (demo stack) | `./scripts/deploy_demo_stack.sh` (assumes Factory + Hub already up) |
| Verify only | `./scripts/verify_ecosystem_full.sh` |

### Hub redeploy hazard — read this

> **Do NOT use the subfolder Compose to redeploy the Hub.** Always use `./scripts/deploy_hub.sh`.
>
> ```bash
> cd aimarket-hub && docker compose up -d --build   # WRONG — breaks image/context; Hub can disappear
> ```
>
> `deploy_hub.sh` builds from the **monorepo root** (`modelmarket-hub:latest`, container
> `modelmarket-hub`), matches the TLS setup in `setup-modelmarket-ssl.sh`, and replaces the
> container safely. The `aimarket-hub/docker-compose.yml` file is kept for local dev reference
> only. Never stop/remove `modelmarket-hub` without immediately running `deploy_hub.sh`.

---

## 11. Related docs

- [`deploy-ecosystem.md`](./deploy-ecosystem.md) — operations reference (manual order, partial redeploys)
- [`production-domain.md`](./production-domain.md) — `magic-ai-factory.com` nginx + TLS
- [`production-modelmarket-dev.md`](./production-modelmarket-dev.md) — hub domain, DNS, oracle host
- [`oracles/docs/en.md`](../oracles/docs/en.md) — the seventeen oracles and the economy loop
- [AIMarket SDK docs](../aimarket-sdks/docs/en.md) · [Python agent](../aimarket-agent/docs/en.md) — consume the Hub

---

🇬🇧 [English](./quickstart-ecosystem-deploy.md) · 🇷🇺 [Русский](./quickstart-ecosystem-deploy.ru.md) · 🇪🇸 [Español](./quickstart-ecosystem-deploy.es.md) · 🇫🇷 [Français](./quickstart-ecosystem-deploy.fr.md) · 🇨🇳 [中文](./quickstart-ecosystem-deploy.zh.md)
