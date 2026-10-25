# Load testing: results of 2026-10-23, before and after

**Languages:** English · [Русский](load-testing.ru.md) · [Español](load-testing.es.md) · [Français](load-testing.fr.md) · [中文](load-testing.zh.md)

What the public fleet does under load, what the money path does under concurrency, what was slow
and why, and what changed. Every number here was measured on 2026-10-23; the commands to repeat
them are at the end.

## What was run

| Test | Tool | Target | Load |
|---|---|---|---|
| Public smoke | Locust 2.46.5, `scripts/load/run_load_smoke.sh` | live fleet (read-only mix) | 8 users, 90 s |
| Public constant | same | live fleet (read-only mix) | 20 users, 10 min |
| Money path | `aimarket-hub/scripts/load_money_path.py` | local hub, SQLite and PostgreSQL | 2,300 requests, 64 at once |
| Factory soak (KI-3) | `scripts/load_test_factory.sh` | local factory backend, 4 uvicorn workers | 10 threads, 15 min |

The public mix reads only: factory health, catalogue and trust strip, the storefront, hub search,
statistics and discovery, mesh, ARGUS, monitor and pulse. It never opens a paid call; the money
path is tested on a local hub instead.

## Public fleet, 20 users for 10 minutes

| | Before | After |
|---|---|---|
| Requests | 7,538 | 7,626 |
| Failures | **0 (0.00%)** | **0 (0.00%)** |
| Median, all requests | 170 ms | 180 ms |
| p95, all requests | 530 ms | 610 ms |

| Request | Before: median / p95 | After: median / p95 | Change |
|---|---|---|---|
| Factory `GET /api/products` (storefront) | 7.3 s / 12 s | **0.22 s / 2.0 s** | 33× faster at the median |
| Factory `GET /api/marketing/trust-metrics` | 4.7 s / 7.8 s | **0.18 s / 0.75 s** | 26× faster at the median |
| Factory `GET /api/health` | 0.18 s / 3.8 s | **0.17 s / 0.43 s** | p95 9× lower |
| Storefront `/` | 0.35 s / 0.38 s | 0.36 s / 0.60 s | — |
| Hub search | 0.34 s / 0.56 s | 0.33 s / 0.65 s | — |
| Hub statistics | 0.17 s / 0.36 s | 0.18 s / 0.45 s | — |
| Hub well-known | 0.33 s / 0.49 s | 0.34 s / 0.67 s | — |
| Hub capital pricing | 0.19 s / 0.39 s | 0.19 s / 0.46 s | — |
| Mesh, ARGUS, Pulse | 0.16–0.17 s / ≤ 0.18 s | 0.17 s / 0.24–0.40 s | — |
| Monitor `/api/health` | 0.16 s / 4.3 s | 0.17 s / 1.8 s | **deployed 2026-10-23** (below) |
| Monitor state | 0.17 s / 3.0 s | 0.19 s / 2.4 s, max 62 s | **deployed 2026-10-23** (below) |

"Before" ran right after the review fixes went live, "after" after the optimizations below. Rows
marked "—" had nothing changed; their spread is the laptop's network between the two runs.

### The 8-user smoke

| | Before | After |
|---|---|---|
| Requests / failures | 477 / 0 | 477 / 0 |
| Mean response | 306 ms | 253 ms |
| Factory storefront, median | 5.1 s | 0.19 s |
| Factory trust strip, median | 4.6 s | 0.18 s |
| Slowest request | 5.1 s | 2.4 s (monitor) |

### The server during the 20-user run

| | Before | After |
|---|---|---|
| Pipeline worker CPU (idle queue) | ~89% of a core | **16%** |
| Factory API CPU | 85–196% | — |
| Hub CPU / memory | 0–55% / 0.1 GB | — |
| Load average (factory-vps) | 2.1–3.6 | — |
| Restarts, limiter blocks, factory tracebacks | 0 / 0 / 0 | 0 / 0 / 0 |

### Monitor, before and after its deploy

