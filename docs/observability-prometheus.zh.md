# 集群可观测性：Prometheus 指标

AICOM / AIMarket 集群的 **指标抓取 + Grafana + Skopos Observability** 指南。
链路追踪（OTel → LangSmith / Tempo）见 [`observability-langsmith.md`](./observability-langsmith.md)。

## 架构

| 组件 | Endpoint | Prometheus job |
|------|----------|----------------|
| AI-Factory | `app:8081/metrics/` | `aicom` |
| AIMarket Hub | `:9083/metrics` | `aimarket-hub` |
| Metis | 内部 `metis:8080/metrics`（不经公网 nginx） | `metis`（可选；需从 factory 建隧道） |
| Skopos UI | 通过 HTTP 查询 PromQL | —（`SKOPOS_PROMETHEUS_URL`） |

Skopos **不**替代 Grafana：它用 Prometheus 拉 KPI 与三维服务图；Grafana 负责重型看板与告警。

## Hub 指标

| 指标 | Labels | 含义 |
|------|--------|------|
| `aimarket_hub_up` | — | 进程提供 `/metrics` |
| `aimarket_hub_invokes_total` | `capability`, `result` | invoke 结果 |
| `aimarket_hub_invoke_duration_seconds` | histogram | 延迟 |
| `aimarket_hub_payment_required_total` | `capability` | HTTP 402 路径 |

实现：`aimarket-hub/aimarket_hub/metrics.py`。

## 抓取

配置：[`prometheus.yml`](../prometheus.yml)。Prometheus 需要
`extra_hosts: host.docker.internal:host-gateway` 才能抓取宿主机上的 Hub。

```bash
docker compose up -d --force-recreate prometheus
```

Targets：`http://127.0.0.1:9090/prometheus/targets`。

## Grafana

看板位于 [`grafana/dashboards/`](../grafana/dashboards/)：
`ecosystem-overview.json`、`hub-invokes.json`。
导入：`./scripts/setup_grafana_dashboards.sh`。
告警：[`grafana/alerting/rules.yml`](../grafana/alerting/rules.yml)。

## Skopos Observability

- 页面：`skopos/pages/6_Observability.py`
- 环境变量：`SKOPOS_PROMETHEUS_URL`（默认 `http://127.0.0.1:9090/prometheus`）
- Prometheus 不可达时使用 **演示回退数据**。

## 为其他服务添加指标（模板）

1. 依赖 `prometheus_client`，暴露 `GET /metrics`
2. 至少提供 `*_up` 与主 RPC 的 RED 计数器
3. 在 `prometheus.yml` 增加 job
4. 可选：`OTEL_EXPORTER_OTLP_ENDPOINT`

## 部署清单

1. 更新 `prometheus.yml` / Grafana JSON / alerting
2. 重建 Prometheus 并导入看板
3. 重建 Hub（含 `prometheus_client`，保留 `hub-payment.env`）
4. 在 Skopos 上配置可达的 `SKOPOS_PROMETHEUS_URL`
