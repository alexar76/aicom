# Наблюдаемость флота: метрики Prometheus

Гид по **scrape метрик + Grafana + Skopos Observability** для флота AICOM / AIMarket.
Трейсы (OTel → LangSmith / Tempo) — отдельно в [`observability-langsmith.md`](./observability-langsmith.md).

## Архитектура

| Компонент | Endpoint | Job Prometheus |
|-----------|----------|----------------|
| AI-Factory | `app:8081/metrics/` | `aicom` |
| AIMarket Hub | `:9083/metrics` | `aimarket-hub` |
| Metis | internal `metis:8080/metrics` (не через публичный nginx) | `metis` (опционально; нужен tunnel с factory) |
| Skopos UI | PromQL по HTTP | — (`SKOPOS_PROMETHEUS_URL`) |

Skopos **не** заменяет Grafana: читает Prometheus для KPI и 3D-графа; Grafana — тяжёлые дашборды и алерты.

## Метрики Hub

| Метрика | Labels | Смысл |
|---------|--------|--------|
| `aimarket_hub_up` | — | Процесс отдаёт `/metrics` |
| `aimarket_hub_invokes_total` | `capability`, `result` | Исходы invoke |
| `aimarket_hub_invoke_duration_seconds` | histogram | Латентность |
| `aimarket_hub_payment_required_total` | `capability` | Путь HTTP 402 |

Код: `aimarket-hub/aimarket_hub/metrics.py`.

**Кто может читать.** В `/metrics` видно каждую способность, которую продаёт хаб, сколько раз
её оплатили или отклонили, какие семейства MCP-клиентов к нему ходят и задержку вызовов — это
панель оператора, а не публичная страница. По умолчанию ответ получает только тот, кто
подключается **напрямую** с loopback- или частного адреса (127.0.0.0/8, 10/8, 172.16/12,
192.168/16, ::1, fc00::/7) и без заголовков проксирования. Prometheus из сети контейнеров
проходит; всё, что приходит через публичный nginx, получает `404`, потому что nginx добавляет
`X-Forwarded-For` / `X-Real-IP`.

| Переменная | По умолчанию | Действие |
|---|---|---|
| `AIMARKET_METRICS_TOKEN` | не задана | Внешний сборщик читает с `Authorization: Bearer <токен>`. |
| `AIMARKET_METRICS_PUBLIC` | `0` | `1` снова открывает всем (как до 3.7.0). |

Метка `capability` — это id **из каталога**: вызов способности, которой в каталоге нет,
считается как `capability="unlisted"`, так что выдуманные id не создают новых рядов.

## Scrape

Конфиг: [`prometheus.yml`](../prometheus.yml). Prometheus нужен
`extra_hosts: host.docker.internal:host-gateway` для Hub на хосте.

```bash
docker compose up -d --force-recreate prometheus
```

Targets: `http://127.0.0.1:9090/prometheus/targets`.

## Grafana

Дашборды в [`grafana/dashboards/`](../grafana/dashboards/): `ecosystem-overview.json`,
`hub-invokes.json` (+ factory). Импорт: `./scripts/setup_grafana_dashboards.sh`.
Алерты: [`grafana/alerting/rules.yml`](../grafana/alerting/rules.yml).

## Skopos Observability

- Страница: `skopos/pages/6_Observability.py`
- Env: `SKOPOS_PROMETHEUS_URL` (по умолчанию `http://127.0.0.1:9090/prometheus`)
- При недоступности Prometheus — демо-данные, UI не пустой.

## Шаблон для нового сервиса

1. `prometheus_client` + `GET /metrics`
2. Хотя бы `*_up` и RED-счётчик основного RPC
3. Job в `prometheus.yml`
4. Опционально `OTEL_EXPORTER_OTLP_ENDPOINT` (см. langsmith-гайд)

## Чеклист деплоя

1. Обновить `prometheus.yml` / Grafana JSON / alerting
2. Recreate Prometheus, импорт дашбордов
3. Rebuild Hub с `prometheus_client` (сохранить `hub-payment.env`)
4. На Skopos: reachable `SKOPOS_PROMETHEUS_URL`