Deployed to monitor.modelmarket.dev at 09:21 UTC (image `alien-monitor:overlaythread-20261023-alien-monitor-live`,
the running image plus the new `main.py`). The same probe before and after: 20 clients, each about one
`GET /api/health` a second for 90 seconds, from the same laptop. The median is mostly a new TLS connection per request.

| | Before | After |
|---|---|---|
| Requests / failures | 960 / 0 | 1,060 / 0 |
| Median | 685 ms | 666 ms |
| p95 | 1,844 ms | **1,147 ms** |
| p99 | 4,185 ms | **1,272 ms** |
| Slowest | 4,330 ms | **1,369 ms** |

## Money path on a local hub

Paid calls from many accounts, each paid call retried three times at once under one
`Idempotency-Key`, and signups racing for a $0.25 grant budget; then an audit of the ledger.

| Database | Requests | Concurrent | Throughput | p95 | Ledger after the run |
|---|---|---|---|---|---|
| SQLite | 2,300 | 64 | 80 req/s | 2.3 s | every invariant holds; 100 keyed groups charged once each; grants stop at $0.25 |
| PostgreSQL 18 | 2,299 | 64 | 41 req/s | 4.3 s | the same; one dropped connection, which the audit shows was not charged |

The invariants: an account's held amount equals the sum of its held holds (and is zero after the
run), no money is created or lost, and each keyed group is charged exactly once.

## Factory backend with 4 workers (KI-3)

| | Before the fix | After the fix |
|---|---|---|
| Requests in 15 min | 25,577 | 33,710 |
| `/api/health` refused by the app's own limiter | **13,779 of 17,907** | **0 of 23,542** |
| Failures (no answer or 5xx) | 0 | 0 |
| Worker restarts | 0 | 0 |
| Memory of the 4 workers | — | 480 → 435 MB, stable |

The supervisor kills the backend after five failed health probes in a row. The limiter used to
count the probe and refuse it under load, so a busy backend was killed for being busy.

## What was slow, and what changed

| Where | Cause, measured | Change |
|---|---|---|
| Pipeline worker | 92% of its CPU in `yaml.safe_load`: the config was re-parsed for every product on every cycle (py-spy, live process) | parse reused while no config file changes (mtime, size, inode) |
| Storefront `/api/products` | 57 demo assessments for 19 products, each walking the product tree including `node_modules`: 5.1 s of 5.4 s | walk prunes vendor trees; one assessment per product per request; built grid reused 30 s and rebuilt at once when the pipeline writes |
| Trust strip | 4 s spent loading all 3,510 tasks the factory ever ran, to count product states | products-only read (0.4 ms); cached a minute; built off the event loop |
| Factory `/api/health` | event loop blocked behind the trust strip | the work moved to a thread |
| KI-3 supervisor | health probe counted and refused by the per-address limiter | probe unmetered; 403/429 read as alive |
| Monitor | 17 satellite polls with blocking HTTP clients on the event loop | one worker thread; **deployed 2026-10-23** |
| Hub logs | 311 tracebacks a day from ACEX ledgers that are off by configuration | one warning per ledger; same 503 answers |
| Director | one empty model answer threw away a whole discovery cycle | an enrichment that fails stays empty |

## Repeat it

```bash
LOAD_TARGET=public LOAD_MODE=smoke ./scripts/load/run_load_smoke.sh
LOAD_TARGET=public LOAD_MODE=constant ./scripts/load/run_load_smoke.sh
python aimarket-hub/scripts/load_money_path.py --invokes 2000 --concurrency 64
python aimarket-hub/scripts/load_money_path.py --invokes 2000 --concurrency 64 --database-url postgresql:///scratch_db
./scripts/load_test_factory.sh --base-url http://127.0.0.1:9081 --duration 900 --concurrency 10
```

The PostgreSQL run wipes the schema of the database it is given. The method, modes and pass
criteria: [`scripts/load/METHODOLOGY.md`](../scripts/load/METHODOLOGY.md). Earlier runs:
[`scripts/load/RESULTS-2026-09-14.md`](../scripts/load/RESULTS-2026-09-14.md).
