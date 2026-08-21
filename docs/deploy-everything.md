# Deploy everything — one box, one command

The **everything tier**: the entire production ecosystem — 36 long-lived containers plus 2 one-shots — on a single machine, reached over plain HTTP at `http://<ip>:<port>`.

This page sits under [running.md](running.md), which is the umbrella for *every* way to run this monorepo. Nothing here replaces the core tier; the everything tier is a third door alongside `./start.sh` (core) and `./start.sh --full` (the 7-step fleet script). If you only want to see the Factory build something, stop reading and run `./start.sh` — see [Which tier](#which-tier).

> **Read [What it costs](#what-it-costs) before you run this.** It is ~12 GB of images, a 30–120 minute first build, and it wants 32 GB of RAM and 100 GB of disk. Finding that out halfway through a 12 GB pull is a bad afternoon.

---

## The one command

```bash
./start.sh --everything
```

That is the whole thing. It drives one compose project on one bridge network:

```bash
docker compose -p aicom \
  -f docker-compose.yml \
  -f docker-compose.core.yml \
  -f docker-compose.everything.yml \
  up -d --build
```

**One project on purpose.** The satellite compose files disagree about which network they live on — `lottery/` wants an external `ecosystem_ecosystem`, `momus/`, `gaia/`, `atlas/` and `oracles/` want an external `ecosystem`, `platon/` *creates* `ecosystem`, `metis/` uses `metis-net`, core uses `aicom_net`. Six names for what has to be one bridge. On three hosts nobody noticed. Merged into a single project they all land on `aicom_net`, every service resolves its neighbours by compose service name, and the whole class of "everything is green but nothing can talk" failures goes away.

### Flags

| Flag | What it does |
|---|---|
| *(none)* | Core tier. Unchanged — see [running.md](running.md#core-stack-startsh). |
| `--everything` | The full tier documented on this page. |
| `--bind <addr>` | Which host address to publish on. Default `127.0.0.1`. See [Binding](#binding-localhost-vs-0000). |
| `--host-ip <addr>` | Override the address printed in URLs and baked into the Factory storefront. See [Addressing](#addressing-no-nginx-no-tls-no-domains). |
| `--no-build` | Reuse existing images. Turns a 45-minute first run into a 2-minute one. |
| `--no-open` | Don't open a browser. |
| `--logs` | Follow logs for the tier. |
| `--down` | Stop the tier. **Keeps** `./data` and all named volumes. |
| `--reset-chain` | Stop, then delete `data/alien-monitor/universe/anvil-state` and the lottery `shared` volume. The disk-reclaim escape hatch — see [Teardown](#teardown-and-reclaiming-disk). |
| `--full` | Unchanged — the existing 7-step `scripts/quickstart_ecosystem.sh` fleet. Not this. |

### What "one command" guarantees

1. **It refuses before it wastes your time.** Disk, RAM and CPU are checked *before* the first pull, with real numbers, and it offers the core tier instead of dying at 80% of a 12 GB build.
2. **It does not lie about readiness.** No "ready" banner and no browser until every service has answered a health check. If something didn't come up you get the service name and the reason, and nothing opens.
3. **Credentials print exactly once.** Generated into a `chmod 600` gitignored `.env`, printed in one block at the end of the *first* run. On later runs it prints where they live, not what they are. No secret is ever echoed into a log line, a health message or an error.
4. **Nothing touches a real chain.** `AIFACTORY_CRYPTO_ENABLED=0` everywhere. The only chain is an ephemeral local Anvil funded with the well-known `test test … junk` accounts. The launcher refuses to start if a mainnet key is present in the environment.

---

## What it costs

Numbers are reasoned from the Dockerfiles, not weighed on a stopwatch — treat them as ±30% sizing guidance and re-measure on your first real build.

| | Everything tier | Core tier |
|---|---|---|
| **Distinct images** | 11–14 GB | ~6 GB |
| **Build cache (first run)** | +8–15 GB, mostly reclaimable | +3–5 GB |
| **Disk — hard floor** | **60 GB free** (below this the launcher refuses) | 20 GB |
| **Disk — recommended** | **100 GB** if you intend to leave it running | 40 GB |
| **RAM at idle** | 8–10 GB | ~2 GB |
| **RAM — hard floor** | **16 GB** (refuses below; 16–32 GB warns — it will swap) | 8 GB |
| **RAM — recommended** | **32 GB**, 64 GB comfortable | 8 GB |
| **CPU** | 4 cores minimum, 8 recommended | 2 cores |
| **First run (build)** | **30–60 min** on 8 cores with good bandwidth; **2 h+** on 4 | 5–15 min |
| **Subsequent runs** | ~2 min with `--no-build` | <1 min |

### Where the disk actually goes

Images are not the problem. Four images dominate the 11–14 GB — the Factory (~4.5–6 GB: Ubuntu + Python 3.12 + Node 20 + a full Playwright/Chromium install + a Next.js production build), alien-monitor (~2–2.5 GB: the Solana toolchain plus `anvil`/`forge`/`cast` and two `forge build` trees), Metis (~0.7–1 GB, one image shared by three containers, so paid once) and SKOPOS (~0.9–1.2 GB). The rest is a long tail of ~12 `python:*-slim` services, 2 `node:22-slim` services and 8 `nginx:alpine` static frontends that share bases and are cheaper than they look.

The two things that *grow* are what fill a disk:

- **Anvil state.** The lottery chain runs `--block-time 1` forever while the relayer drives rounds every 4–5 s, and the Monitor persists its own universe Anvil to `./data/alien-monitor/universe`. Nothing caps or rotates either. **This is the exact failure that took one of our own production hosts to 100% disk and cost an hour to diagnose.** Budget 20–40 GB, and use `--reset-chain` periodically.
- **Container logs.** Only `dioscuri`, `helios`, `helios-worker` and the Metis prod overlay set `logging.options.max-size`. The other ~30 services inherit Docker's unlimited `json-file` default. Budget 10 GB, or set a daemon-wide default in `/etc/docker/daemon.json`.

Plus `./data` itself — products, sandboxes, SQLite, the Prometheus TSDB and Grafana state — which reaches 10–20 GB over a few weeks of real use.

### Under load it is a different machine

The idle figure assumes nothing is happening. One real Factory pipeline run spawns headless Chromium plus sandboxed compose previews (`AIFACTORY_SANDBOX_COMPOSE_PREVIEW=1`, up to `AIFACTORY_MAX_RUNNING_TASKS=12`), and the two Metis nodes are provisioned for 8 GB each in production. 16 GB will swap-thrash under a pipeline run; that is not a prediction, it is what happened on server 2.

### Linux first

The everything tier targets **Linux**. On Docker Desktop for macOS/Windows the `data-init` sidecar's `chown` of the `./data` bind mount to UID 10001 is a no-op against the VM file-sharing layer, so the non-root `app` container may not be able to write its data directory. macOS is best served by the **core** tier, which is explicitly cross-platform.

---

## Which tier

| You are… | Tier | Command |
|---|---|---|
| Trying the project for the first time | **core** | `./start.sh` |
| On a laptop, or on macOS/Windows | **core** | `./start.sh` |
| Demoing "idea → real AI build" | **core** | `./start.sh` |
| Reproducing production on one server to evaluate the whole ecosystem | **everything** | `./start.sh --everything` |
| Working on cross-satellite integration (MOMUS ↔ Treasury ↔ SKOPOS, oracles ↔ hub, Metis verification) | **everything** | `./start.sh --everything` |
| Deploying to real servers with TLS and domains | neither | [deploy-ecosystem.md](deploy-ecosystem.md) |

Core is Factory + Hub + Mesh + Monitor: 6 long-lived containers, one LLM key, 8 GB of RAM. It is not a cut-down everything tier, it is the tier most people want. The everything tier exists because some behaviour — a MOMUS finding routed through SKOPOS to a fix and back through a Metis-gated Treasury payout — cannot be seen with four services running.

---

## What comes up

33 published host ports, all ≥ 1024, all bound to `127.0.0.1` unless you pass `--bind`. (A 34th, 9195, exists only under the opt-in `lottery-uni` profile.) Ports marked **remapped** differ from production; [why](#port-remaps).

### Factory core

| Port | Service | What it is |
|---|---|---|
| 9080 | `app` (web) | Factory storefront + admin (Next.js). The front door. |
| 9081 | `app` (API) | Factory API (FastAPI) + pipeline/director workers, same container. |
| 9082 | `grafana` | Dashboards. Login `admin` + generated password. |
| 9090 | `prometheus` | Metrics, served under `/prometheus/`. |
| 9083 | `hub` | AIMarket Federation Hub — where shipped products list and federate. |
| 8090 | `mesh-api` | Service Mesh API — topology/registry the Monitor's mesh contour reads. |
| 8091 | `mesh-dashboard` | Mesh UI. Its nginx is given a config pointing at `http://mesh-api:8090`; without one it renders an empty shell (see [risks](#troubleshooting)). |
| 9100 | `alien-monitor` | The showpiece: live universe, reputation graph, contours, ARGUS run panel. At `/monitor/`. |
| 5199 | `pulse-terminal` | Pulse (ACEX) terminal — CapShare NAV, Proof-of-Audit, live pricing. |
| 3847 | `aicom-landing` | Standalone AI landing-page generator. |
| — | `data-init` | One-shot: chowns the `./data` bind mount, exits. `app` waits on it. |

### Red team and remediation

| Port | Service | What it is |
|---|---|---|
| 9410 | `momus-backend` | Adversarial-audit satellite. **Control plane** — `/scan`, `/selfaudit`, `/retest`, `/remediate`, `/intel/refresh`, `/a2a/tasks`, all behind `MOMUS_OPERATOR_TOKEN`. |
| 9411 | `momus-treasury` | The payer. Separate service, separate signing key MOMUS never holds, separate volume. |
| 5186 | `momus-frontend` | MOMUS UI. |
| 9450 | `momus-canary` | Deliberately vulnerable target. Without it MOMUS has nothing real to find and the red-team demo is theatre. |
| 9402 | `skopos-remediation` | The conductor: routes a MOMUS finding to the node agent that can fix it. |
| 8501 | `skopos` | Fleet observability dashboard (Streamlit). **Control plane.** |
| 8502 | `skopos` (healthz) | Health endpoint on its own port. |
| — | `skopos-postgres` | SKOPOS's database. Internal only, no host port. |
| 9460 | `logos` | Read-only federation intelligence — source snapshots, rolling z-score anomalies, cross-system correlation. |
| — | `logos-postgres` | LOGOS's database. Internal only, no host port. |

### Verification and oracles

| Port | Service | What it is |
|---|---|---|
| 9111 | `metis-coordinator` | **remapped** — verification tier / factory confidence gate. |
| — | `metis-node-a` / `node-b` | Verification nodes, internal only (8443/8444). |
| 9400 | `oracle-family` | 17 signed math capabilities, one manifest. |
| 9300 | `chronos` | Time oracle. |
| 5180 | `oracles-landing` | Oracle portal. |
| 9200 | `platon-backend` | Platon federated oracle. |
| 9201 | `platon-frontend` | **remapped** — UMBRAL cave app. |
| 9320 | `gaia-backend` | Physical-world oracle gateway — attested IoT sensors + plausibility verify. |
| 5185 | `gaia-frontend` | GAIA UI. |
| 9330 | `atlas` | Sensor map, 52 pins / 6 layers. Polls GAIA every 30 s — repointed at `http://gaia-backend:9320`. |

### Agents

| Port | Service | What it is |
|---|---|---|
| 8787 | `argus` | ARGUS-3 demand-side agent + WARDEN MCP firewall. |
| 8788 | `argus-uni` | Same image, UNI mode. Repointed at `http://lottery-chain:8545`, so it is only meaningful once the lottery layer is up. |
| 8790 | `dioscuri` | Community agent — twin Telegram + Discord bots (Castor/Pollux). Sleeps without tokens; `DIOSCURI_DRY_RUN=1` by default. |
| 8791 | `helios` | Broadcast layer. `HELIOS_DRY_RUN=1` by default — see [unavailable in IP mode](#unavailable-in-ip-mode). |
| — | `helios-worker` | HELIOS queue worker. No port; its inherited `:8791` healthcheck is disabled, because it never binds that port and would otherwise report unhealthy forever while working fine. |

### Lottery (machine UBI)

| Port | Service | What it is |
|---|---|---|
| — | `lottery-chain` | Local Anvil, fake-funded, ephemeral. Internal only — deliberately not published. |
| — | `lottery-deploy` | One-shot: deploys the lottery contracts to that local chain, exits. |
| 8390 | `lottery-relayer` | Draw relayer. |
| — | `lottery-agent` | Participating agent. No port. |
| 5182 | `lottery-showcase` | Lottery economy UI. |
| 9195 | `lottery-relayer-uni` | **Not started.** On its own `lottery-uni` profile, and the launcher prints one line saying so. It needs two things this tier cannot supply: a `LOTTERY_ADDRESS` from a completed Monitor universe bootstrap, and an RPC to the chain that address lives on — the Monitor's *embedded* Anvil, which binds `127.0.0.1` inside the Monitor container (`alien-monitor/backend/universe.py`) and is therefore unreachable from the bridge. `lottery-chain:8545` is **not** a substitute: different chain, the address would not resolve. Start it by hand with both values if you have them. |

### Startup order

You do not need to know this to run it, but you do to read the progress output. The launcher brings services up in dependency layers: `data-init` → `hub` → `app` (its healthcheck has a 120 s start period and realistically takes 60–150 s cold) → `mesh-api`, `mesh-dashboard` → `alien-monitor` (**the slowest step in the stack** — 2–4 minutes, because it deploys Anvil + FakeUSDT + Escrow + NFT inside the container before reporting `blockchain_ready`) → all satellites in parallel → Metis nodes then coordinator → SKOPOS postgres then SKOPOS → lottery, strictly serial: `lottery-chain` healthy → `lottery-deploy` completed → `lottery-relayer` → `lottery-agent`.

Most satellites degrade gracefully rather than hang if a neighbour is missing: the Monitor idles its remote panels, ATLAS shows an empty map, MOMUS records a HELD intent instead of stalling, Treasury conservatively never releases a high/critical bounty without Metis, oracle-family just advertises fewer federated capabilities. The ones that genuinely block are the lottery chain, SKOPOS's postgres, and `data-init`.

---

## Addressing: no nginx, no TLS, no domains

There is no reverse proxy in this tier, no certificates, and no domain names. Every service publishes its own port and you reach it directly at `http://<host-ip>:<port>`.

**Inside** the stack, services address each other by compose service name — `http://hub:9083`, `http://gaia-backend:9320`, `http://lottery-chain:8545`. Never by the host IP: a container reaching its neighbour through the host is a hairpin that breaks the moment the machine sits behind NAT.

### How the host IP is detected

In order: the address on the default route (`ip route get 1.1.1.1` on Linux, `route -n get default` on macOS), then `127.0.0.1` as the laptop fallback. Detection is only ever used for the URLs it *prints* — never for wiring services together.

Override it with `--host-ip <addr>` when the address you reach the machine on is not the address on its interface — a cloud VM behind a NAT gateway is the usual case.

> **`--host-ip` and `--bind 0.0.0.0` trigger a Factory rebuild.** `NEXT_PUBLIC_SITE_URL` is inlined by `next build` and arrives as a Docker build arg, so the storefront's own base URL cannot be changed at runtime. Changing it rebuilds the largest image in the stack — budget 10+ minutes. Leave both alone and the default `http://127.0.0.1:9080` is baked once and never rebuilt.

### Production domains are overridden

Several compose files default to our production hostnames. Left alone, a user's laptop would be talking to *our* servers — wrong, and a privacy problem. The overlay overrides every one:

| File | Overridden |
|---|---|
| `docker-compose.yml` | `PROMETHEUS_EXTERNAL_URL`, `GRAFANA_ROOT_URL`, `GRAFANA_DOMAIN` (all default to `magic-ai-factory.com`) |
| `docker-compose.core.yml` | `ALIEN_ORACLE_PORTAL`, `ALIEN_ORACLE_PLATON_URL`, `ALIEN_ORACLE_FAMILY_URL`, `ALIEN_METIS_URL`, `ALIEN_SKOPOS_URL`, `ALIEN_HELIOS_URL`, `ALIEN_DIOSCURI_URL` (7) |
| `alien-monitor/docker-compose.prod.yml` | 13 more `ALIEN_*_URL` / `ALIEN_PUBLIC_*_URL` (Factory, Chronos, Platon cave, Metis, SKOPOS, ATLAS, MOMUS, Treasury) |
| `momus/docker-compose.yml` | `MOMUS_PUBLIC_URL`, `MOMUS_CORS_ORIGINS` (`momus.modelmarket.dev`) |
| `gaia/docker-compose.yml` | `GAIA_PUBLIC_URL`, `GAIA_CORS_ORIGINS` (`iot.modelmarket.dev`) |
| `atlas/docker-compose*.yml` | `ATLAS_PUBLIC_URL`, `ATLAS_CORS_ORIGINS`, **`ATLAS_GAIA_URL`** |
| `oracles/docker-compose.yml` | `CHRONOS_PUBLIC_URL`, `ORACLE_FAMILY_PUBLIC_URL` |
| `platon/docker-compose.yml` | `PLATON_PUBLIC_URL` |
| `argus/docker-compose.yml` + `.env.example` | `ALIEN_MONITOR_URL`, `ARGUS_HUB_URL`, `ARGUS_MESH_URL`, `ARGUS_ORACLE_FAMILY_URL` |
| `momus/docker-compose.yml` | `AIMARKET_VERIFY_METIS_URL` — defaults to `http://metis:9100`, which is wrong twice over: there is no service named `metis` (it is `metis-coordinator`, which also carries the network alias `coordinator` that Metis's own cluster config hard-codes) and it listens on 8080, not 9100. Left alone, high/critical bounty verification never resolves and the Treasury holds intents forever with no visible error. |

#### The `env_file` path, closed

The table above covers what the compose *files* declare. It missed a route that no reading of those files reveals: `app` and `grafana` take `env_file: .env`, and compose hands such a service **every** key in the operator's `.env` — including values left from a production deploy, or copied out of `.env.vps.example`. On an operator box that meant `ALIEN_PUBLIC_ARGUS_URL` and `ARGUS_PUBLIC_URL` arriving in both containers pointing at `magic-ai-factory.com/arena`, while both compose files looked clean.

An earlier version of this document called those two "inert passengers" — nothing reads them, so nothing acts on them. That argument is not good enough, for two reasons. It depends on today's code: the moment some service starts reading a variable that is already in its environment, the leak becomes live with no change that review would flag. And it cannot be checked — "is this variable read anywhere?" is a judgement call, whereas "does our hostname appear in the resolved config?" is a fact. So they are now pinned in `environment:` for both services, alongside `NEXT_PUBLIC_SITE_URL` and `AIFACTORY_PUBLIC_URL` (which `.env.vps.example` really does set to our domain).

Two layers hold the line, because pinning alone only covers the variables somebody thought of:

- **Pinned**, so the resolved config is clean whatever your `.env` says. `tests/test_everything_self_contained.py` asserts it, deriving the risk set from `.env.vps.example` — add a production variable to that template and the test immediately demands a pin.
- **Refused at launch.** `scripts/everything.sh` resolves the merged config before starting anything and stops if any of our hosts survive, naming the variable. That is the layer that catches the next one. `ECO_ALLOW_PROD_HOSTS=1` overrides it, for an operator who genuinely means to federate with our production.

Check it yourself before exposing anything:

```bash
docker compose -f docker-compose.yml -f docker-compose.everything.yml --profile everything config | grep -E "modelmarket\.dev|magic-ai-factory\.com"
```

Empty output is the expected result, and the launcher enforces it. Anything printed is a bug — report it.

**The worst one is `ATLAS_GAIA_URL`.** It defaults to `https://iot.modelmarket.dev` in *both* ATLAS compose files — including the one titled "Local / CI compose" — and with `ATLAS_POLL_INTERVAL_S=30` and `ATLAS_GAIA_CONCURRENCY=4`, an untouched local ATLAS polls our production GAIA four-wide, twice a minute, forever, from every user's machine. It is repointed at `http://gaia-backend:9320`.

### Binding: localhost vs 0.0.0.0

**The default is `127.0.0.1`.** The stack is reachable from the machine itself, which is what an evaluation needs. Nothing binds a privileged port (<1024) — production uses 80/443 through the nginx edge; here nothing needs root.

`--bind 0.0.0.0` puts all 32 ports on every interface. It must be passed deliberately; it is never inferred from `--host-ip` or anything else. It prints a loud warning first, because what it exposes includes:

| Port | Control plane exposed | Guarded by |
|---|---|---|
| 9410 | MOMUS operator routes — scan, self-audit, remediate, A2A task submission | `MOMUS_OPERATOR_TOKEN` |
| 9411 | Treasury — the service that authorises payouts | operator token |
| 9402 | SKOPOS remediation conductor — dispatches fixes to node agents | operator token |
| 8501 | SKOPOS dashboard — fleet observability, Security Center, AI analyst | `SKOPOS_DASHBOARD_PASSWORD` |
| 9080 | Factory admin (`/admin/login`) — full product pipeline control | `AIFACTORY_DEV_BOOTSTRAP_PASSWORD` |
| 9100 | Monitor authenticated writes (ARGUS run panel) | `ALIEN_API_TOKEN` |
| 8090 | Mesh admin API | `MESH_ADMIN_TOKEN` |
| 9082 / 9090 | Grafana / Prometheus | Grafana password; Prometheus **unauthenticated** |
| 9111 | Metis coordinator | `METIS_API_KEY` |

**The generated tokens in `.env` are the only thing in front of all of it.** There is no TLS, so those tokens cross the network in clear text. On Linux, remember that a Docker publish inserts a DNAT rule *ahead* of UFW — a host firewall does not save you here. Use `--bind 0.0.0.0` on a trusted network or behind your own firewall, and not otherwise.

One more consequence: on `http://<lan-ip>` (as opposed to `http://127.0.0.1`) browsers withhold secure-context features, so service workers and `crypto.subtle` are unavailable. The Factory PWA and anything doing in-browser crypto degrade when you browse from a second machine.

---

## Three hosts, one box

Production runs this ecosystem across **three servers** — an oracle host, a factory host and a skopos host — each behind an nginx TLS edge, with services addressing each other by domain (`momus.modelmarket.dev`, `metis.modelmarket.dev`, …). This tier collapses all three onto one machine. That is where the port collisions come from, and it changes some behaviour:

| Production | Here |
|---|---|
| nginx TLS edge on 80/443, path routing (`/monitor/`, `/pulse/`, `/arena/`, `/argus/`) | No edge. Direct `http://<ip>:<port>` per service. |
| Services call each other by public domain over TLS | Services call each other by compose service name over the bridge |
| Real certificates, HSTS, secure-context browser features | Plain HTTP; secure-context features unavailable off `127.0.0.1` |
| MOMUS control routes 404 at the edge for non-operators | Ports are simply not published beyond `127.0.0.1` unless you say otherwise |
| Three separate Docker daemons, three disks, three sets of logs | One daemon, one disk — which is why the resource floors are what they are |
| Signing keys survive redeploy on host volumes | Same, via named volumes — see [Identity keys](#identity-keys-do-not-rotate-these-casually) |

### Unavailable in IP mode

These are not half-shipped. They are off, and here is what each costs:

- **HELIOS YouTube upload.** Google OAuth requires a registered `https` redirect URI; the consent flow cannot complete against `http://<ip>:8791`. *Cost:* rendering works, publishing does not. Runs with `HELIOS_DRY_RUN=1`.
- **Discord interaction endpoints / Telegram webhook mode.** Both need a public `https` receiver. *Cost:* DIOSCURI is limited to outbound long-polling — which works behind NAT and is the supported path here. Note only one container may long-poll a given bot token.
- **Inbound hub federation.** `AIMARKET_HUB_URL` becomes `http://<host-ip>:9083` and no remote peer can crawl a NAT'd machine. Seeds are already empty (`AIMARKET_SKIP_SEED=1`), so the local hub is self-contained. *Cost:* no inbound peers — correct for an evaluation.
- **Factory AI-market webhooks** (`AIFACTORY_AI_MARKET_WEBHOOK_1/2`). Need a reachable `https` receiver. Empty by default; leave them empty.
- **Real on-chain settlement and any chain callback.** Out of scope by design. MOMUS bounties stay as UNI/HELD intents.

---

## Port remaps

The rule: **when production already moved a service off a contested port, production's value wins.** We only invent a number where production has no precedent, and then we say so.

### Collisions resolved with production's own precedent

| Port | Contenders | Winner | Loser moves to |
|---|---|---|---|
| 8090 | `mesh-api` ↔ `lottery-relayer` | `mesh-api` | **8390** — already the value in `lottery/docker-compose.override.yml` |
| 9083 | `hub` ↔ mesh's embedded hub | `docker-compose.core.yml#hub` | the other two definitions stay down (see below) |
| 9400 | `oracle-family` ↔ `momus-backend` | `oracle-family` | **9410** — already MOMUS's production port |
| 9401 | `treasury` ↔ momus range | — | **9411** — already Treasury's production port |
| 5199 | `pulse-terminal` ↔ `logos` | `pulse-terminal` | **9460** — already `LOGOS_PORT`, which the old `5199:5199` mapping did not even reach |

### Remaps that differ from production

Two, both caused by a collision that only exists on one box:

| Service | Production | Here | Why |
|---|---|---|---|
| `platon-frontend` | 8080 | **9201** | `platon/docker-compose.yml` publishes `127.0.0.1:8080:80` and `metis/docker-compose.yml#coordinator` publishes `8080:8080`. On separate hosts they never met. 9201 sits next to its own backend on 9200 — self-documenting — and gets the stack off 8080, the most contended port on any developer machine. |
| `metis-coordinator` | 8080 (behind `metis-nginx`) | **9111** | The `+10` precedent would give 8090, which is `mesh-api`, so the precedent breaks. 9111 is free and sits in the 91xx control band next to the Monitor on 9100. |

### One hub, one mesh

Three compose files build the same hub and all bind 9083 (`docker-compose.core.yml#hub`, `aimarket-hub/docker-compose.yml#hub`, `ai-service-mesh/docker-compose.yml#aimarket-hub`); two build the same mesh-api on 8090. Beyond the port clash, three hubs means three signing keys, three databases and federation identity churn. The tier starts **exactly one of each** — the `docker-compose.core.yml` definitions — and prints which.

---

## Credentials

### Where they live

| Location | What |
|---|---|
| `.env` (repo root) | Every generated token and password. `chmod 600`, gitignored. |
| `data/secrets/` | Keys minted by the container entrypoint — `jwt_secret.key`, `bootstrap_admin.txt`, `sandbox_demo_password`. |
| Named Docker volumes | Ed25519 identity keys, minted on first boot. Never in `.env`. |
| `<satellite>/.env` | Seeded from each `.env.example` on first run. Also gitignored (the root `.gitignore` `.env` pattern has no slash, so it matches at any depth). |
| `platon/platon.env` | Platon's deliberately *scoped* env file — it gets a provider key and nothing else, so a Platon compromise cannot reach the rest of the ecosystem's secrets. Pointed at by `PLATON_ENV_FILE`. |

They print **once**, in one block, at the end of the first run. On every later run the launcher prints the path, not the values. No secret is written to a log line, a health message or an error string.

### Generated for you

You do not supply any of these. Several are fail-closed — compose refuses to start the whole project without them, which is exactly why the launcher mints them first.

| Secret | Guards | Fail-closed? |
|---|---|---|
| `GRAFANA_ADMIN_PASSWORD` | Grafana login | **yes** |
| `MESH_API_TOKEN`, `MESH_ADMIN_TOKEN` | Mesh API and admin routes | **yes** |
| `SKOPOS_DASHBOARD_PASSWORD` | SKOPOS dashboard (min 12 chars, auth required by default) | effectively |
| `SKOPOS_POSTGRES_PASSWORD`, `SKOPOS_DATABASE_URL` | SKOPOS's database. The compose default is the literal string `skopos` — regenerated, not inherited. | yes in one variant |
| `SKOPOS_AGENT_TOKEN_SECRET` | Floating-agent HMAC across processes | no |
| `SKOPOS_NODE_SECRET_KEY` | SKOPOS node identity | no |
| `MOMUS_OPERATOR_TOKEN` | **The entire MOMUS control plane.** Defaults to empty in the compose file. | no — mint it |
| `GAIA_SIM_TOKEN` | GAIA `/sim/*` routes (defence in depth even with `GAIA_SIM_CONTROL=0`) | no |
| `METIS_API_KEY`, `METIS_NODE_A_KEY`, `METIS_NODE_B_KEY` | Metis API and both nodes. Shipped as `change-me-*`. | no |
| `ALIEN_API_TOKEN` | Monitor authenticated writes (ARGUS run panel) | no |
| `ARGUS_HTTP_TOKEN` | ARGUS HTTP surface | no |
| `AIFACTORY_DEV_BOOTSTRAP_PASSWORD` | Factory admin login | no |
| `JWT_SECRET_KEY` | Factory sessions. Minted by the entrypoint into `data/secrets/jwt_secret.key`; deliberately has no compose default. | no |
| `AIFACTORY_SANDBOX_DEMO_PASSWORD` | Sandbox preview auth | no |

> **`ALIEN_API_TOKEN` has a trap.** It must arrive via `env_file` **only**. Setting `${ALIEN_API_TOKEN:-}` in an `environment:` block overrides the `env_file` value with an empty string and silently breaks Monitor auth. Both Monitor compose files carry this warning; the overlay respects it.

Every lottery key — `OPERATOR_KEY`, `SPONSOR_KEY`, `BENEFACTOR_KEY`, `AGENT_KEYS`, `TREASURY_KEY`, `ORACLE_SIGNER_KEY` — is a well-known `test test … junk` mnemonic account hardcoded in `lottery/docker-compose.yml`. Fake money on an ephemeral local chain. That is correct as it stands, and the launcher will never swap in a real one.

### You supply

Exactly one thing is genuinely worth supplying:

| Key | Effect if missing |
|---|---|
| **`DEEPSEEK_API_KEY`** (the ecosystem default — MOMUS, Treasury, ATLAS, DIOSCURI, HELIOS, SKOPOS, Platon and the Factory gate model all default to `deepseek/deepseek-v4-pro`). `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GROQ_API_KEY` / `TOGETHER_API_KEY` / `OPENROUTER_API_KEY` are accepted alternatives per service. | The stack still boots. The Factory falls back to synthetic templated output and every AI panel degrades. Not fail-closed anywhere. |

Everything else is optional, and the service either sleeps or runs in dry-run without it:

| Key | For | Without it |
|---|---|---|
| `TELEGRAM_BOT_TOKEN`, `DISCORD_BOT_TOKEN` + `DISCORD_GUILD_ID` | DIOSCURI twins | That twin sleeps. `DIOSCURI_DRY_RUN=1` needs neither and is the recommended first smoke test. |
| `ARGUS_TELEGRAM_TOKEN`, `ARGUS_TELEGRAM_OWNER_ID` | ARGUS notifications | ARGUS runs autonomously. |
| `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_TOKEN` | HELIOS publishing | Unavailable in IP mode regardless — see above. |
| `GITHUB_TOKEN` | DIOSCURI knowledge/release features | Those features are off. |
| `GAIA_OPENAQ_API_KEY` | The `openaq-01` sensor | One sensor fewer. |
| `MAXMIND_LICENSE_KEY`, `MAXMIND_ACCOUNT_ID` | SKOPOS geoip | `SKOPOS_GEOIP_API_FALLBACK` covers it. |
| `ARGUS_WALLET_KEY`, `ARGUS_KEYSTORE_PASSPHRASE` | Crypto mode only | Not needed — crypto stays off. |

### Rotating a secret

1. `./start.sh --everything --down`
2. Delete the line from `.env` (or from the relevant `<satellite>/.env`).
3. `./start.sh --everything` — anything missing is regenerated, and the new value prints in the credentials block.

The Factory admin password is the exception: bootstrap only runs when *no* admin exists, so changing `AIFACTORY_DEV_BOOTSTRAP_PASSWORD` on an existing install does nothing. Change it in the admin UI. See [running.md](running.md#admin-login--first-password).

### Identity keys: do not rotate these casually

Ed25519 signing keys are minted on first boot into named volumes — `hub_signing_key`, `momus-scanner-keys`, `momus-treasury-keys` (a **separate** volume the scanner never mounts; preserve that separation), `gaia-keys`, `oracle_family_data`, `platon_signing_key`.

They must stay on their volumes. The oracles compose carries a first-hand warning about this: run `compose up --build` without the volume and it mints a *new* key, after which every hub that pinned the old one answers `public key changed! Rejecting (possible takeover)` and drops all 22 capabilities. `--down` and `--reset-chain` both preserve these volumes. Only `docker compose -p aicom down -v` destroys them, and that is a full identity reset.

---

## What is deliberately not deployed

A missing service that nobody mentions reads as a broken deploy. These are all absent on purpose, or absent because they cannot be built.

### Excluded by design

| Not deployed | Why | Where it lives instead |
|---|---|---|
| **Smart contracts on any real chain** | Contract deployment is deliberately a separate concern and already has its own tooling. This launcher must never touch a real chain. | `contracts/evm/script/*.s.sol` (`Deploy.s.sol`, `DeployBountySplitter.s.sol`, `DeployFakeUSDT.s.sol`, `DeployNFT.s.sol`) and `scripts/redeploy_uni_contracts.sh`. The local UNI chain that ships inside the lottery and Monitor stacks *is* deployed — it is ephemeral and funded with fake tokens. |
| **gitea, act_runner, dind (infra)** | Our build and mirror infrastructure, not part of the product. Someone evaluating the ecosystem has no use for our git server. | The three production hosts. |
| **metis-apache-test** | A test fixture. | — |
| **nginx / traefik / caddy, and any certificate** | Explicitly out of scope: this tier is IP:PORT. | Production's TLS edge; see [deploy-ecosystem.md](deploy-ecosystem.md). |

### Cannot be built from this repository

| Prod service | What is missing |
|---|---|
| **`ecosystem-monitor-frontend` :5175** (oracle host) | Nothing in the tree matches. Grepping for `monitor-frontend` and for `5175` returns zero hits outside a GeoJSON coincidence. The container name implies a compose project `ecosystem` with a service `monitor-frontend`, and that compose file is not in this repository. The Alien Monitor's own frontend is baked into the `alien-monitor` image, so :5175 is a *separate* standalone SPA we cannot reproduce. **Nothing is lost from the Monitor** — you get the Monitor at :9100. |
| **`azimuth`** — the whole application (web :5173, api :8080, worker, redis, postgres) on the skopos host | There is no `azimuth/` folder, no Dockerfile, no compose anywhere in the tree. Five production containers with no local path. This is the largest honest gap in the tier. |
| **`metis-nginx`** | No buildable service — `metis/docker-compose.prod.yml` has the sidecar commented out and the real config (`metis/deploy/nginx.conf`) is applied to a *host* nginx. Excluded by the no-edge rule anyway; the practical effect is that Metis has no TLS front and the coordinator's raw port (9111) is the only way in. |
| **The literal production SKOPOS compose** (`metis/deploy/skopos-test/docker-compose.yml`) | Its `build.context` is `${SKOPOS_APP_DIR:-/opt/skopos-test/app}` — an absolute host path that does not exist on a clean machine. SKOPOS itself *is* deployed, built from the in-repo `skopos/docker-compose.yml`, which builds the same application. |

### Deployed, but knowingly different from production

- **`argus-uni`** — production points it at `http://host.docker.internal:8545`, which resolves to nothing on a single-box bridge. Repointed at `http://chain:8545` (the lottery's Anvil), so it depends on the lottery layer being up.
- **`mesh-dashboard`** — its own nginx config proxies `/v1/` to `127.0.0.1:8090` *inside its own container*, and the static variant proxies nothing at all; the frontend Dockerfile declares no `ARG VITE_MESH_API_URL`, so the base URL cannot be baked either. The overlay mounts a config pointing at `http://mesh-api:8090`. Without it the dashboard loads and shows nothing.
- **`momus-canary` and `skopos-remediation`** — neither has a compose service anywhere in the repository; both are `docker build`/`docker run` only in production. The overlay defines them. Dropping the canary is tempting and wrong: it is the only target that makes MOMUS demonstrably fire against a real contract violation.
- **`alien-monitor` and `pulse-terminal`** — production runs both with `network_mode: host`. That ignores the `--bind` decision entirely and behaves differently on Docker Desktop, so both run on the bridge with published ports instead. The core overlay's Monitor variant states it cuts zero Monitor features.
- **`ALIEN_UNIVERSE_ENABLE_SOLANA=0`**, as in production. The Solana toolchain install in the Dockerfile is `|| echo`-guarded, so a build behind a proxy silently produces an image with no toolchain and the flag then fails at *runtime* instead of at build. Leaving it off also saves ~1.5 GB of RAM and ~1.2 GB of image.

---

## Troubleshooting

The four failures a first run actually hits, in the order you are likely to meet them.

### 1. `docker compose up` aborts before anything builds

**Symptom:** an error about a missing `.env` file or a missing build context, with nothing built and no containers created.

**Cause:** five of the compose files this tier uses declare `env_file: .env` with no `required: false` — `argus/`, `dioscuri/`, `helios/`, `skopos/` and `aicom-landing/`. On a clean checkout **`dioscuri/.env` and `helios/.env` do not exist**, so compose aborts before building anything. (A sixth, `metis/deploy/skopos-test/`, has the same problem but is not used here — see [what cannot be built](#cannot-be-built-from-this-repository).)

Separately, `platon/docker-compose.yml` takes its environment from a *scoped* file — `env_file: ${PLATON_ENV_FILE:-/root/.hermes/platon.env}` — deliberately, so a Platon compromise cannot exfiltrate the rest of the ecosystem's secrets. That default is an absolute path on our oracle host, so on any other machine compose aborts. Platon does not read a `.env` at all; its template is `platon/platon.env.example`.

**Fix:** the launcher seeds all five from their `.env.example`, seeds a repo-local scoped Platon file, and exports `PLATON_ENV_FILE` before it calls `up`. If you are driving compose by hand:

```bash
for d in argus dioscuri helios skopos aicom-landing; do
  [ -f "$d/.env" ] || cp "$d/.env.example" "$d/.env"
done
[ -f platon/platon.env ] || cp platon/platon.env.example platon/platon.env
export PLATON_ENV_FILE="$PWD/platon/platon.env"
```

### 2. A service starts, then dies with a parse error

**Symptom:** `dioscuri` or `helios` restarts in a loop, complaining that its config is not valid JSON/YAML.

**Cause:** `dioscuri/dioscuri.config.json`, `helios/helios.config.yaml`, `helios/data/` and `skopos/ssh/` are bind-mount sources that do not exist in a clean tree. **Docker does not fail on a missing bind source — it creates an empty *directory* where a file was expected**, and the application then tries to parse a directory.

**Fix:** seed all four from their examples before `up`. This is worse than a hard failure precisely because it looks like an application bug.

### 3. Everything is green in `docker ps` and nothing works

**Symptom:** all containers healthy, but the Monitor's satellite panels are empty, ATLAS has no sensors, MOMUS never resolves a verification, and every service claims its neighbour is unreachable.

**Cause:** the network-name disagreement. Six different network names across the compose files for what has to be one bridge. Unreconciled, every cross-service call falls into its "degrades gracefully" path *at once* — and every one of those paths is silent by design. This is the single highest-probability first-run failure and it is invisible in `docker ps`.

**Fix:** run the tier as **one compose project** so everything lands on `aicom_net` (that is what `./start.sh --everything` does). To confirm:

```bash
docker network inspect aicom_net --format '{{len .Containers}} containers attached'
docker compose -p aicom exec alien-monitor curl -fsS http://hub:9083/.well-known/ai-market.json
```

If a container resolves `hub` but not `gaia-backend`, it is on the wrong network.

### 4. The Monitor never goes healthy

**Symptom:** `alien-monitor` sits `unhealthy` for minutes, and the launcher reports it as the one service that did not come up.

**Cause:** its healthcheck requires `blockchain_ready`, and it deploys Anvil + FakeUSDT + Escrow + NFT inside the container first. **2–4 minutes cold is normal** on the first run. Permanently red means the `forge`/Anvil step degraded — usually a build that could not reach `ghcr.io/foundry-rs/foundry` or GitHub for `forge install`.

**Fix:** wait out the first four minutes. If it stays red, check `docker compose -p aicom logs alien-monitor` for the Anvil deployment, and rebuild with network access to ghcr.io and GitHub. Nothing else in the stack gates on the Monitor being *healthy* — every consumer polls it and idles — so the rest of the tier is usable meanwhile.

### Also worth knowing

- **Metis nodes report unhealthy while working.** Their healthchecks `curl` with `Authorization: Bearer $METIS_NODE_A_KEY`, so wrong or default `change-me-*` values make a perfectly good node look broken. The coordinator waits on `service_started`, not `service_healthy`, so this is cosmetic — but confusing.
- **Every image is built; none is pullable.** There is no registry fallback for any of the ~30 first-party services. Only `alpine`, `postgres:16-alpine`, `prom/prometheus`, `grafana/grafana`, `nginx:alpine`, `node:20-alpine` and the Foundry base are pulled. A machine that cannot build cannot run this at all.
- **Builds need specific network access.** The Factory image needs `deb.nodesource.com` (apt repo + GPG key), npm, PyPI and `playwright install chromium`. alien-monitor needs ghcr.io, `release.anza.xyz` and GitHub. A corporate proxy breaks the two most important images.

---

## Teardown and reclaiming disk

```bash
./start.sh --everything --down          # stop; keeps ./data and every named volume
./start.sh --everything --reset-chain   # stop, then wipe the two chain state sinks
```

`--reset-chain` deletes `data/alien-monitor/universe/anvil-state` and the lottery `shared` volume. That is the honest fix for the growth problem described in [What it costs](#what-it-costs) — `--down` deliberately preserves both, so a stop-and-start does not silently reset your universe.

Reclaiming the rest, roughly in order of how much you get back for how much you lose:

```bash
docker builder prune                    # 8-15 GB of build cache; costs a slower next build
docker compose -p aicom down --rmi local # the ~12 GB of images; costs a full rebuild
docker compose -p aicom down -v         # named volumes — DESTROYS every signing key (see above)
rm -rf data/                            # products, sandboxes, SQLite, Prometheus TSDB, Grafana
```

A full uninstall is `docker compose -p aicom down -v --rmi local` followed by `docker builder prune -a` and `rm -rf data/`. Read [Identity keys](#identity-keys-do-not-rotate-these-casually) before you use `-v`.

To stop the logs growing in the first place, give the daemon a default in `/etc/docker/daemon.json`:

```json
{ "log-driver": "json-file", "log-opts": { "max-size": "50m", "max-file": "3" } }
```

---

## See also

- [running.md](running.md) — the umbrella: every way to run this monorepo, and how the tiers relate.
- [deploy-ecosystem.md](deploy-ecosystem.md) — the real multi-host production redeploy, with the fixed script order and the Hub-redeploy hazard.
- [quickstart-ecosystem-deploy.md](quickstart-ecosystem-deploy.md) — tiered greenfield quick-start for a bare Ubuntu VPS.
- [crypto-switch.md](crypto-switch.md) — what `AIFACTORY_CRYPTO_ENABLED` actually gates, and why off is the default.
- [ecosystem-architecture.md](ecosystem-architecture.md) — what all these services are to each other.
