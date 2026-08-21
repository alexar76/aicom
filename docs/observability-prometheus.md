# Fleet observability: Prometheus metrics

This guide covers **metrics scrape + Grafana + Skopos Observability** for the
AICOM / AIMarket fleet. Traces (OTel → LangSmith / Tempo) are documented
separately in [`observability-langsmith.md`](./observability-langsmith.md).

## Architecture

| Component | Metrics endpoint | Prometheus job |
|-----------|------------------|----------------|
| AI-Factory | `app:8081/metrics/` | `aicom` |
| AIMarket Hub | `:9083/metrics` | `aimarket-hub` |
| Metis | internal `metis:8080/metrics` (not on public nginx) | `metis` (optional; tunnel required from factory) |
| Skopos UI | reads PromQL over HTTP | — (`SKOPOS_PROMETHEUS_URL`) |

Skopos does **not** replace Grafana. It queries Prometheus for operator KPIs
and a 3D service graph; Grafana keeps heavy dashboards and alerting.

```
Factory / Hub / Metis  →  Prometheus  →  Grafana dashboards
                               ↓
                     Skopos Observability page
```

## Hub metrics

Hub exposes `prometheus_client` gauges/counters:

| Metric | Labels | Meaning |
|--------|--------|---------|
| `aimarket_hub_up` | — | Process is serving `/metrics` |
| `aimarket_hub_invokes_total` | `capability`, `result` | Invoke outcomes (`ok`, `payment_required`, `error`, …) |
| `aimarket_hub_invoke_duration_seconds` | histogram | Invoke latency |
| `aimarket_hub_payment_required_total` | `capability` | HTTP 402 path |

Implementation: `aimarket-hub/aimarket_hub/metrics.py`, mounted at `GET /metrics`.

## Prometheus scrape

Config lives in repo-root [`prometheus.yml`](../prometheus.yml):

```yaml
- job_name: aimarket-hub
  metrics_path: /metrics
  static_configs:
    - targets: ['modelmarket-hub:9083']  # hub on aicom_aicom_net

# Metis /metrics is internal-only — enable when a tunnel exposes :8080:
# - job_name: metis
#   metrics_path: /metrics
#   static_configs:
#     - targets: ['host.docker.internal:18080']
```

Reload / recreate after editing:

```bash
docker compose up -d --force-recreate prometheus
# or: curl -X POST http://127.0.0.1:9090/prometheus/-/reload
```

Check targets: `http://127.0.0.1:9090/prometheus/targets`.

## Grafana dashboards

Bundled under [`grafana/dashboards/`](../grafana/dashboards/):

| File | Purpose |
|------|---------|
| `ai_factory.json` | Factory pipeline / HTTP |
| `factory-iq.json` | Factory IQ |
| `ecosystem-overview.json` | Hub up, invoke RPS, 402, p99, Factory/Metis |
| `hub-invokes.json` | Breakdown by capability / result |

Import (idempotent):

```bash
./scripts/setup_grafana_dashboards.sh
# or full stack helper:
./scripts/deploy_observability.sh
```

Alert rules (Hub down, Hub error rate) live in
[`grafana/alerting/rules.yml`](../grafana/alerting/rules.yml).

## Skopos Observability page

- Page: `skopos/pages/6_Observability.py` (sidebar **Observability**)
- Env: `SKOPOS_PROMETHEUS_URL` — default `http://127.0.0.1:9090/prometheus`
- If Prometheus is unreachable, the UI shows **demo fallback** KPIs/charts so
  local/dev still has a rich APM surface.

Tabs: Overview · Hub · Factory · Mesh/Metis · Service Graph 3D.

## Adding metrics to another service (template)

1. Depend on `prometheus_client`.
2. Expose `GET /metrics` returning `generate_latest()` (or FastAPI
   `Response(content=…, media_type=CONTENT_TYPE_LATEST)`).
3. Export at least `*_up 1` and one RED counter/histogram for your main RPC.
4. Add a scrape job to `prometheus.yml` (docker DNS name or
   `host.docker.internal:PORT`).
5. Optionally set `OTEL_EXPORTER_OTLP_ENDPOINT` for traces (see
   [`observability-langsmith.md`](./observability-langsmith.md) /
   `core/tracing.py`).

Minimal FastAPI sketch:

```python
from fastapi import FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, Gauge, generate_latest

UP = Gauge("myservice_up", "1 if process is up")
UP.set(1)
app = FastAPI()

@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
```

## Deploy checklist (factory host)

1. Sync `prometheus.yml`, Grafana JSON, alerting rules.
2. Recreate Prometheus; import dashboards.
3. Rebuild / recreate Hub so `/metrics` and `prometheus_client` are present
   (preserve `hub-payment.env` / `AIMARKET_SELLS_FOR`).
4. On Metis/Skopos: set `SKOPOS_PROMETHEUS_URL` to a reachable Prometheus
   (VPN, SSH tunnel, or authenticated public path).

## Related

- [`running.md`](./running.md) — ports (Prometheus **9090**, Grafana **9082**)
- [`factory-metrics-reference.md`](./factory-metrics-reference.md) — Factory metric names
- [`ecosystem/skopos-integration.md`](./ecosystem/skopos-integration.md) — Skopos deploy
