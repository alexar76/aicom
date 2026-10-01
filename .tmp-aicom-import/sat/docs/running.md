# Running AI-Factory

Every way to run this monorepo, what each one brings up, and what gets deployed. Start with the decision table, then jump to the section for your path.

---

## TL;DR — which command?

| I want to… | Run this | What you get |
|---|---|---|
| Just tinker / see it work locally | [`./start.sh`](../start.sh) | Core stack: Factory + Hub + Mesh + Alien Monitor. One LLM key, crypto OFF, browser opens. |
| Reuse already-built images (faster) | `./start.sh --no-build` | Same core stack, skips the image build. |
| Tail core logs | `./start.sh --logs` | Follows all core services (`logs -f --tail=120`). |
| Stop core, keep my data | `./start.sh --down` | Stops core; `./data` + named volumes preserved. |
| Run the **whole ecosystem** (15-satellite fleet) | `./start.sh --full` | Delegates to [`scripts/quickstart_ecosystem.sh`](../scripts/quickstart_ecosystem.sh) → [`scripts/deploy_ecosystem.sh`](../scripts/deploy_ecosystem.sh). |
| Reproduce **all of production on one box** | `./start.sh --everything` | Everything tier: 38 containers, 32 ports, no nginx/TLS/domains — `http://<ip>:<port>`. Wants 32 GB RAM + 100 GB disk. See [deploy-everything.md](deploy-everything.md). |
| Deploy the fleet **publicly with TLS** | `./start.sh --full --public-url https://…` | Fleet + nginx/certbot routing (needs nginx on host). |
| One-click cloud, zero local setup | Dev Container / GitHub Codespaces | [`.devcontainer`](../.devcontainer/devcontainer.json) builds the box; you supply the LLM key as a Codespaces secret, then run `./start.sh --no-open`. |
| A single container, no Hub/Mesh/Monitor | `docker compose up -d --build` | Just `app` + `prometheus` + `grafana` from the base [`docker-compose.yml`](../docker-compose.yml). |
| Full monitoring + DinD/host-docker toggle | [`./run-compose.sh`](../run-compose.sh) | Base + DinD (or host-docker) + secrets overlay + Grafana/Prometheus. |
| One plain `docker run` container (legacy) | [`./run.sh`](../run.sh) | Factory app only, on ports `8080/8081`, data in `~/aicom-data`. |
| Submit a product idea to a running stack | [`./demo.sh`](../demo.sh) / [`./batch-demo.sh`](../batch-demo.sh) | Enqueues one / five ideas via the API. |
| Production / soak-test deployment | `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build` | Postgres + Redis + split services + prod guards. |

**New here?** Use `./start.sh`. Everything else on this page is a variation of, or an ancestor of, that one door.

---

## Core stack (`./start.sh`)

`./start.sh` is the front door. It always drives **two** compose files, layered:

```bash
docker compose -f docker-compose.yml -f docker-compose.core.yml <up|logs|down>
```

- [`docker-compose.yml`](../docker-compose.yml) (base) owns `data-init`, `data-keep`, `app`, `prometheus`, `grafana`, and the `aicom_net` bridge network.
- [`docker-compose.core.yml`](../docker-compose.core.yml) (overlay) **only adds** `hub`, `mesh-api`, `alien-monitor` (plus named volumes `hub_data`, `mesh_data`). Its header: *"It ONLY adds services; it never edits the root."*

Every action (`up` / `logs` / `down`) runs against **both** files.

### What `./start.sh` does on a default run

1. **Resolve root & `cd`**, `set -euo pipefail`.
2. **Preflight** — hard-fails unless all three pass: `docker` present, `docker compose version` (Compose v2), `docker info` (daemon reachable). Prints `✓ docker + compose v2`.
3. **`.env` bootstrap** — if no `.env`, copies [`.env.demo`](../.env.demo) → `.env` (or creates an empty `.env` if `.env.demo` is missing too).
4. **Secrets** — auto-generates any missing secret into `.env`, then `chmod 600 .env` (see below).
5. **LLM-key check** — warns if none found (see below).
6. **Data dirs** — `mkdir -p data/config data/alien-monitor/universe data/secrets`; seeds `data/config/model_providers.yaml` from the example if absent.
7. **Remote satellites** — prints which of *our* public endpoints the map will read, and how to opt out (see below).
8. **Up** — `up -d --build` (default). With `--no-build`, `up -d` reusing existing images.
9. **Health wait** — polls Factory API, Hub, Monitor (see below).
10. **Report** — prints the URL/credential block.
11. **Open browser** — opens `http://localhost:9080/admin/login` (skipped with `--no-open`).

### Flags

| Flag | What it does |
|---|---|
| *(none)* | Preflight → bootstrap → secrets → LLM check → data dirs → remote-satellite notice → `up -d --build` → health wait → print report → open browser. |
| `--no-build` | `up -d` **without** `--build`; reuses existing images ("Starting core stack (reusing existing images)"). All other steps still run. |
| `--no-open` | Skips step 11 (no browser launched). Build still happens. |
| `--logs` | `exec … logs -f --tail=120` — follows all core logs. Replaces the process before preflight/up run. |
| `--down` | `… down` (no `-v`): stops core, **keeps** `./data` bind mount and `hub_data`/`mesh_data` volumes. Prints restart hint, exits. |
| `--full [...]` | `shift` + `exec scripts/quickstart_ecosystem.sh "$@"` — hands off to the full fleet; **none** of the core logic runs. Remaining args (`--public-url …`, `--skip-verify`) pass straight through. |
| `--everything` | Switches to the **everything tier** — dispatches to [`scripts/everything.sh`](../scripts/everything.sh) (38 containers, all three production hosts on one box). Order-independent: `--everything --down` and `--down --everything` both work. Enables `--bind` / `--host-ip` / `--reset-chain` / `--yes` / `--skip-resource-check`, which apply to this tier only. |
| `-h` / `--help` | Prints the banner/usage block, exits. |
| *(unknown)* | `die "Unknown option: … (see ./start.sh --help)"`. |

### What gets deployed

