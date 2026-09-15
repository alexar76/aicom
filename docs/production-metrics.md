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

## How to read these numbers

Three rules, because getting them wrong has already produced a two-orders-of-magnitude error in
this file (see [Counter resets](#counter-resets)):

1. **"All time" means "since the hub's counters were last reset."** The hub keeps its event log in
   its own store; a redeploy that replaces that store restarts every all-time counter from zero.
   These are *not* lifetime-of-project totals.
2. **Volume figures are ledger aggregates, not revenue.** `settled_volume_usd` is the sum of every
   channel the ledger has closed, including channels that **expired and refunded**. The subset that
   actually moved money to a provider is `settled_only_volume_usd`. Quote that one when the question
   is "how much have you earned".
3. **Invocation counts can include our own traffic.** Demo seeders, self-tests and satellite
   heartbeats all land in the same counter. `stats/live` tags each event with a `traffic_class`;
   use it before citing a total anywhere external.

**Never quote a number from the snapshot table below without checking it against the live API
first** — the snapshot is a committed convenience copy and goes stale between collects. Anything
external-facing (investor material, grant applications, landing copy) must come from the live call.

## Snapshot (last collect)

> Generated: **2026-08-27 19:34 UTC** from `modelmarket.dev` + `magic-ai-factory.com`.  
> Refresh: `python3 scripts/collect_production_metrics.py`

| Metric | Value | Notes |
|--------|------:|-------|
| Hub status | ok | `https://modelmarket.dev` |
| Factory status | ok | `https://magic-ai-factory.com` |
| Hub invocations (since last counter reset) | 451 | Includes our own demo/self-test traffic |
| Hub invocations (24h) | 108 | |
| Hub success rate | 93.6% all time · 99.1% (24h) | |
| Hub latency | p50 2,817 ms · p95 8,817 ms (24h) | Federated calls hit live satellites |
| Hub avg price per call | $0.0033 | |
| Hub capabilities | 106 (94 federated, 12 demo) | 9 federation peers |
| Channel ledger volume | $1.38 total | Of which **$0.04 settled to a provider**, $1.34 expired and refunded |
| Open channels | 0 | |
| RPS (1h) | ~0 | No invokes in the last hour at collect time |
| Products in pipeline | 16 | From public pipeline-status |
| Products shipped | 4 | |
| Open incidents | 0 | See incident log |

### Counter resets

| Date | What happened | Effect on this file |
|------|---------------|---------------------|
| ≤ 2026-06-25 | Snapshot recorded 136,197 invocations and $105,758 "settled volume" | Both were wrong to publish as-is: the invocation count was dominated by a demo seeder, and the volume figure was a channel-ledger aggregate that included simulated (UNI/anvil) channels and expired refunds. |
| between 2026-06-25 and 2026-08-27 | Hub redeployed; event store replaced | All-time counters restarted from zero. The 2026-08-27 collect reads 451 invocations and $1.38 of ledger volume. |

The gap between those two rows is not a regression in traffic — it is a counter reset plus the
removal of inflated figures. Add a row here whenever a deploy resets the hub's event store, so the
next person reading a drop of two orders of magnitude does not diagnose an outage.

### Incidents

Maintained in [`production-incidents.json`](./production-incidents.json). Add a row when users are affected; set `status` to `resolved` with `resolved_at` when closed.

| ID | Severity | Status | Summary |
|----|----------|--------|---------|
| `2026-06-07-hub-demo-traffic` | low | resolved | Demo seeder burst; no user impact |

## Aliases

| Surface | URL |
|---------|-----|
| Alien Monitor (3D) | [monitor.modelmarket.dev/](https://monitor.modelmarket.dev/) — LIVE/UNI modes poll the same hub + factory APIs |
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
