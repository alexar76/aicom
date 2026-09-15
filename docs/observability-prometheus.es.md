# Observabilidad de flota: métricas Prometheus

Guía de **scrape de métricas + Grafana + Skopos Observability** para el fleet AICOM / AIMarket.
Trazas OTel: [`observability-langsmith.md`](./observability-langsmith.md).

## Arquitectura

| Componente | Endpoint | Job Prometheus |
|------------|----------|----------------|
| AI-Factory | `app:8081/metrics/` | `aicom` |
| AIMarket Hub | `:9083/metrics` | `aimarket-hub` |
| Metis | interno `metis:8080/metrics` (no en nginx público) | `metis` (opcional; tunnel desde factory) |
| Skopos UI | PromQL por HTTP | — (`SKOPOS_PROMETHEUS_URL`) |

Skopos **no** sustituye Grafana: consulta Prometheus para KPI y el grafo 3D; Grafana conserva dashboards pesados y alertas.

## Métricas Hub

| Métrica | Labels | Significado |
|---------|--------|-------------|
| `aimarket_hub_up` | — | El proceso sirve `/metrics` |
| `aimarket_hub_invokes_total` | `capability`, `result` | Resultados de invoke |
| `aimarket_hub_invoke_duration_seconds` | histogram | Latencia |
| `aimarket_hub_payment_required_total` | `capability` | Ruta HTTP 402 |

Código: `aimarket-hub/aimarket_hub/metrics.py`.

## Scrape

Config: [`prometheus.yml`](../prometheus.yml). Prometheus necesita
`extra_hosts: host.docker.internal:host-gateway` para el Hub en el host.

```bash
docker compose up -d --force-recreate prometheus
```

Targets: `http://127.0.0.1:9090/prometheus/targets`.

## Grafana

Dashboards en [`grafana/dashboards/`](../grafana/dashboards/): `ecosystem-overview.json`,
`hub-invokes.json`. Import: `./scripts/setup_grafana_dashboards.sh`.
Alertas: [`grafana/alerting/rules.yml`](../grafana/alerting/rules.yml).

## Skopos Observability

- Página: `skopos/pages/6_Observability.py`
- Env: `SKOPOS_PROMETHEUS_URL` (default `http://127.0.0.1:9090/prometheus`)
- Si Prometheus no responde, hay **demo fallback**.

## Plantilla para otro servicio

1. `prometheus_client` + `GET /metrics`
2. Al menos `*_up` y un contador RED del RPC principal
3. Job en `prometheus.yml`
4. Opcional: `OTEL_EXPORTER_OTLP_ENDPOINT`

## Checklist de despliegue

1. Actualizar `prometheus.yml` / JSON Grafana / alerting
2. Recreate Prometheus e importar dashboards
3. Rebuild Hub con `prometheus_client` (conservar `hub-payment.env`)
4. En Skopos: `SKOPOS_PROMETHEUS_URL` alcanzable