`depends_on`: `data-init` runs to completion first; `app` waits for it. `hub` has **no** dependency and starts immediately. `prometheus`/`grafana` wait for `app` **healthy**; `mesh-api` waits for `hub` started; `alien-monitor` waits for `app` **healthy** + `hub` started.

| Service | Port (host→container) | Role | In image? |
|---|---|---|---|
| **data-init** | none (`network_mode: none`) | Sidecar: `install -d`/`chown` bind-mount dirs to the app UID (prometheus 65534, grafana 472), then exits (`restart: "no"`). | `alpine:3.19` |
| **data-keep** | none (`network_mode: none`) | Re-chowns `/data/code` to uid 10001 every 30s (host rsync as 501/root). `app` cannot `CAP_CHOWN`. | `alpine:3.19` |
| **app** | `9080→8080`, `9081→8081` | Batteries-included single container: FastAPI API (8081) + pipeline worker + Next.js storefront/admin (8080). Runs `10001:10001`, `cap_drop: ALL`, `no-new-privileges`, 2 CPU / 4g. | Built from [`Dockerfile`](../Dockerfile) → `ai-factory:${AICOM_IMAGE_TAG:-local}` |
| **prometheus** | `9090→9090` | Metrics TSDB, served under `/prometheus/`, read-only rootfs, TSDB in `./data/prometheus`. | `prom/prometheus:v3.11.3` |
| **grafana** | `9082→3000` | Dashboards; state in `./data/grafana` (provisioning disabled, UI-only datasource). | `grafana/grafana:13.0.1` |
| **hub** | `9083→9083` (`AIMARKET_HUB_HOST_PORT`) | AIMarket Federation Hub — where shipped products list/federate. Fully local (`AIMARKET_SEED_LIST=""`, `AIMARKET_SKIP_SEED="1"`). | Built from [`aimarket-hub/Dockerfile`](https://github.com/alexar76/aimarket-hub/blob/main/Dockerfile) |
| **mesh-api** | `8090→8090` (`MESH_HOST_PORT`) | Service Mesh API — topology/registry the Monitor's mesh contour reads (`MESH_ENV: production`). | Built from [`ai-service-mesh/backend`](https://github.com/alexar76/ai-service-mesh/tree/main/backend/) |
| **alien-monitor** | `9100→9100` | The showpiece: live universe (local Anvil + FakeUSDT sim), reputation graph, contour switching, ARGUS run panel. `ALIEN_MODE: universe`, Solana off. | Built from [`alien-monitor/Dockerfile`](https://github.com/alexar76/alien-monitor/blob/main/Dockerfile) |

> **All six long-lived core services publish host ports:** `app` (9080/9081), `hub` (9083), `mesh-api` (8090), `alien-monitor` (9100), `prometheus` (9090), `grafana` (9082). `hub` and `mesh-api` are published via `${AIMARKET_HUB_HOST_PORT:-9083}` / `${MESH_HOST_PORT:-8090}`, **and** are additionally reachable inside the stack by service name (`http://hub:9083`, `http://mesh-api:8090`) — which is how the Monitor talks to them over the `aicom_net` bridge. So `start.sh`'s `localhost:9083` health-wait succeeds normally.

### The one-LLM-key requirement

You supply **one** LLM key — everything else is generated for you. `start.sh` scans `.env` for a non-empty value of any of `DEEPSEEK_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `TOGETHER_API_KEY`, `GROQ_API_KEY`, and also treats any file matching `data/secrets/llm/*_api_key` as a key.

- **With a key:** `✓ LLM key detected — real AI agents enabled`.
- **Without a key:** the stack still boots and the Monitor works, but the AI pipeline uses the **synthetic fallback (templated output)** instead of real agents. Add e.g. `DEEPSEEK_API_KEY=sk-...` to `.env`.

The key is never generated — it is the one thing you provide. [`.env.demo`](../.env.demo) ships all example key lines commented out.

### Auto-generated secrets

On first run `start.sh` fills any missing secret (idempotent — existing non-empty values are kept; empty `KEY=` lines are stripped and regenerated), then `chmod 600 .env`:

| Env key | Bytes → hex chars |
|---|---|
| `GRAFANA_ADMIN_PASSWORD` | 18 → 36 |
| `MESH_API_TOKEN` | 24 → 48 |
| `MESH_ADMIN_TOKEN` | 24 → 48 |
| `ALIEN_API_TOKEN` | 24 → 48 |
| `AIFACTORY_DEV_BOOTSTRAP_PASSWORD` | 12 → 24 |

These satisfy the overlay's required-var guards (`MESH_API_TOKEN`/`MESH_ADMIN_TOKEN`/`GRAFANA_ADMIN_PASSWORD` all use `${VAR:?…}`) — running compose raw without them fails fast, which is why the wrapper generates them.

### Safe by default (crypto OFF)

The core stack never touches money. `AIFACTORY_CRYPTO_ENABLED` is unset → local Anvil sim + fake USDT, no wallet, no chain, no real funds. See [Safe by default](#safe-by-default) below.

### Remote satellites — the core tier calls out, and says so

The core tier starts four services. The ecosystem map has more nodes than that, and the ones it does not run are read from **our public read-only endpoints** so the map is not two-thirds dead: `oracles.modelmarket.dev` (portal, Platon, oracle family), `metis.modelmarket.dev`, `skopos.modelmarket.dev`, `helios`/`dioscuri` on the oracle host, and `magic-ai-factory.com/arena` for ARGUS. That is a deliberate choice — see the *"Remote satellites"* block in [`docker-compose.core.yml`](../docker-compose.core.yml) — and it degrades gracefully: offline, those panels simply idle.

What was wrong with it was not the calls, but the silence. A stack that quietly contacts someone else's servers is something the operator should learn *before* it happens, not by reading a compose comment afterwards, so `start.sh` now prints the list on every run.

| You want | Do this | Result |
|---|---|---|
| The map live, satellites from our public endpoints | *(default)* | Panels populated; nothing sent beyond the requests themselves. |
| Nothing leaves your machine | `ECO_NO_REMOTE=1 ./start.sh` | Those seven variables are pointed at the discard port (`127.0.0.1:9`) — refused instantly, panels take the documented idle path. |
| Those satellites running **locally**, for real | `./start.sh --everything` | The everything tier builds them and calls nothing of ours. It refuses to start if any of our hosts survive into the resolved config — see [deploy-everything.md](deploy-everything.md#the-env_file-path-closed). |

Blanking the variables does **not** work, and the launcher deliberately does not do it: compose's `${VAR:-default}` falls back on empty as well as unset, so an empty value silently restores our hostname.

**One gap remains, and it is not fixed here.** `prometheus` and `grafana` take their external URL from base-file defaults (`PROMETHEUS_EXTERNAL_URL`, `GRAFANA_ROOT_URL`, `GRAFANA_DOMAIN`) that point at `magic-ai-factory.com`, and `ECO_NO_REMOTE=1` does not clear them. They affect generated links inside those two UIs, not data flow. The fix is not a local one: production relies on those same defaults rather than setting them in its own `.env`, so flipping them would break production's Grafana and Prometheus links on the next redeploy. It needs the values moved into the production environment first.

### Health wait + printed report

`start.sh` polls (every 3s, `curl -fsS -m 3`):

| Target | URL | Timeout |
|---|---|---|
| Factory API | `http://localhost:9081/api/health` | 90s |
| Hub | `http://localhost:9083/.well-known/ai-market.json` | 60s |
| Monitor | `http://localhost:9100/api/health` | 120s |

Mesh, Prometheus, and Grafana are not health-waited. On timeout it warns and continues.

Then it prints (Grafana at 9082 is intentionally not advertised; "Metrics" points at Prometheus under `/prometheus/`):

```
Core is up.

  Factory    http://localhost:9080              idea → real AI build
  Admin      http://localhost:9080/admin/login  user admin · pass <ADMIN_PW>
  Monitor    http://localhost:9100/monitor/     live universe · reputation graph · contours
  Hub        http://localhost:9083              federation / marketplace
  Mesh API   http://localhost:8090
  Metrics    http://localhost:9090/prometheus/

  stop: ./start.sh --down · logs: ./start.sh --logs · whole fleet: ./start.sh --full
```

**Admin password shown:** the value of `AIFACTORY_DEV_BOOTSTRAP_PASSWORD` from `.env`, **overridden** by `data/secrets/bootstrap_admin.txt` (whitespace-stripped) if that file exists. See [Admin login & first password](#admin-login--first-password).

### Smoke test

[`scripts/smoke_core.sh`](../scripts/smoke_core.sh) probes a running core: Factory API (`/api/health`, required), Factory web (`/`, required), Hub (`/.well-known/ai-market.json`, required), Mesh (`/health`, required), Prometheus (`/prometheus/-/ready`, optional), Monitor (`/api/health`, soft — 120s budget). Exits 0 (`core smoke OK`) only if no **required** check fails. Verified locally: **6/6 green** (Monitor universe `blockchain_ready:true`, `crypto_enabled:false`).

---

## Full fleet (`./start.sh --full`)

`--full` `exec`s [`scripts/quickstart_ecosystem.sh`](../scripts/quickstart_ecosystem.sh), which is a thin preflight wrapper — *"NOT a new deploy engine; deploy_ecosystem.sh remains the source of truth."* It then hands off to [`scripts/deploy_ecosystem.sh`](../scripts/deploy_ecosystem.sh).

### Preflight (in `quickstart_ecosystem.sh`)

1. **Docker + Compose v2** — three hard gates (`docker`, `docker compose version`, `docker info`), each `die`s.
2. **`.env` required** — unlike core `start.sh`, quickstart does **not** auto-generate secrets or copy `.env.demo`. If `.env` is missing it warns `cp .env.example .env` and `die`s.
3. **nginx / public-URL tier** — if `--public-url` is given it captures `PUBLIC_URL` and **warns** (does not die) if `nginx` is missing (Level-3 TLS tier). With no `--public-url`, nginx is not checked (local tier).

Then: `scripts/deploy_ecosystem.sh "$@"`. Afterwards it prints next-steps (local URLs, re-verify command, and — only when `--public-url` was set — the `sudo CERTBOT_EMAIL=… ./scripts/setup-modelmarket-ssl.sh` one-shot), plus a note that **Metis, DIOSCURI, HELIOS are NOT launched by the fleet script**.

### Exact ordered deploy sequence (`deploy_ecosystem.sh`)

**Pre-flight (before step 1):** `ensure_deploy_satellites.sh` (verifies satellite dirs exist for Docker COPY, fetches if missing) → `docker network create ecosystem` (if absent) → `ecosystem_process_cleanup.sh --disk`.

| # | Label | Script | Container(s) | Port(s) | Fatal? |
|---|---|---|---|---|---|
| 1/7 | Factory (aicom-app) | [`deploy.sh`](../scripts/deploy.sh) | `aicom-app-1` | Frontend **9080**, API **9081** | yes |
| 2/7 | Hub (:9083) | [`deploy_hub.sh`](../scripts/deploy_hub.sh) | `modelmarket-hub` | **9083** (`127.0.0.1:9083`) | yes |
| 3/7 | Mesh (:8090) | [`deploy_mesh.sh`](../scripts/deploy_mesh.sh) | `aicom-mesh-api` | **8090** | yes |
| 4/7 | ARGUS (reference agent) | [`deploy_argus.sh`](../scripts/deploy_argus.sh) | `argus` + `argus-uni` | LIVE **8787**, UNI **8788** | yes |
| 5/7 | Alien Monitor + Pulse | [`deploy_alien_monitor.sh`](../scripts/deploy_alien_monitor.sh) | `alien-monitor` + `pulse-terminal` | Monitor **9100**, Pulse **5199** (+ Anvil `8545`, opt-in Solana `8899`, Vite dev `5173`) | yes |
| 6/7 | UNI lottery relayer | [`deploy_lottery_uni.sh`](../scripts/deploy_lottery_uni.sh) | `ailottery-relayer-uni` | **9195** | **soft** (`|| WARN`) |
| 7/7 | Ecosystem landing | [`deploy_ecosystem_landing.sh`](../scripts/deploy_ecosystem_landing.sh) | static nginx site | 80/443 | **soft** (`-x`-guarded) |

Only step 1 receives `--public-url` (via `DEPLOY_ARGS`); no other step does. Steps 1–5 abort the fleet on failure; 6 and 7 only warn.

**Per-step highlights:**

- **1 — Factory:** requires `.env` + an intact tree (`require_intact_tree`). Runs `fill_production_env.py` (this is where `--public-url` sets CORS/site URLs). Layers `docker-compose.host-docker.yml` **or** `docker-compose.dind.yml`, plus `docker-compose.secrets.yml` if all four `data/secrets/llm/*_api_key` exist.
- **2 — Hub:** builds `modelmarket-hub`, `docker run` with `-p 127.0.0.1:9083:9083`, factory data mounted read-only. Health-gates `/.well-known/ai-market.json`, then syncs the factory catalog and crawls the oracle-family well-known. *Do NOT redeploy via `aimarket-hub/docker compose`.*
- **3 — Mesh:** ensures mesh tokens + `MESH_HUB_URL`, flips `ALIEN_MODE test→real`, builds `docker-compose.prod.yml`, health-gates `:8090/health`.
- **4 — ARGUS:** forces `ARGUS_HTTP_PORT=8787`, wires the Monitor run feed (`ALIEN_API_TOKEN`). LIVE `:8787/health` fatal; UNI `:8788/health` WARN-only (needs host Anvil on `:8545`).
- **5 — Alien Monitor:** mode = `universe` by default from the fleet (embedded Anvil; Solana opt-in). Health-gates Monitor `:9100/api/health` + Pulse `:5199/` (both fatal). DIOSCURI `:8790` / HELIOS `:8791` are remote poll-only, not deployed here.
- **6 — UNI lottery:** resolves the `evm_lottery` address from the Monitor; `RPC_URL=http://127.0.0.1:8545`, `CHAIN_ID=31337`; health-gates `:9195/healthz`.
- **7 — Landing:** rebuilds SEO landings; **SKIPs cleanly (exit 0)** if neither `/var/www` nor `/etc/nginx/sites-available` exists — i.e. no-ops on a laptop.

**Warm-up + verify:** after step 7 the engine warms the Factory API (`/api/health`, `/api/products`, `/api/marketing/trust-metrics`), then runs [`scripts/verify_ecosystem_full.sh`](../scripts/verify_ecosystem_full.sh) ("17+ checks") unless `--skip-verify` was passed. Verify exits non-zero if any check fails.

**Final banner:**

```
Factory:  http://127.0.0.1:9081
Hub:      http://127.0.0.1:9083
Mesh:     http://127.0.0.1:8090
ARGUS:    http://127.0.0.1:8787/health
Monitor:  https://monitor.modelmarket.dev/ (or :9100 local)
Landing:  https://modeldev.modelmarket.dev/
```

### Local vs `--public-url` tiers

| Aspect | Local fleet (no flag) | `--public-url https://…` (production/TLS) |
|---|---|---|
| nginx preflight | not checked | quickstart warns if `nginx` missing |
| `--public-url` propagation | n/a | forwarded **only** to `deploy.sh` (step 1) |
| Factory env fill | CORS/site → localhost | `fill_production_env.py --public-url` sets CORS/site to the public host |
| Monitor mode | `universe` (embedded Anvil, crypto off) | still `universe` unless `ALIEN_MODE=real`; LIVE Base needs `AIFACTORY_CRYPTO_ENABLED=1` |
| nginx routing | patch functions no-op (no site file) | Argus/Monitor/Pulse snippets patched; `nginx -t` + reload |
| Landing (step 7) | SKIP (no `/var/www`) | rsync to `/var/www/modeldev.modelmarket.dev` + certbot 443 |
| TLS one-shots | not printed | quickstart prints `sudo CERTBOT_EMAIL=… ./scripts/setup-modelmarket-ssl.sh` |
| Access URLs | `127.0.0.1:9080/9081/9083/8090/8787/9100/5199/9195` | `https://magic-ai-factory.com/` (+ `/monitor/`, `/pulse/`, `/arena/`, `/argus/`), `https://modelmarket.dev`, `https://modeldev.modelmarket.dev/` |

`--public-url` does **not** by itself enable crypto or change the Monitor mode — those are separate env switches (`ALIEN_MODE`, `AIFACTORY_CRYPTO_ENABLED`).

**Not launched by the fleet script** (documented in [quickstart-ecosystem-deploy.md](quickstart-ecosystem-deploy.md)): Metis, DIOSCURI, HELIOS (poll-only from the Monitor); the Level-4 oracle host (`setup-oracles-platon-on-host.sh` + `announce-platon-oracles.sh`); and on-chain Base mainnet (`deploy_ecosystem_base.sh` / `deploy_lottery_base.sh`, chain 8453).

---

## One click (Dev Container / Codespaces)

Open the repo in a Dev Container or GitHub Codespace and the box builds itself from [`.devcontainer/devcontainer.json`](../.devcontainer/devcontainer.json).

- **Base image:** `mcr.microsoft.com/devcontainers/base:ubuntu-24.04`, name *"AI-Factory · core"*, `remoteUser: vscode`.
- **Features:** Docker-in-Docker (so `./start.sh` can build/run compose inside the box) + Python 3.11.
- **Host requirements:** 4 CPUs, 8 GB memory, 32 GB storage.
- **Forwarded ports:** `9080, 9081, 9083, 9100, 8090, 9090`.

| Port | Label | On auto-forward |
|---|---|---|
| 9080 | Factory (idea → build) | openBrowser |
| 9100 | Alien Monitor (universe) | notify |
| 9083 | Hub (federation) | silent |
| 8090 | Service Mesh API | silent |
| 9081 | Factory API | silent |
| 9090 | Prometheus | silent |

- **`postCreateCommand`:** runs [`.devcontainer/post-create.sh`](../.devcontainer/post-create.sh), which copies `.env.demo → .env` if needed and injects any LLM key present as an env/Codespaces **secret** (`DEEPSEEK_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `TOGETHER_API_KEY`, `GROQ_API_KEY`) into `.env` — never overwriting an existing key. It does **not** run `./start.sh` itself.

**How to supply the LLM key:** add one of the key names above as a Codespaces (or Dev Container) secret. On create it lands in `.env` automatically. Then in the terminal run:

```bash
./start.sh --no-open
```

(`--no-open` because browser-opening is handled by port forwarding.) Open the forwarded ports — Factory at `:9080`, Monitor at `:9100/monitor/`.

---

## Manual Docker Compose & overlays

All overlays layer on the base [`docker-compose.yml`](../docker-compose.yml) (v2.1) — a single-container "batteries-included" design where the FastAPI API, pipeline worker, and Next.js all run in ONE `app` container. The base owns `data-init`, `data-keep`, `app`, `prometheus`, `grafana`, and the `aicom_net` network.

### Base — single container

```bash
docker compose up -d --build
```

Brings up `data-init` → `app` (Factory web **9080** / API **9081**) → `prometheus` (**9090**) → `grafana` (**9082**). No Hub, Mesh, or Monitor. This is the plainest way to run just the Factory.

### Core overlay — what `./start.sh` runs

```bash
docker compose -f docker-compose.yml -f docker-compose.core.yml up -d --build
```

Adds `hub`, `mesh-api`, `alien-monitor`. Needs `MESH_API_TOKEN` / `MESH_ADMIN_TOKEN` / `GRAFANA_ADMIN_PASSWORD` in `.env` (`./start.sh` generates these; a raw run fails fast without them).

### Every overlay

Combine pattern: `docker compose -f docker-compose.yml -f <overlay> up -d` (add `--build` when the overlay introduces built images — split, prod, core).

| Overlay | What it changes / adds | When to use | Combine command |
|---|---|---|---|
| [`docker-compose.core.yml`](../docker-compose.core.yml) | **Adds** `hub`, `mesh-api`, `alien-monitor` on the `aicom_net` bridge. Add-only; crypto off (local Anvil sim, fake USDT). | The "2 a.m. tinker" tier — real AI + the live Monitor, without the full fleet. Normally via `./start.sh`. | `-f docker-compose.yml -f docker-compose.core.yml up -d --build` |
| [`docker-compose.split.yml`](../docker-compose.split.yml) | **Overrides** `app` to be API-only; **adds** `frontend`, `pipeline-worker`, `director-worker` (same image, differ by `AICOM_ROLE`). Still shares one SQLite. | Per-role isolation/observability instead of one supervised process tree. Header advises moving to Postgres next. | `-f docker-compose.yml -f docker-compose.split.yml up -d --build` |
| [`docker-compose.pg.yml`](../docker-compose.pg.yml) | **Adds** `postgres:16-alpine`, wires `app` via `DATABASE_URL`. `POSTGRES_PASSWORD` **required** (`${VAR:?}`). | Postgres instead of the zero-config SQLite default. Precursor to running split safely. | `-f docker-compose.yml -f docker-compose.pg.yml up -d` |
| [`docker-compose.prod.yml`](../docker-compose.prod.yml) | Production superset: pg + split + guards. **Adds** `postgres` + `redis`, splits services, pins Postgres, `AIFACTORY_PROD=1`, Redis queue, healthchecks, restart caps. | Production / soak-testing. Requires `.env` bootstrap (`POSTGRES_PASSWORD`, `GRAFANA_ADMIN_PASSWORD`, ≥1 LLM key). | `-f docker-compose.yml -f docker-compose.prod.yml up -d --build` (or [`./scripts/run_prod_compose.sh`](../scripts/run_prod_compose.sh) `up -d --build`) |
| [`docker-compose.dind.yml`](../docker-compose.dind.yml) | **Adds** a privileged `docker:27.4.0-dind` sidecar; points `app` at it via `DOCKER_HOST` (TLS). Isolates product-build compose from the host daemon. | Whenever the factory builds/runs sandboxed products. Enabled by default via `run-compose.sh` / `deploy.sh`. Header flags a host-escape risk. | `-f docker-compose.yml -f docker-compose.dind.yml up -d` |
| [`docker-compose.host-docker.yml`](../docker-compose.host-docker.yml) | **Overrides** `app` to bind-mount `/var/run/docker.sock`. Bypasses the DinD sidecar. | Emergency fallback ONLY, on a throwaway host. Header: *"DANGER — DIRECT HOST ROOT … NO isolation here."* Never in prod / near secrets. | `AIFACTORY_USE_HOST_DOCKER=1 ./run-compose.sh` (≡ `-f docker-compose.yml -f docker-compose.host-docker.yml up -d`) |
| [`docker-compose.host-gateway.yml`](../docker-compose.host-gateway.yml) | Adds `extra_hosts: host.docker.internal:host-gateway` to `app`. No new services. | When `app` must reach a host service, e.g. local Ollama on `:11434`. | `-f docker-compose.yml -f docker-compose.host-gateway.yml up -d` |
| [`docker-compose.secrets.yml`](../docker-compose.secrets.yml) | Mounts LLM keys as Docker **secrets** from `./data/secrets/llm/*` (not visible in `docker inspect`). No new services. | Key hygiene. Hardening, not strictly required — the entrypoint also reads `data/secrets/llm/*` when the files exist. | `-f docker-compose.yml -f docker-compose.secrets.yml up -d` |

**Mutually exclusive (pick one per axis):**
- **Docker access:** `dind.yml` XOR `host-docker.yml` (both set how `app` reaches a Docker daemon).
- **Topology:** `prod.yml` already contains split's role-splitting — don't stack `split.yml` on `prod.yml`.
- **DB:** `prod.yml` already contains pg's `postgres` + `DATABASE_URL` (plus Redis + hard pinning) — don't add `pg.yml` on top.

**Common combinations:** the everyday dev launch merges base + **dind** automatically (`./run-compose.sh` / `deploy.sh`). `split + pg` is the documented upgrade path (`prod.yml` is that pre-baked with guards). `core` pairs naturally with **dind** (real builds), **secrets** (key hygiene), **host-gateway** (local Ollama). `secrets` and `host-gateway` are additive/orthogonal — safe to append to anything. Put the topology overlay (split/prod/core) before the small additive ones (compose is last-wins).

---

## All satellites (what `--full` deploys)

"In core?" = brought up by `./start.sh` core (Core), vs requiring `./start.sh --full`.

| Satellite | Role | Port(s) | In core? |
|---|---|---|---|
| **aimarket-hub** | AIMarket Hub — protocol-v2 marketplace/registry (paid invokes, escrow, federation) | `9083` (`127.0.0.1`) | **Core (Hub)** |
| **ai-service-mesh** | Orchestration mesh; bundles hub + Postgres + mesh-api + dashboard | mesh-api `8090`, dashboard `5173`→80, embedded hub `9083` | **Core (Mesh)** |
| **alien-monitor** | 3D graph of Hub, Factory & on-chain metrics | API `9100` (host-net) | **Core (Monitor)** |
| **argus** | ARGUS-3 demand-side agent · WARDEN MCP firewall (crypto off by default) | `8787` (argus), `8788`→8787 (argus-uni) | `--full` |
| **dioscuri** | Community agent — twin Telegram+Discord bots (Castor/Pollux) | `8790` | `--full` |
| **gaia** | Physical-world oracle gateway — attested IoT sensors + plausibility verify | API `9320`, landing `5185`→80 (both `127.0.0.1`) | `--full` |
| **helios** | Broadcast layer of the AIMarket ecosystem | `8791` | `--full` |
| **lottery** | On-chain oracle draws · machine UBI for mesh agents | relayer `8090`, showcase `5182` (both `127.0.0.1`) | `--full` |
| **metis** | Cognition/verification tier — factory confidence gate | coordinator `8080`; nodes `8443`/`8444` internal | `--full` |
| **oracles** | 17 signed math capabilities (randomness, VDF, reputation, …) | landing `5180`→80, chronos `9300`, oracle-family `9400` (all `127.0.0.1`) | `--full` |
| **platon** | Platon federated oracle + UMBRAL cave app | oracle `9200` (internal only), frontend `8080`→80 (`127.0.0.1`) | `--full` |
| **skopos** | Fleet observability — analytics, Security Center, AI analyst (Streamlit) | `8501` | `--full` |
| **aimarket-mcp** | Shared MCP gateway: `web_fetch` · `web_search` · `metis_verify` | `9090` (`127.0.0.1`) | `--full` |
| **aicom-landing** | Standalone AI landing-page generator service | `3847` (`127.0.0.1`) | `--full` |
| **relay-scout-fix** | Relay Scout — autonomous Python health watchdog | `8000` | `--full` |
| **apps/pulse-terminal** | Pulse (ACEX) terminal — CapShare NAV · Proof-of-Audit · live pricing | `5199` (host-net) | `--full` (built/run via `alien-monitor/docker-compose.prod.yml`, no own compose) |

**Notes:**
- **Port collisions across separate deploys** (never co-run in the same stack): `8090` is used by both ai-service-mesh mesh-api and the lottery relayer; `8080` by both Metis coordinator and Platon frontend; `9090` by both Prometheus and aimarket-mcp (MCP binds loopback). Flag if co-deploying.
- **alien-monitor & pulse-terminal use `network_mode: host`** in their *own* composes / the `--full` fleet (no `ports:` mapping); public access is nginx-only (`/monitor/`, `/pulse/`) — `9100`/`5199` should be firewalled on the host. **In the core overlay** ([`docker-compose.core.yml`](../docker-compose.core.yml)) alien-monitor instead runs on the `aicom_net` **bridge** with `9100` published — the one deliberate change from the prod compose, so it works cross-platform (incl. macOS/Docker Desktop) with **no** loss of Monitor features (universe, contours, reputation graph, remote-satellite polling, ARGUS run panel).
- Most `--full` satellites bind to `127.0.0.1`; `argus`, `dioscuri`, `helios`, `skopos`, `relay-scout-fix`, and ai-service-mesh mesh-api/dashboard bind to all interfaces.
- ai-service-mesh embeds its own hub on `9083`, distinct from the standalone aimarket-hub satellite.

---

## Other / legacy entrypoints

`./start.sh` is the modern door (compose core, one LLM key, crypto OFF, auto-generated secrets **including the admin password**). Everything here is older, lower-level, or a helper.

| Entrypoint | What it is | Ports / data | Relation to `./start.sh` |
|---|---|---|---|
| [`run.sh`](../run.sh) | Legacy single-container `docker build` + `docker run -d` (no compose). Factory app only — no Hub/Mesh/Monitor/Prometheus. Host first-run prompt for autonomous vs ideas-only pipeline. Forwards only `JWT_SECRET_KEY`, `DEEPSEEK_API_KEY`, `TOGETHER_API_KEY`, `GROQ_API_KEY`. | Frontend `8080`, backend `8081` (overridable). Data in **`~/aicom-data`** (not `./data`). | The old single-container door `start.sh` replaces. Use when you want just the app, no compose, or the separate `~/aicom-data` volume. Substrate for `demo.sh` + `quickstart.sh`. |
| [`run-compose.sh`](../run-compose.sh) | Legacy full compose stack + monitoring: base + **dind** (or **host-docker** if `AIFACTORY_USE_HOST_DOCKER=1`) + **secrets** (when all four LLM key files exist). Runs `init-compose-volumes.sh`, `fill_production_env.py`; **hard-requires `GRAFANA_ADMIN_PASSWORD`**. Flags: `--build`, `--down`, `--down-volumes` (destructive), `--logs`, `--help`. | App `9080`, API `9081`, Prometheus `9090`, Grafana `9082`. Does **not** use `docker-compose.core.yml`. | Predecessor of the compose approach — heavier, more production-shaped. Use for full Grafana/Prometheus monitoring, the DinD/host-docker toggle, or the secrets overlay. |
| [`demo.sh`](../demo.sh) | "Submit a product idea" driver, not a stack launcher. Ensures the `ai-factory` container is up (or `./run.sh --no-build`), waits for `/api/health`, logs in as `admin`, POSTs an idea. Profiles: `full_software` (default), `--landing`, `--full-stack` (alias), `--no-open`, `--compose`. | Default target `run.sh` container (`8080`); `--compose`/`DEMO_BASE_URL` points it at the `9080` compose/core UI. | Orthogonal — an action on top of a running stack. Works against a `start.sh` stack with `--compose`. |
| [`batch-demo.sh`](../batch-demo.sh) | Loops `demo.sh` over 5 hard-coded showcase ideas. Requires a running stack + API. | (inherits from `demo.sh`) | A demo-seeding convenience wrapper around `demo.sh`. |
| [`scripts/quickstart.sh`](../scripts/quickstart.sh) | Legacy "clone → one command → running demo": `./run.sh` (single container) then `./demo.sh --no-open` (enqueue one idea). Default profile `marketing_landing`; a positional idea arg switches to `full_software`. Flags: `--no-build`, `--full`/`--full-stack`, `--landing`. | Bound to the `run.sh` path (`8080/8081`). | The conceptual ancestor of `start.sh`, but built on `run.sh` + `demo.sh` rather than compose core. |
| [`entrypoint.sh`](../entrypoint.sh) | In-container entrypoint (runs inside the image, not invoked by a human). Loads secrets, first-run pipeline-mode prompt, JWT keys, **admin bootstrap**, prod startup guard, DB backend selection + JSON→SQLite migration, `AICOM_ROLE` dispatch, then uvicorn `:8081` + Next.js `:8080`. | — | **Downstream of every launcher** — `run.sh`, `run-compose.sh`, and `start.sh` all run this as the container entrypoint. Where the admin bootstrap actually happens. |

---

## Admin login & first password

Username is always **`admin`**, role `super_admin`. Bootstrap runs **only when no admin exists** (neither `data/config/admin_users.json` with a non-empty `users` list nor legacy `data/config/admin.json` with a `password_hash`). Existing installs are never reset.

The initial password is chosen by a fixed 3-tier priority (`security/bootstrap_admin.py`):

1. **`dev_env`** — `AIFACTORY_DEV_BOOTSTRAP_PASSWORD` (≥ 8 chars). In production, rejected if it is a known-insecure value (`demo123`, `admin123`, `password`, `changeme`, `admin`, `factory`). No file written.
2. **`interactive`** — only if stdin is a TTY. `getpass` prompts (min 8 chars, up to 3 attempts); on 3 failures falls through to generated. No file written.
3. **`generated`** — fallback (non-TTY, no env var). `secrets.token_urlsafe(18)` written to `${AIFACTORY_DATA_ROOT:-/app/data}/secrets/bootstrap_admin.txt` (`chmod 0600`), as two lines: `username=admin` / `password=<token>`.

### Per mode

| Launcher | TTY in container? | `AIFACTORY_DEV_BOOTSTRAP_PASSWORD`? | Source | Where to read the password |
|---|---|---|---|---|
| **`./start.sh`** | No | **Yes** — generated into `.env` (24 hex chars) | `dev_env` | The value in `.env`; `start.sh` echoes it as `pass <ADMIN_PW>`. No `bootstrap_admin.txt` written. |
| **`./run.sh`** | No (`docker run -d`; env var not forwarded) | No | `generated` | Random token in **`~/aicom-data/secrets/bootstrap_admin.txt`**. |
| **`./run-compose.sh`** | No (`compose up -d`) | No (unless operator sets it) | `generated` | **`data/secrets/bootstrap_admin.txt`** (repo `./data` bind-mount). |
| **Interactive install** (`docker compose run --rm -it app`) | **Yes** | No | `interactive` | Typed at the console; nothing written to disk. |
| **`demo.sh` / `batch-demo.sh`** | — (consumers) | — | reads existing creds | `DEMO_ADMIN_PASSWORD`, else `data/secrets/bootstrap_admin.txt`. |

**Two real caveats:**

1. **`run.sh` is not actually interactive for the admin password.** It uses `docker run -d`, so the container stdin is not a TTY → the password is **generated** to `bootstrap_admin.txt`, not prompted. The only truly interactive path is `docker compose run --rm -it app`. (The first-run prompt you see under `run.sh` is the host-side *pipeline-mode* question, not the admin password.)
2. **Generated-file format vs consumers.** The generated file is two `key=value` lines, but `demo.sh` / `start.sh` read the whole file as the password (`tr -d`), yielding `username=adminpassword=<token>`. So to read an auto-generated password reliably, open the file and take the `password=` line by hand — or set `AIFACTORY_DEV_BOOTSTRAP_PASSWORD` / `DEMO_ADMIN_PASSWORD` explicitly. `bootstrap_admin.py` never *reads* this file as input, so pre-seeding a one-line password does not set the admin password (it only makes the `tr -d` consumers work).

See [security-persistence.md](security-persistence.md) and `docs/security.md` for the full story.

---

## Full port map

### Core stack (`./start.sh`)

| Port | Service | Where set |
|---|---|---|
| **9080** | Factory web / storefront (Next.js) | `docker-compose.yml` → `${AICOM_PORT_FRONTEND:-9080}:8080` |
| **9081** | Factory API (FastAPI) | `docker-compose.yml` → `${AICOM_PORT_API:-9081}:8081` |
| **9082** | Grafana | `docker-compose.yml` → `${AICOM_PORT_GRAFANA:-9082}:3000` |
| **9090** | Prometheus (served under `/prometheus/`) | `docker-compose.yml` → `${AICOM_PORT_PROMETHEUS:-9090}:9090` |
| **9100** | Alien Monitor (served at `/monitor/`) | `docker-compose.core.yml` → `${ALIEN_PORT:-9100}:9100` |
| **9083** | AIMarket Federation Hub | `docker-compose.core.yml` → `${AIMARKET_HUB_HOST_PORT:-9083}:9083` (host-published in core, **and** reachable in-stack as `http://hub:9083`); also `aimarket-hub/docker-compose.yml` (`127.0.0.1:9083`), `ai-service-mesh/docker-compose.yml` (`9083`). |
| **8090** | Service Mesh API | `docker-compose.core.yml` → `${MESH_HOST_PORT:-8090}:8090` (host-published in core, **and** `http://mesh-api:8090` in-stack); also `ai-service-mesh/docker-compose.yml` (`8090`; override `127.0.0.1:8095:8090`). |
| **5173** | Mesh dashboard (frontend) | Standalone `ai-service-mesh/docker-compose.yml` only (`5173:80`). Not in the core overlay. |
| **5199** | Pulse Terminal (served at `/pulse/`) | Not in core compose. `alien-monitor/docker-compose.prod.yml` (`pulse-terminal`, `network_mode: host`), hardcoded in `apps/pulse-terminal`. |

> In the **core** overlay all six long-lived services publish host ports: `app` (9080/9081), `hub` (9083), `mesh-api` (8090), `alien-monitor` (9100), `prometheus` (9090), `grafana` (9082). `hub` and `mesh-api` are *additionally* reachable in-stack by service name (`http://hub:9083`, `http://mesh-api:8090`) — the path the Monitor uses.

### Additional ports (full-fleet satellites)

| Port | Service | Where set |
|---|---|---|
| 9320 | GAIA physical-oracle | `gaia/docker-compose.yml` (`127.0.0.1:9320`) |
| 5185 | GAIA landing | `gaia/docker-compose.yml` (`127.0.0.1:5185:80`) |
| 9200 | Platon oracle | `platon/docker-compose.yml` — container listen port only (`PLATON_PORT`); **not** host-published. Only the Platon frontend is published (`127.0.0.1:8080:80`). |
| 8080 | Platon landing | `platon/docker-compose.yml` (`127.0.0.1:8080:80`) |
| 9300 | Chronos oracle | `oracles/docker-compose.yml` (`127.0.0.1:9300`) |
| 9400 | Oracle-family | `oracles/docker-compose.yml` (`127.0.0.1:9400`) |
| 5180 | Oracles landing | `oracles/docker-compose.yml` (`127.0.0.1:5180:80`) |
| 8080 / 8443 / 8444 | Metis coordinator + 2 nodes | `metis/docker-compose.yml` |
| 8501 | SKOPOS (Streamlit) | `skopos/docker-compose.yml` (`8501:8501`) |
| 8790 | DIOSCURI community agent | `dioscuri/docker-compose.yml` (`8790:8790`) |
| 8791 | Helios | `helios/docker-compose.yml` (`8791:8791`) |
| 8090 / 5182 | Lottery relayer + economy UI | `lottery/docker-compose.yml` (`127.0.0.1:8090`, `127.0.0.1:5182`) |
| 9090 | aimarket-mcp server | `aimarket-mcp/docker-compose.yml` (`127.0.0.1:9090`; collides with Prometheus 9090 — separate stacks, loopback) |
| 8787 / 8788 | ARGUS agent (two instances) | `argus/docker-compose.yml` (`8787:8787`, `8788:8787`) |
| 3847 | aicom landing | `aicom-landing/docker-compose.yml` (`127.0.0.1:3847`) |
| 8545 / 8899 / 9195 | Universe Anvil / opt-in Solana / UNI lottery relayer | fleet steps 5–6 (`deploy_alien_monitor.sh`, `deploy_lottery_uni.sh`) |

---

## Safe by default

**Crypto is OFF unless you opt in.** `core/crypto_config.py` is the single source of truth: `AIFACTORY_CRYPTO_ENABLED` is read with a default of `0` and is True only for truthy `{1, true, yes, on}` (case-insensitive). With the switch off, *nothing loads a wallet, contacts a chain/RPC, opens a payment channel, returns a 402, verifies a transaction on-chain, or settles UNI/lottery.* Everything still runs on a free tier — federation signing and internal accounting keep working, it just never touches money. The standalone packages (aimarket-hub, oracles, ai-service-mesh, lottery, ARGUS) read the **same** env var with the **same** default-off rule.

Enabling crypto is one deployment-wide opt-in (`AIFACTORY_CRYPTO_ENABLED=1`); even then each component needs its own recipient addresses/RPC/keys plus the `AIFACTORY_PROD` interlocks.

**Production startup guard.** `security/prod_startup_guard.py`: when production mode is on (`AIFACTORY_PROD`/`AIFACTORY_PRODUCTION` truthy, or `AIFACTORY_ENV ∈ {production, prod, live}`), `assert_production_startup_safe()` refuses to boot (`SystemExit(1)`) on any hardening gap — known-weak admin password, ephemeral JWT, broad SSO CIDRs, SQLite backend, no LLM key, simulated ZK, host-Docker/DinD-on-host escape, and (only when crypto is on) payment stub/testnet enabled or placeholder/zero recipient & contract addresses (and the inverse: addresses set while crypto is off).

The result: the core stack is safe to run on a laptop — real AI, live Monitor, **no real funds**, and production can only start once it is actually hardened.

---

## See also

- [deploy-everything.md](deploy-everything.md) — The **everything tier** (`./start.sh --everything`): the three-host production topology collapsed onto one machine, reached at `http://<ip>:<port>` with no nginx, no TLS and no domains. Costs, tiers, the full 33-port service table, the port remaps, what is deliberately not deployed, and teardown.
- [deploy-ecosystem.md](deploy-ecosystem.md) — Full ecosystem redeploy: the ops-grade reference for the fixed script order, partial redeploys, and the Hub-redeploy hazard.
- [quickstart-ecosystem-deploy.md](quickstart-ecosystem-deploy.md) — Tiered greenfield quick-start for a bare Ubuntu VPS; also covers Metis/DIOSCURI/HELIOS, the Level-4 oracle host, and on-chain Base mainnet.
- [ecosystem-architecture.md](ecosystem-architecture.md) — C4-style architecture reference (Factory + AIMarket Protocol v2 + Hub + desktop SKUs + on-chain settlement) with mermaid diagrams.
- [security-persistence.md](security-persistence.md) — SQLite-backed persistence for login rate-limits and OIDC nonce replay protection (no Redis needed in the single-container stack).
- [deploy-ecosystem-runbook.md](deploy-ecosystem-runbook.md) — Prod redeploy runbook + `.env` / `data/secrets/` preflight checklist to run before any full redeploy.
- [onboard-a-node.md](onboard-a-node.md) — The 5-step procedure for a new node to join: discoverable, verifiable, paid, visible in the Monitor, lottery-eligible.