# Alien Monitor — Factory 产品星团

> **English:** [alien-monitor-factory-catalog.md](./alien-monitor-factory-catalog.md) · **Русский:** [alien-monitor-factory-catalog.ru.md](./alien-monitor-factory-catalog.ru.md) · **Español:** [alien-monitor-factory-catalog.es.md](./alien-monitor-factory-catalog.es.md) · **Français:** [alien-monitor-factory-catalog.fr.md](./alien-monitor-factory-catalog.fr.md) · **中文**

真实的 AI-Factory 产品如何在 UNI / LIVE 模式下，作为 Factory 节点附近的**橙色星团**显示。

---

## UNI 模式下应显示产品吗？

**应该。** `ALIEN_MODE=universe` 并非 TEST 模拟：

| 模式 | 3D 地图上的 Factory 产品 |
|------|--------------------------|
| **TEST** | 否 — Factory 上仅有一个模拟计数器 |
| **UNIVERSE (UNI)** | **是** — 从 `GET /api/products` 同步 |
| **LIVE (real)** | **是** — 相同目录 + 生产 RPC |

UNI 运行本地 Anvil，**并**实时轮询 Factory / Hub / Mesh / Prometheus。目录同步在启动（bootstrap）时运行，此后约每 60 秒一次（`ALIEN_FACTORY_SYNC_TICKS`，默认 40 个 tick）。

只有**在 storefront 上架的**产品才会显示（与公开商店相同的门槛），而非所有流水线状态。

---

## 配置

| 变量 | 默认值（prod） | 作用 |
|------|----------------|------|
| `AICOM_API_URL` | `http://127.0.0.1:9081` | Factory API 基址（prod 上为 host 网络） |
| `ALIEN_FACTORY_API_TIMEOUT` | `30` | HTTP 超时 — `/api/products` 可能耗时 12–30 秒 |
| `ALIEN_MODE` | `universe` | `.env` 中只放一个值 — 避免重复行 |

生产 compose `alien-monitor/docker-compose.prod.yml` 使用 **`network_mode: host`**，因此 `127.0.0.1:9081` 是正确的。

---

## 星团为何消失

1. **API 超时（最常见）** — Monitor 曾使用 8 秒超时；Factory 的 `/api/products` 往往更慢 → 目录为空 → 所有星团被移除。**已修复：** 抓取失败返回 `None` → **保留现有星团**；默认超时 25–30 秒。
2. **切换到 TEST 模式** — 无目录同步。
3. **合理的空目录** — 严格 QA 将所有产品从 storefront 隐藏（`200` + `[]`）。按设计移除星团。

---

## 验证

```bash
curl -s --max-time 45 http://127.0.0.1:9081/api/products | jq '.products | length'
curl -s http://127.0.0.1:9100/api/state | jq '[.nodes[] | select(.group=="cluster")] | length'
docker logs alien-monitor 2>&1 | grep -i 'factory catalog' | tail -5
```

启动（bootstrap）时应出现提示：`factory catalog: +N products`。

---

## 相关

- [alien-monitor/README.md](https://github.com/alexar76/alien-monitor/blob/main/README.md) — 部署
- [uni-troubleshooting.md](./uni-troubleshooting.md) §16 — 扩展排障
- [funnel-growth.zh.md](./funnel-growth.zh.md) — 公开 lead → 流水线（Factory 侧）
