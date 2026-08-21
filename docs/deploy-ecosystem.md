# Full ecosystem redeploy

Production runs several containers besides the main Factory Compose app. A **full redeploy** must use the root scripts in a fixed order. Skipping steps or using the wrong Hub command leaves services down until manual recovery.

## One command (recommended)

Greenfield wrapper (Docker + `.env` preflight):

```bash
./scripts/quickstart_ecosystem.sh
./scripts/quickstart_ecosystem.sh --public-url https://magic-ai-factory.com
./scripts/quickstart_ecosystem.sh --skip-verify
```

Engine (same steps):

```bash
./scripts/deploy_ecosystem.sh
./scripts/deploy_ecosystem.sh --public-url https://magic-ai-factory.com
./scripts/deploy_ecosystem.sh --skip-verify
```

Tiered runbook (EN / RU / ES): [`quickstart-ecosystem-deploy.md`](./quickstart-ecosystem-deploy.md)

## Manual order (same as the script)

| Step | Script | Service | Port / URL |
|------|--------|---------|------------|
| 1 | `./scripts/deploy.sh` | Factory (`aicom-app-1`) | `:9081` API, `:9080` frontend |
| 2 | **`./scripts/deploy_hub.sh`** | Hub (`modelmarket-hub`) + factory→hub sync | `:9083` |
| 3 | `./scripts/deploy_mesh.sh` | Mesh (`aicom-mesh-api`) | `:8090` |
| 4 | `./scripts/deploy_argus.sh` | ARGUS-3 reference agent | `:8787` |
| 5 | `./scripts/deploy_alien_monitor.sh` | Alien Monitor + Pulse + nginx | `/monitor/` |
| 6 | `./scripts/deploy_lottery_uni.sh` | UNI lottery relayer (non-fatal) | `:9195` |
| 7 | `./scripts/deploy_ecosystem_landing.sh` | Ecosystem map (non-fatal) | `modeldev.modelmarket.dev` |
| 8 | warm-up + `./scripts/verify_ecosystem_full.sh` | 17+ smoke checks | — |

**Not included:** seventeen oracles (Level 4 — separate host by default), Metis, DIOSCURI, on-chain Base deploy. See [`quickstart-ecosystem-deploy.md` §9](./quickstart-ecosystem-deploy.md#9-what-one-vps-does-not-include).

## Hub — do not use subfolder Compose for redeploy

**Correct:**

```bash
./scripts/deploy_hub.sh
```

**Wrong for production redeploy:**

```bash
cd aimarket-hub && docker compose up -d --build   # breaks image/context; Hub can disappear
```

`deploy_hub.sh` builds from the **monorepo root** (`modelmarket-hub:latest`, container `modelmarket-hub`), matches TLS setup in `scripts/setup-modelmarket-ssl.sh`, and replaces the container safely.

The file `aimarket-hub/docker-compose.yml` is kept in sync for local dev reference only; **ops redeploy path is always `deploy_hub.sh`**.

## Partial redeploys

| Goal | Command |
|------|---------|
| Factory only | `./scripts/deploy.sh` |
| Hub only | `./scripts/deploy_hub.sh` |
| Mesh + Monitor (demo stack) | `./scripts/deploy_demo_stack.sh` (assumes Factory + Hub already up) |
| Verify only | `./scripts/verify_ecosystem_full.sh` |

## After redeploy

- Expect **`17/17 PASS`** from `verify_ecosystem_full.sh`.
- Hub manifest: `curl -s http://127.0.0.1:9083/.well-known/ai-market.json`
- Public Hub: `https://modelmarket.dev` (see [`production-modelmarket-dev.md`](./production-modelmarket-dev.md))

**Подробный runbook для ops** (секреты, Monitor auth, channel secret, post-deploy чеклист, cron): [`deploy-ecosystem-runbook.md`](./deploy-ecosystem-runbook.md).

## Agents / automation

When asked to restart or redeploy the **whole core fleet**, run from repo root:

```bash
./scripts/quickstart_ecosystem.sh
# or
./scripts/deploy_ecosystem.sh
```

Never stop/remove `modelmarket-hub` without immediately running `deploy_hub.sh`.
