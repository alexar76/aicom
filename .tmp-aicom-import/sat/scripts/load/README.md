# Ecosystem load tests (Locust)

HTTP load coverage for the fleet Locust file in this folder. Mesh-only tests also live
in `ai-service-mesh/backend/load/`. Factory KI-3 soak is `./scripts/load_test_factory.sh`.
Metis has a separate k6 script: `metis/deploy/loadtest.k6.js`.

Host map (which URL hits which box): [`topology.py`](topology.py).
`python3 scripts/load/topology.py --check-dns` flags A-record drift.

| Block | Local default | Public URL | Server (SSH) | Endpoints |
|-------|---------------|------------|--------------|-----------|
| Factory | `:9081` | `magic-ai-factory.com` | factory `my-vps` | `/api/health`, trust-metrics, `/api/products` |
| Frontend | `:9080` | same | factory | `/` |
| Hub | `:9083` | `modelmarket.dev` | factory | well-known, stats/live, search, capital/pricing, health |
| Mesh | `:8090` | `service-mesh.modelmarket.dev` | factory | `/v1/stats`, activity, agents, optional `POST /v1/tasks` |
| ARGUS | `:8787` | `magic-ai-factory.com` | factory | `/arena`, `/arena/stats`, optional `POST /ask` |
| Monitor | `:9100` | `monitor.modelmarket.dev` | factory | `/api/health`, `/monitor/api/state` |
| Pulse | `:5199` | `pulse.modelmarket.dev` | factory | `/pulse/` and `/` |
| ATLAS / THEMIS / forge | — | `atlas` / `themis` / `forge` / `verify`.modelmarket.dev | factory | fleet GETs |
| GAIA / oracles / MOMUS | — | `iot` / `oracles` / `lottery` / `momus` / `logos`.modelmarket.dev | oracles `admin-vps` | fleet GETs |
| Metis / SKOPOS | — | `metis` / `skopos`.modelmarket.dev | metis (`skopos.modelmarket.dev`) | `/health`, Metis `POST /v1/verify` |

Heavy POSTs hit **the same server as the matching read**. Tokens: ARGUS from `argus` on `my-vps`, Mesh from factory `.env`, Metis verify needs no key (LLM on Metis host). Hub invoke uses the factory Hub (`modelmarket.dev`), not the lab hub on `competing-lab`.

---

Полная методика (смесь запросов, три режима, критерии, preflight 2026-09-14):
[`METHODOLOGY.md`](METHODOLOGY.md).

Кратко: `LOAD_MODE=smoke` (8 VU / 90 с), `constant` (20 VU / 10 мин), `ramp` (лестница +4 VU / 20 с до 80 или fail-ratio ≥ 8%), `full` (core+флот, 24 VU / 10 мин), `heavy` (2 VU / 90 с, редкие POST).

```bash
LOAD_TARGET=public LOAD_MODE=smoke ./scripts/load/run_load_smoke.sh
LOAD_TARGET=public LOAD_MODE=constant ./scripts/load/run_load_smoke.sh
LOAD_TARGET=public LOAD_MODE=ramp ./scripts/load/run_load_smoke.sh
LOAD_TARGET=public LOAD_MODE=full ./scripts/load/run_load_smoke.sh
LOAD_TARGET=public LOAD_MODE=heavy ./scripts/load/run_load_smoke.sh
```

---

## Quick smoke (headless)

Local fleet (`./scripts/deploy_ecosystem.sh` first):

```bash
./scripts/load/run_load_smoke.sh
```

Live public read-only mix (this machine has no local stack):

```bash
LOAD_TARGET=public LOAD_USERS=8 LOAD_DURATION=90s ./scripts/load/run_load_smoke.sh
```

Override users/duration:

```bash
LOAD_USERS=25 LOAD_DURATION=90s ./scripts/load/run_load_smoke.sh
```

Reads tokens from repo `.env` when present (`MESH_API_TOKEN`, `ALIEN_API_TOKEN`, …).
Reports land in `scripts/load/reports/` (gitignored).

## Interactive UI

```bash
pip install -r scripts/load/requirements.txt
locust -f scripts/load/locust_ecosystem.py
# open http://127.0.0.1:8089
```

## Heavy paths (opt-in)

| Env | Effect |
|-----|--------|
| `ARGUS_LOAD_ASK=1` | Adds `POST /ask` (needs `ARGUS_HTTP_TOKEN`; runs the LLM — use low user count) |
| `MESH_API_TOKEN` | Enables `POST /v1/tasks` when `LOAD_MESH_TASKS=1` |
| `LOAD_MESH_TASKS=1` | Include Mesh task creation (otherwise read-only) |
| `ALIEN_API_TOKEN` | Required for `/monitor/api/state` in production |

## After deploy

```bash
./scripts/deploy_ecosystem.sh
./scripts/verify_ecosystem_full.sh
./scripts/load/run_load_smoke.sh
```

KI-3 factory soak (separate, needs a running Factory API):

```bash
./scripts/load_test_factory.sh --base-url http://127.0.0.1:9081 --duration 600 --concurrency 10
```
