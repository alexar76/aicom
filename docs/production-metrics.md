# Production metrics

Public SLO-style numbers for the live demo fleet. Prefer the **live JSON API**; the snapshot below is refreshed by CI or `./scripts/collect_production_metrics.py`.

## Live API

```bash
curl -s https://magic-ai-factory.com/api/public/ecosystem-status | jq .
```

| Field | Meaning |
|-------|---------|
| `slo.rps_1h` | Hub invokes in the last hour ÷ 3600 |
| `slo.p50_latency_ms_24h` / `p95_latency_ms_24h` | Hub invoke latency percentiles (24h window) |
| `slo.success_rate_24h` | Successful invokes ÷ total invokes (24h) |
| `services.*.uptime_seconds` | Process uptime since last restart |
| `pipeline.*` | Factory catalog counts (`pipeline.db`) |
| `incidents` | Operator log — [`production-incidents.json`](./production-incidents.json) |

**Hub source:** `GET https://modelmarket.dev/ai-market/v2/stats/live` (public).  
**Factory heartbeat:** `GET /api/public/pipeline-status` (homepage banner uses the same endpoint).  
**Internal detail:** Prometheus `/metrics` on `:9081` (not public) — see [`factory-metrics-reference.md`](./factory-metrics-reference.md).

## Snapshot (last collect)

> Generated: **2026-06-25** from `modelmarket.dev` + `magic-ai-factory.com`.  
> Refresh: `python3 scripts/collect_production_metrics.py`

| Metric | Value | Notes |
|--------|------:|-------|
| Hub status | ok | `https://modelmarket.dev` |
| Factory status | ok | `https://magic-ai-factory.com` |
| Hub invocations (all time) | 136,197 | Includes demo-seeder traffic |
| Hub success rate (all time) | 100% | |
| Hub avg latency | 34.7 ms | All-time mean |
| Hub capabilities | 23 (11 federated) | 3 federation peers |
| Settled volume | $105,758 | Channel ledger aggregate |
| RPS (1h) | ~0 | No invokes in the last hour at collect time |
| Products in pipeline | 19 | From public pipeline-status |
| Products shipped | 2 | |
| Open incidents | 0 | See incident log |

### Incidents

Maintained in [`production-incidents.json`](./production-incidents.json). Add a row when users are affected; set `status` to `resolved` with `resolved_at` when closed.

| ID | Severity | Status | Summary |
|----|----------|--------|---------|
| `2026-06-07-hub-demo-traffic` | low | resolved | Demo seeder burst; no user impact |

## Aliases

| Surface | URL |
|---------|-----|
| Alien Monitor (3D) | [magic-ai-factory.com/monitor/](https://magic-ai-factory.com/monitor/) — LIVE/UNI modes poll the same hub + factory APIs |
| Hub live ticker | [modelmarket.dev/live](https://modelmarket.dev/live) |
| Ecosystem landing | [modeldev.modelmarket.dev](https://modeldev.modelmarket.dev) — metrics bar (live fetch) |

## Operator refresh

```bash
# After deploy — update committed snapshot for docs/README
python3 scripts/collect_production_metrics.py

# Or print without writing
python3 scripts/collect_production_metrics.py --stdout | jq .slo
```

Deploy note: `GET /ai-market/v2/health` and windowed hub aggregates (`invocations_24h`, `rps_1h`) ship with the hub image from this repo; until redeploy, the Factory API backfills 24h SLO fields from `stats/live` events when possible.
