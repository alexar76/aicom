# 部署整个生态系统 — 从零开始的快速上手

一份分层的 runbook，用于在一台裸机 Ubuntu VPS 上搭建完整的公开生态系统。它封装了
现有的部署脚本 — 它 **不会** 引入新的部署引擎。从你需要的层级开始，并就此停下；
每个层级都建立在前一个层级之上。

要获取运维级参考（部分重新部署、Hub 重新部署的隐患、精确的手动步骤顺序），
请参见 **[`deploy-ecosystem.md`](./deploy-ecosystem.md)**。

---

## 1. “生态系统”指的是什么

| 组件 | 它做什么 | 容器 / 进程 |
|-----------|--------------|---------------------|
| **Factory** | 构建并交付 AI 产品（`aicom-app` Compose 栈） | `aicom-app-1` |
| **Hub** | AIMarket Protocol v2 联邦枢纽（Hub）— 发现、通道、invoke、结算 | `modelmarket-hub` |
| **Mesh** | 将产品互相接线的服务网格 API | `aicom-mesh-api` |
| **ARGUS-3** | 个人智能体 + WARDEN MCP 防火墙（参考客户端） | `argus` / `:8787` |
| **Alien Monitor** | 3D 生态系统可视化器（UNIVERSE / TEST / REAL 模式）+ **Pulse** 终端 | `alien-monitor`, Pulse |
| **Lottery relayer** | 用于实时 Monitor 数据流的 UNI 模式 relayer（可选；该步骤可能 WARN） | `:9195` |
| **Ecosystem landing** | 位于 [modeldev.modelmarket.dev](https://modeldev.modelmarket.dev) 的公开地图 | nginx 静态 / 步骤 7 |
| **Oracles** | 位于 [oracles.modelmarket.dev](https://oracles.modelmarket.dev) 上的十七个可验证数学预言机（+ Platon UMBRAL cave） | **独立主机（L4）** |
| **On-chain**（可选） | Base 主网合约：Escrow、能力 NFT、Agent Lottery | Foundry 部署 |

**不在 `deploy_ecosystem.sh` 中的：** Metis、DIOSCURI、HELIOS — 需要时单独运行；参见 [§一台 VPS 不包含什么](#9-一台-vps-不包含什么)。

上手层级：

| 层级 | 目标 | 一条命令 |
|-------|------|-------------|
| **L1** | 在本地试用（仅 Factory） | `./scripts/quickstart.sh` |
| **L2** | 在一台 VPS 上自托管 **核心舰队（core fleet）** | `./scripts/quickstart_ecosystem.sh`（preflight 包装器）或 `./scripts/deploy_ecosystem.sh` |
| **L3** | 生产环境公开（DNS + TLS + 验证） | `./scripts/quickstart_ecosystem.sh --public-url https://…` |
| **L4** | 预言机主机（默认 **独立机器**） | `./scripts/setup-oracles-platon-on-host.sh` |

*消费* Hub 的认证模型是 **Ed25519**（SDK 对每次 invoke 签名；钱包密钥是一个 32 字节的
Ed25519 种子，而非以太坊密钥）。secp256k1/EIP-712 是可选的，仅用于链上通道扣款。
消费方相关请参见 [AIMarket SDK 文档](https://github.com/alexar76/aimarket-sdks/blob/main/docs/en.md) 和
[Python agent](https://github.com/alexar76/aimarket-agent/blob/main/docs/en.md)（无状态，无钱包）。

---

## 2. 前置条件

在目标 Ubuntu VPS 上，任何层级之前：

- **Docker Engine + Compose v2**（`docker compose`，而非老旧的 `docker-compose`）。
- **nginx** — TLS 终结与反向代理（层级 3–4）。
- **DNS A/AAAA 记录** 指向你运行所在的主机（层级 3+）：
  - `magic-ai-factory.com`、`www.magic-ai-factory.com` → Factory 主机
  - `modelmarket.dev`、`www.modelmarket.dev` → Factory 主机
  - `oracles.modelmarket.dev` → **预言机主机**（`78.17.126.214`），直接指向（不经 factory 代理）
- **仓库根目录中一个已填写的 `.env`**。复制 `.env.example` 并至少设置一个 LLM 密钥：

```bash
cp .env.example .env
# 然后设置，例如：
#   DEEPSEEK_API_KEY=...
#   ANTHROPIC_API_KEY=...
# 可选的端口覆盖：
#   AICOM_PORT_FRONTEND=9080
#   AICOM_PORT_API=9081
```

相对于内联的 `environment:` 条目，更推荐对 LLM 密钥使用文件形式的 secret
（`data/secrets/llm/<provider>_api_key` + `docker-compose.secrets.yml` overlay）— 参见
`.env.example` 中的注释。

---

## 3. 层级 1 — 在本地试用

仅 Factory。构建镜像、运行栈，并端到端地把一个演示产品入队：

```bash
./scripts/quickstart.sh                      # build + run + landing demo
./scripts/quickstart.sh --no-build           # reuse the existing image
./scripts/quickstart.sh "Your product idea"  # full_software profile from your idea
```

它做了什么：`./run.sh`（构建）→ 运行 → `./demo.sh --no-open`（把一个演示产品入队）。
在 `http://localhost:9080` 的 **Admin → Pipeline** 中观察进度。一个无需 Docker 的样例构建
回放位于 `docs/sample-output/build-replay-spliteasy.json`。

---

## 4. 层级 2 — 自托管核心舰队（一台 VPS）

**推荐的包装器**（Docker preflight + `.env` 检查 + 部署 + 后续步骤）：

```bash
./scripts/quickstart_ecosystem.sh
./scripts/quickstart_ecosystem.sh --skip-verify          # faster; not for prod
./scripts/quickstart_ecosystem.sh --public-url https://…   # forwarded to deploy engine
```

该包装器调用 **`scripts/deploy_ecosystem.sh`** — 即权威来源。你也可以直接调用它：

```bash
./scripts/deploy_ecosystem.sh
```

脚本按以下固定顺序运行：

1. **Factory** — `./scripts/deploy.sh`（`aicom-app-1`）
2. **Hub** — `./scripts/deploy_hub.sh`（`modelmarket-hub`，**绝不** 使用子文件夹的 Compose）
3. **Mesh** — `./scripts/deploy_mesh.sh`（`aicom-mesh-api`）
4. **ARGUS-3** — `./scripts/deploy_argus.sh`（`:8787`）
5. **Alien Monitor + Pulse** — `./scripts/deploy_alien_monitor.sh`
6. **UNI lottery relayer** — `./scripts/deploy_lottery_uni.sh`（非致命；失败则记录一条 WARN）
7. **Ecosystem landing** — `./scripts/deploy_ecosystem_landing.sh`（非致命；`modeldev.modelmarket.dev`）

随后它会 **预热** Factory API（`/api/health`、`/api/products`），并运行
`./scripts/verify_ecosystem_full.sh`（**17+ 项冒烟检查**），除非你传入 `--skip-verify`。

### 端口（宿主机）

| 服务 | 宿主机端口 | 健康检查 / 入口 |
|---------|-----------|----------------|
| Factory API | `:9081` | `GET /api/health` |
| Factory UI（前端） | `:9080` | `GET /` |
| Hub | `:9083` | `GET /.well-known/ai-market.json` |
| Mesh | `:8090` | `GET /v1/stats` |
| ARGUS | `:8787` | `GET /health` |
| Alien Monitor | `:9100` | `GET /api/health` |
| Pulse 终端 | `:5199` | `GET /` |
| UNI lottery relayer | `:9195` | `GET /healthz` |
| Ecosystem landing | nginx vhost | `https://modeldev.modelmarket.dev/`（在 L3 TLS 之后） |

> **公开 UI 端口是 `:9080`，而非旧的 `:8080`。** nginx 将公开域名代理到
> `127.0.0.1:9080`。

标志：

```bash
./scripts/deploy_ecosystem.sh --skip-verify   # faster; skips the smoke suite (not for prod)
```

---

## 5. 层级 3 — 生产环境公开

### 5.1 指向 DNS

`magic-ai-factory.com`、`www.magic-ai-factory.com`、`modelmarket.dev` 和
`www.modelmarket.dev` 的 A/AAAA 记录必须在 **签发证书之前** 解析到本主机。

### 5.2 部署时把公开 URL 烘焙进去

```bash
./scripts/deploy_ecosystem.sh --public-url https://magic-ai-factory.com
```

`--public-url` 会被转发给 `deploy.sh`，以便为 Next.js 构建设置 `NEXT_PUBLIC_SITE_URL`
（Open Graph、sitemap、服务端元数据）。如果 TLS 尚未就绪，你可以先使用
`http://magic-ai-factory.com`，等 HTTPS 上线后再重新构建 app 镜像。

### 5.3 TLS 一次性脚本（以 root 运行）

**Hub vhost + AIMarket Hub + Let's Encrypt**，用于 `modelmarket.dev`：

```bash
sudo CERTBOT_EMAIL=you@example.com ./scripts/setup-modelmarket-ssl.sh
```

它会安装 `deploy/nginx/modelmarket.dev.conf`，从 **仓库根目录** 上下文构建
`modelmarket-hub:latest`，在 `127.0.0.1:9083` 上运行 hub，启用 `certbot.timer`，并为
`modelmarket.dev` + `www.modelmarket.dev` 签发证书。

**Factory vhost**，用于 `magic-ai-factory.com`（依据 [`production-domain.md`](./production-domain.md)）：

```bash
sudo cp deploy/nginx/magic-ai-factory.com.conf /etc/nginx/sites-available/magic-ai-factory.com
sudo ln -sf /etc/nginx/sites-available/magic-ai-factory.com /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

sudo certbot --nginx \
  -d magic-ai-factory.com -d www.magic-ai-factory.com \
  --non-interactive --agree-tos --redirect \
  -m YOUR_EMAIL@example.com
```

在 HTTPS 上线后，在 `.env` 中设置 `NEXT_PUBLIC_SITE_URL=https://magic-ai-factory.com`
并重新构建，使打包产物读取到它：

```bash
docker compose build app --no-cache
docker compose up -d
```

公开的 Alien Monitor 在 `https://magic-ai-factory.com/monitor/` 提供服务（nginx 将
`/monitor/` 代理到 `127.0.0.1:9100`；如果该 block 缺失，`deploy_alien_monitor.sh` 会给
运行中的 Certbot vhost 打补丁）。

### 5.4 验证

```bash
./scripts/verify_ecosystem_full.sh
```

预期 **`17/17 PASS`**。

---

## 6. 层级 4 — 预言机主机

预言机运行在一台 **独立机器** 上（`78.17.126.214`）。**`deploy_ecosystem.sh` 不会
部署预言机或 Platon** — 本 monorepo 中的 `oracles/` 和 `platon/` 是外部栈的归档镜像。
请在 Platon 主机上把它们搭建起来，然后从 Factory 主机联邦（federate）过去。

### 6.1 在 Platon 主机上（`78.17.126.214`，以 root）

Platon 应用必须已经在 `127.0.0.1:8080` 上监听，且
`PUBLIC_URL=https://oracles.modelmarket.dev`。然后：

```bash
sudo CERTBOT_EMAIL=you@example.com ./scripts/setup-oracles-platon-on-host.sh
```

它会安装 `deploy/nginx/oracles.modelmarket.dev.conf`，在 `127.0.0.1:8080/api/health`
上验证 Platon，并为 `oracles.modelmarket.dev` 签发证书。

### 6.2 从 Factory 主机 — 联邦

```bash
./scripts/announce-platon-oracles.sh
```

它读取管理员令牌（`data/secrets/aimarket_admin_token.txt`），带上 Platon 的 well-known URL
和签名者公钥，向本地 hub（`:9083`）POST `/ai-market/v2/federation/announce`，然后触发
一次联邦爬取。

验证预言机主机：

```bash
curl -s https://oracles.modelmarket.dev/.well-known/ai-market.json | jq '{hub_url, manifest_url, capabilities_count}'
curl -s https://oracles.modelmarket.dev/api/health | jq '{status, kappa, order_parameter}'
```

十七个预言机（Platon、Chronos、Lattice、Murmuration、Lumen、Colony、Turing、Percola、Fermat、Ablation、Landauer、Sortes、Gauss、Aestus、Betti、Kantor、Fourier）以及
经济循环记录在 [`oracles/docs/en.md`](../oracles/docs/en.md) 中。

---

## 7. 可选 — 链上（Base，chain 8453）

与容器编排 **相互独立**。这些会用 Foundry 将 Solidity 合约部署到 Base 主网。
两者默认都是免 gas 的 dry run；传入 `broadcast` 以花费真实 gas。

**生态系统核心** — FakeUSDT + `AIMarketEscrow` + `AIMarketCapabilityNFT`
（ACEX 被有意排除 — 审计将 AuditPool TWAP + PulseAMM 标为 HIGH）：

```bash
./scripts/deploy_ecosystem_base.sh            # dry-run (no gas)
./scripts/deploy_ecosystem_base.sh broadcast  # real deploy
```

**Agent Lottery** — `AIAgentLottery`（原生 ETH 门票，部署时 admin/governance/treasury
设置为 `OWNER`）：

```bash
./scripts/deploy_lottery_base.sh              # dry-run (simulate, NO gas)
./scripts/deploy_lottery_base.sh broadcast    # real deploy
```

两者都从 `$BURNER_KEYFILE`（默认 `~/.aicom-base-deployer.json`）读取 burner 密钥，并使用
`BASE_RPC`（默认 `https://mainnet.base.org`）。生态系统核心脚本在 broadcast 之后会将
Escrow/NFT 所有权分两步转移给 `OWNER`（`OWNER` 随后必须调用 `acceptOwnership`）；lottery
则改为在部署时把 admin/governance/treasury 设为 `OWNER`，没有部署后的转移。这些是真实资金 —
请将金额保持在最小限度。

---

## 8. 多主机拓扑

```
┌──────────────────────────────────────────────┐      ┌────────────────────────────────────┐
│  FACTORY FLEET — 5.129.212.122                │      │  ORACLE HOST — 78.17.126.214        │
│                                                │      │                                      │
│  Factory  aicom-app-1        :9081 API/:9080 UI│      │  Platon Shadow Oracle  127.0.0.1:8080│
│  Hub      modelmarket-hub    :9083             │ fed  │  Oracle family (17 oracles)          │
│  Mesh     aicom-mesh-api     :8090             │◄────►│                                      │
│  ARGUS    reference agent    :8787             │ announce-platon-oracles.sh (factory host)   │
│  Monitor  alien-monitor      :9100             │      │  oracles.modelmarket.dev (own nginx) │
│  Pulse    terminal           :5199             │      │  NOT in deploy_ecosystem.sh (L4)     │
│  Lottery relayer (UNI)       :9195             │      │                                      │
│  Landing  modeldev…          nginx             │      └────────────────────────────────────┘
│                                                │
│  magic-ai-factory.com  /  modelmarket.dev      │
└──────────────────────────────────────────────┘
```

`deploy_ecosystem.sh` / `quickstart_ecosystem.sh` 覆盖 **左侧框**（步骤 1–7）。预言机
主机用 `setup-oracles-platon-on-host.sh` 置备（层级 4 — 默认 **独立机器**），并用
`announce-platon-oracles.sh`（从 Factory 主机）加入联邦。

你 *可以* 把预言机运行在与 factory 相同的 VPS 上（单机实验室）— 把
`oracles.modelmarket.dev` 指向同一个 IP 并在那里也运行 L4 脚本即可 — 这不是默认的
生产拓扑。

---

## 9. 一台 VPS **不包含**什么

| 组件 | 为什么 | 如何添加 |
|-----------|-----|------------|
| **17 个预言机 + portal** | 层级 4 — 生产文档中的独立主机 | `setup-oracles-platon-on-host.sh` + `announce-platon-oracles.sh` |
| **Base 链上合约** | 可选；真实 gas | `deploy_ecosystem_base.sh broadcast`、`deploy_lottery_base.sh broadcast` |
| **Metis** | 认知层；未接入舰队脚本 | 单独部署 `metis/`；Factory 可调用 `/v1/verify` |
| **DIOSCURI / HELIOS** | 社区 / 广播卫星 | 独立仓库；不属于核心舰队 |
| **Prometheus** | 可观测性可选层 | `./scripts/deploy_observability.sh`（参见生态系统审计笔记） |

---

## 10. 验证与运维

### 完整冒烟测试（17+ 项检查）

```bash
./scripts/verify_ecosystem_full.sh
```

检查 Factory 核心（`/api/health`、前端 `:9080`、`/api/products`、trust-metrics、security
store、funnel lead、admin dashboard、product P&L）、Hub（`.well-known`、`stats/live`、capital
pricing）、Mesh（`/v1/stats`）、Pulse（`:5199`）、Alien Monitor（UNIVERSE health + TEST/REAL/
UNIVERSE 进程内探测），以及 UNI lottery（已部署的 `evm_lottery`、relayer `/healthz`、
实时 lottery 指标）。用 `FACTORY_URL`、`HUB_URL`、`MESH_URL`、`MONITOR_URL`、`PULSE_URL`、
`LOTTERY_RELAYER_URL` 覆盖目标。

### 部分重新部署

| 目标 | 命令 |
|------|---------|
| 仅 Factory | `./scripts/deploy.sh` |
| 仅 Hub | `./scripts/deploy_hub.sh` |
| Mesh + Monitor（演示栈） | `./scripts/deploy_demo_stack.sh`（假定 Factory + Hub 已启动） |
| 仅验证 | `./scripts/verify_ecosystem_full.sh` |

### Hub 重新部署的隐患 — 请阅读

> **不要用子文件夹的 Compose 重新部署 Hub。** 始终使用 `./scripts/deploy_hub.sh`。
>
> ```bash
> cd aimarket-hub && docker compose up -d --build   # WRONG — breaks image/context; Hub can disappear
> ```
>
> `deploy_hub.sh` 从 **monorepo 根目录**（`modelmarket-hub:latest`，容器
> `modelmarket-hub`）构建，与 `setup-modelmarket-ssl.sh` 中的 TLS 配置相匹配，并安全地
> 替换容器。`aimarket-hub/docker-compose.yml` 文件仅保留作本地开发参考。切勿在不立即
> 运行 `deploy_hub.sh` 的情况下停止/移除 `modelmarket-hub`。

---

## 11. 相关文档

- [`deploy-ecosystem.md`](./deploy-ecosystem.md) — 运维参考（手动顺序、部分重新部署）
- [`production-domain.md`](./production-domain.md) — `magic-ai-factory.com` nginx + TLS
- [`production-modelmarket-dev.md`](./production-modelmarket-dev.md) — hub 域名、DNS、预言机主机
- [`oracles/docs/en.md`](../oracles/docs/en.md) — 十七个预言机与经济循环
- [AIMarket SDK 文档](../aimarket-sdks/docs/en.md) · [Python agent](../aimarket-agent/docs/en.md) — 消费 Hub

---

🇬🇧 [English](./quickstart-ecosystem-deploy.md) · 🇷🇺 [Русский](./quickstart-ecosystem-deploy.ru.md) · 🇪🇸 [Español](./quickstart-ecosystem-deploy.es.md) · 🇫🇷 [Français](./quickstart-ecosystem-deploy.fr.md) · 🇨🇳 **中文**
