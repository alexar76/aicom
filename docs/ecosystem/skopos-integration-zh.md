# SKOPOS — 生态系统集成

**SKOPOS**（[`skopos/`](https://github.com/alexar76/skopos)）是 AICOM 的机群**可观测性卫星** — 通过 SSH 进行 nginx 与 Apache 分析、Security Center、扫描历史，以及一个 AI 分析师。自托管；生产环境推荐 PostgreSQL。

> 🌐 语言： [English](./skopos-integration.md) · [Русский](./skopos-integration-ru.md) · [Español](./skopos-integration-es.md) · [Français](./skopos-integration-fr.md) · **中文**

---

## 实时界面

| 界面 | URL | 角色 |
|------|-----|------|
| **仪表盘** | [skopos.modelmarket.dev](https://skopos.modelmarket.dev) | Streamlit UI（生产环境中密码保护） |
| **公共状态** | `GET /healthz` | 供 Alien Monitor 和探针使用的非机密 JSON |
| **Alien Monitor** | [monitor.modelmarket.dev/](https://monitor.modelmarket.dev/) | 3D 图节点 — 点击 **SKOPOS** 球体 |

---

## Alien Monitor 节点

| Env | 用途 |
|-----|------|
| `ALIEN_SKOPOS_URL` | 轮询 `GET /healthz`（默认 `https://skopos.modelmarket.dev`） |
| `ALIEN_PUBLIC_SKOPOS_URL` | 面板链接 — 仪表盘 URL |
| `ALIEN_SKOPOS_GITHUB_URL` | 面板中的 GitHub 链接（默认 `https://github.com/alexar76/skopos`） |

**health 响应（非机密）：**

```json
{
  "ok": true,
  "service": "skopos",
  "version": "0.1.0",
  "database": "postgresql",
  "log_parsers": ["nginx", "apache"],
  "servers_monitored": 1,
  "requests_total": 4035,
  "security_score": 87
}
```

**图中位置：** Metis 附近的西侧架 (`skopos` @ `-11.5, -3.5, 1.5`)。  
**边：** `factory → skopos`（流量遥测）、`skopos → metis`（主机机群）、`skopos → hub`（生态系统态势）。

点击球体 → **Open SKOPOS dashboard**、GitHub、docs、集成指南。指标显示受监控的服务器、已解析请求总数以及 security score — 无机密信息。

---

## 在 Metis 节点上部署

生产测试栈：[`metis/deploy/skopos-test/`](https://github.com/alexar76/metis/tree/main/deploy/skopos-test/)。

```bash
cd metis/deploy/skopos-test
./remote-sync.sh
```

Nginx vhost `skopos.modelmarket.dev` 位于 [`metis/deploy/nginx.conf`](https://github.com/alexar76/metis/blob/main/deploy/nginx.conf) — 代理 `:8501`（UI）和 `:8502`（`/healthz`）。

TLS（一旦 DNS 指向 Metis 主机）：

```bash
docker run --rm -v /opt/metis/deploy/letsencrypt:/etc/letsencrypt \
  -v /var/www/certbot:/var/www/certbot certbot/certbot certonly --webroot \
  -w /var/www/certbot -d skopos.modelmarket.dev --agree-tos -m you@example.com
docker restart metis-nginx
```

---

## Monorepo 路径

| 路径 | 角色 |
|------|------|
| `skopos/` | 应用源代码 |
| `metis/deploy/skopos-test/` | 用于 Metis 主机的 Docker Compose + `servers.yaml` |
| `alien-monitor/backend/skopos_*.py` | 图节点 + 实时轮询 |
| `docs/ecosystem/skopos-integration.md` | 本文件 |

卫星仓库：[alexar76/skopos](https://github.com/alexar76/skopos) — 通过 `./scripts/publish_all_repos.sh --satellite skopos` 发布。

**Landing：** [skopos.modelmarket.dev](https://skopos.modelmarket.dev)（live）· [alexar76.github.io/skopos](https://alexar76.github.io/skopos/)（GitHub Pages，EN/RU/ES）。源：`skopos/docs/landing/index.html`。Workflow：`skopos/.github/workflows/pages.yml`。

---

## 独立性

SKOPOS 在运行时不需要 Factory、Hub 或 Metis。当 `/healthz` 不可达时，Alien Monitor 会优雅降级（节点显示 `offline`）。

---

## AIMarket 经济（可选的供给侧）

SKOPOS 可以通过 [AIMarket Protocol v2](https://github.com/alexar76/aimarket-protocol/blob/main/spec.md) 向其他 AI 智能体**出售机群情报** — 与 Metis `/aimarket/invoke` 相同的模式。

**默认关闭。** 仅当你希望 SKOPOS 加入联邦智能体经济时才启用：

```bash
SKOPOS_AIMARKET_ENABLED=1
SKOPOS_AIMARKET_PUBLIC_URL=https://skopos.modelmarket.dev
# Optional: protect invoke with API key
SKOPOS_AIMARKET_API_KEY=your-secret
# Optional: auto-register capabilities on Hub at startup
SKOPOS_HUB_URL=https://modelmarket.dev
SKOPOS_AIMARKET_AUTO_REGISTER=1
SKOPOS_AIMARKET_PUBLISH_TOKEN=...
```

| Endpoint | 角色 |
|----------|------|
| `GET /.well-known/ai-market.json` | 发现 |
| `GET /ai-market/v2/manifest` | 能力目录 |
| `POST /aimarket/invoke` | Hub 调用契约 `{input, product_id, capability_id}` → `{result}` |

### 可计费能力

| ID | 出售内容 | ~USD/次调用 |
|----|----------|-----------|
| `skopos.fleet.status@v1` | Heartbeat + security score | $0.01 |
| `skopos.security.posture@v1` | 机群评分、告警、备注 | $0.08 |
| `skopos.traffic.summary@v1` | 24 小时流量聚合 | $0.05 |
| `skopos.briefing@v1` | 人类可读的机群简报（规则 / LLM） | $0.15 |

ARGUS、Factory 或 Alien Monitor 可以在无需 SSH 访问你的机群的情况下**购买**态势上下文。

### 消费方模式（可选）

设置 `SKOPOS_HUB_URL`，使 SKOPOS 能够**发现** Hub 能力（免费搜索）。SKOPOS 向预言机发起的付费调用需要钱包集成（未来）；独立模式会忽略缺失的 Hub。

Metis 上的 Nginx 应为 `/healthz`、`/.well-known/*`、`/ai-market/*` 和 `/aimarket/invoke` 代理 **8502** 端口（见 `metis/deploy/nginx.conf`）。
