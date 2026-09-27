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

**Quién puede leerlo.** `/metrics` nombra cada capacidad que vende el hub, cuántas veces se pagó
o se rechazó cada una, qué familias de clientes MCP lo usan y la latencia de las invocaciones: es
el panel del operador, no una página pública. Por defecto solo responde a quien se conecta
**directamente** desde una dirección de loopback o privada (127.0.0.0/8, 10/8, 172.16/12,
192.168/16, ::1, fc00::/7) y sin cabeceras de reenvío. Prometheus en la red de contenedores pasa;
todo lo que llega por el nginx público recibe `404`, porque nginx añade `X-Forwarded-For` /
`X-Real-IP`.

| Variable | Por defecto | Efecto |
|---|---|---|
| `AIMARKET_METRICS_TOKEN` | sin definir | Un recolector externo lo lee con `Authorization: Bearer <token>`. |
| `AIMARKET_METRICS_PUBLIC` | `0` | `1` lo vuelve a abrir a todos (como antes de 3.7.0). |

La etiqueta `capability` es el id **del catálogo**: una invocación de una capacidad que el hub no
lista cuenta como `capability="unlisted"`, así que los ids inventados no crean series nuevas.

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
