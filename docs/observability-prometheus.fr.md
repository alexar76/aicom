# Observabilité de flotte : métriques Prometheus

Guide **scrape métriques + Grafana + Skopos Observability** pour la flotte AICOM / AIMarket.
Traces OTel : [`observability-langsmith.md`](./observability-langsmith.md).

## Architecture

| Composant | Endpoint | Job Prometheus |
|-----------|----------|----------------|
| AI-Factory | `app:8081/metrics/` | `aicom` |
| AIMarket Hub | `:9083/metrics` | `aimarket-hub` |
| Metis | interne `metis:8080/metrics` (pas sur nginx public) | `metis` (optionnel ; tunnel depuis factory) |
| Skopos UI | PromQL HTTP | — (`SKOPOS_PROMETHEUS_URL`) |

Skopos **ne** remplace **pas** Grafana : il lit Prometheus pour les KPI et le graphe 3D ; Grafana garde les dashboards lourds et l’alerting.

## Métriques Hub

| Métrique | Labels | Sens |
|----------|--------|------|
| `aimarket_hub_up` | — | Le process sert `/metrics` |
| `aimarket_hub_invokes_total` | `capability`, `result` | Résultats d’invoke |
| `aimarket_hub_invoke_duration_seconds` | histogram | Latence |
| `aimarket_hub_payment_required_total` | `capability` | Chemin HTTP 402 |

Code : `aimarket-hub/aimarket_hub/metrics.py`.

## Scrape

Config : [`prometheus.yml`](../prometheus.yml). Prometheus a besoin de
`extra_hosts: host.docker.internal:host-gateway` pour le Hub sur l’hôte.

```bash
docker compose up -d --force-recreate prometheus
```

Targets : `http://127.0.0.1:9090/prometheus/targets`.

## Grafana

Dashboards dans [`grafana/dashboards/`](../grafana/dashboards/) :
`ecosystem-overview.json`, `hub-invokes.json`.
Import : `./scripts/setup_grafana_dashboards.sh`.
Alertes : [`grafana/alerting/rules.yml`](../grafana/alerting/rules.yml).

## Skopos Observability

- Page : `skopos/pages/6_Observability.py`
- Env : `SKOPOS_PROMETHEUS_URL` (défaut `http://127.0.0.1:9090/prometheus`)
- Si Prometheus est injoignable → **données démo**.

## Modèle pour un autre service

1. `prometheus_client` + `GET /metrics`
2. Au minimum `*_up` et un compteur RED du RPC principal
3. Job dans `prometheus.yml`
4. Optionnel : `OTEL_EXPORTER_OTLP_ENDPOINT`

## Checklist de déploiement

1. Mettre à jour `prometheus.yml` / JSON Grafana / alerting
2. Recreate Prometheus, importer les dashboards
3. Rebuild Hub avec `prometheus_client` (garder `hub-payment.env`)
4. Sur Skopos : `SKOPOS_PROMETHEUS_URL` joignable
