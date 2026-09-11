# FAQ — AI-Factory（详细版）

> 图解指南：[USER_GUIDE.zh.md](./USER_GUIDE.zh.md) · English: [FAQ.md](./FAQ.md) · Español: [FAQ.es.md](./FAQ.es.md) · Русский: [FAQ.ru.md](./FAQ.ru.md) · Français: [FAQ.fr.md](./FAQ.fr.md) · **中文**

---

## 综述

### 用一句话说明 AI-Factory 是什么？

一个系统：它接收纯文本形式的创意，让其经过一条 **AI 智能体链**（调研 → 规格 → 编码 → QA → …），并将产物保存到磁盘，同时配有管理面板和可选的公开店面。

### 店面与管理面板有什么区别？

| | 店面 `/` | 管理端 `/admin` |
|---|------------|------------------|
| 登录 | 通常无需 | JWT，用户名 `admin` |
| 用途 | 展示成品、线索表单 | 管理流水线 |
| 权威数据源 | 经过筛选的 API 目录 | **Pipeline** — 完整的 `prod-…` 列表 |

### “真实”的产品数据在哪里？

**Admin → Pipeline** — 包含任务和错误的完整目录。Dashboard 仅是加载时刻的快照。Live Monitor 是一路指标流。

### 运维人员需要 git clone 吗？

不需要。已部署实例的 URL 和管理员密码就足够了。文档也通过 `/docs` 提供。

---

## 访问与安装

### 默认的管理员密码是什么？

**没有固定密码。** 在首次、空的 `data/` 上，密码会在入口点（entrypoint）控制台中设置，或写入 `data/secrets/bootstrap_admin.txt`。详见 [security.md](./security.md)。

### 公开演示（magic-ai-factory.com）？

**免密码：** 用户名 `admin`，点击 **Enter admin demo**（密码字段被隐藏）。`AIFACTORY_DEMO_READONLY=1` 会在管理面板中阻止破坏性操作。参见 [security.md § Public demo](./security.md#public-demo-mode-aifactory_demo_readonly1)。

### 登录不了 — 该检查什么？

1. 用户名精确为 **`admin`**（如果你还没有创建其他用户）。
2. 首次 `up` 时生成的 bootstrap 文件 / 设置的密码。
3. 服务器时钟（JWT）。
4. HTTPS 与 HTTP 以及 `Secure` cookie。
5. 不要弄混端口：在默认 Compose 配置下，UI 通常是 **9080**，API 是 **9081**。

### viewer / operator / admin / super_admin 这些角色是什么？

参见 [admin-panel-rbac.md](./admin-panel-rbac.md)。**Operator** 可以运行流水线，但不一定总能修改 Settings 和提供方。

---

## New product 与队列

### 一次完整运行需要多久？

从 **几分钟** 到 **数小时** — 取决于 `full_software`、LLM 负载、带 Playwright 的 QA，以及修复循环的次数。落地页通常更快。

### 产品处于 HUMAN_REVIEW_PENDING、没有任务？

对于 **`full_software`**，DevOps 之后有一个 **手动关卡**：你需要在 Pipeline 卡片（`HumanReviewGatePanel`）上 **Approve** 或 **Reject**。落地页（`marketing_landing`）会跳过此步。参见 [admin-guide.md](./admin-guide.md#post-devops-human-review)（EN）。

### full_software 与 marketing_landing 有什么区别？

| | full_software | marketing_landing |
|---|---------------|-------------------|
| 结果 | API、数据库、许多页面 | 静态/简单站点 |
| 阶段 | 完整链条 | 缩短的路径 |
| 部署 | Railway / compose | Vercel/Netlify 静态 |

### 创建后在哪里找到产品 id？

向导中的成功页面、**Pipeline**（按名称搜索），或者如果已发布则通过 URL `/product/{id}`。

### 可以取消队列中的产品吗？

取决于状态和 worker 策略。参见 admin-guide 和 API。通常，让它保持 `FAILED` / 不再推进，比物理删除它更简单。

---

## Pipeline Monitor

### 为什么显示 “try 4 of 8” / “Server request 4 / 8”？

那是对 `/api/admin/pipeline/products` **同一个 HTTP 请求的第四次尝试**。之前的尝试以错误、超时或 502 结束。客户端 **有意** 以退避（backoff）方式重试（参见 `pipelineCatalogFetch.ts`）。它 **并不** 意味着“浏览器连不上 API”。

### 一次尝试应该花多久？

每次尝试最多 **5 分钟**（`clientTimeoutMs` 300 000 ms）。两次尝试之间在首页有最多约 8 秒的暂停。

### 为什么进度条“不动”？

- 在 **连接阶段（Connection phase）**，进度条显示的是 **HTTP 尝试次数**，而非目录加载的百分比。
- 一旦出现行数据，请看表头：**X / total** 和绿色进度条 — 那才是页面填充（hydration）的 **真实** 进度。

### 目录缓存在哪里？

**Pipeline Monitor：** 在 **localStorage** 中 — `aicom_pipeline_catalog_v2_{sort}` 加上两行预览。首次访问 / 不同排序 / 清空存储 → 会进入带重试的“冷”启动。

**公开店面（`/`）：** `aicom_storefront_catalog_v1_{category}` — 先用缓存，再在后台 `GET /api/products`。参见 [marketing.md](./marketing.md)。

### 为什么先显示 “All Categories (0)”，然后才出现数字？

分类计数来自 **已加载** 的行；当目录仍在填充时，计数器可能不完整（选项上的 `+` 后缀）。

### 产品 COMPLETED，但不在店面上 — 为什么？

`storefront_gate_reasons` 中的典型原因：

- 磁盘上没有代码；
- 未通过 **marketplace quality**；
- 被手动隐藏（**hidden from storefront**）；
- 状态尚未进入可发布（shipped）族。

请在 **Pipeline** 中检查该卡片，并参见 [pipeline-operations.md](./pipeline-operations.md)。

### 如何找到“卡住”的产品？

1. Pipeline → 按状态 **running** 过滤 / 留意橙色阶段。
2. 点击某个阶段 → 长时间处于 `running` 且没有 `ended_at` 的任务。
3. Live Monitor / LLM Logs。
4. Worker 日志：`data/logs/`。

### “Updating from server… 2 / 10” 是什么意思？

服务器上 10 行目录中已加载 2 行；其余的会在后台以每批 12 行拉取。

---

## LLM 与提供方

### 智能体没反应 / LLM 全部 FAILED

1. **LLM Providers** — 密钥、是否启用、model id。
2. **LLM Logs** — 最近的错误。
3. 卷上的 `data/config/model_providers.yaml`（不在 git 中）。
4. 提供方的速率限制。

### 容器需要访问互联网吗？

需要，对于云端 API。宿主机上的 Ollama — 使用 `docker-compose.host-gateway.yml` overlay。

### 什么是 heavy / light 模型？

在 Providers 中做路由：重任务（architect）与轻任务。参见 admin-guide。

---

## 店面与买家

### 为什么首页上的产品比 Dashboard 中的 Completed 少？

店面会应用 **额外的过滤**（质量、代码、隐藏）。Dashboard 统计流水线中每一个 `COMPLETED`。

### Support / Lumen — 那是流水线里的智能体吗？

**不是。** 它是面向交易市场买家的助手，与 **AI Agents** 名单相互独立。

---

## Discovery 与 Director

### 创意自己出现了 — 这正常吗？

正常，如果启用了 **autonomous pipeline** 和 **discovery auto-enqueue**。否则创意只会手动产生，或通过 Discovery API 产生。

### 如何关闭创意的自动入队？

`AIFACTORY_DISCOVERY_AUTO_ENQUEUE=0`，在 Settings 中设置 `general.auto_pipeline: false` — 参见 [configuration.md](./configuration.md)。

---

## Sandbox 与预览

### Sandbox 无法在 iframe 中打开

1. `AIFACTORY_SANDBOX_PREVIEW_API`、compose preview。
2. app 容器中的 Docker socket。
3. CSP / 混合内容 — HTTPS。
4. API 中的 sandbox 日志。

### sandbox 与 auto-publish 有何不同？

**Sandbox** 是工厂上的预览。**Auto-publish** 是 DevOps 之后向 Vercel/Netlify 的静态导出。

---

## 数据与备份

### 产品存放在哪里？

绑定挂载（bind mount）**`./data`**（或 `~/aicom-data`）— `data/code/`、`data/specs/`、`data/state/pipeline.db` 以及各项配置。

### docker run 之后数据消失了

一个常见错误：用了 **命名卷（named volume）** 而非绑定挂载。参见 README — 关于从命名卷迁移的章节。

### 可以删除所有 demo 产品吗？

`./scripts/run_factory_demo_reset.sh` 或 `wipe_pipeline_products.py` — 小心，此操作不可逆。

---

## 性能与 CI

### 目录 API 很慢

在优化之后，对于较小的 `limit`，light 模式应在 **数秒内** 响应。如果又变成数分钟 — 检查 `pipeline.db` 的大小、代理超时，并且不要在没有需要时加载 `light=0`。

### GitHub Actions 在测试上失败

参见 `.github/workflows/ci.yml` — pytest + Playwright 作业。本地：在 venv 中运行 `pytest -q`。

---

## 安全

### 可以在直播中展示 git remote 吗？

**不可以**，如果 URL 中包含令牌。参见 README — Screen recordings & Git remotes。

### JWT 存储在哪里？

浏览器的 `localStorage` + 一个 httpOnly cookie（参见 security.md）。不要在公共机器上。

---

## 文档与截图

### 如何更新指南中的截图？

```bash
cd web/frontend
DOCS_SCREENSHOT_BASE_URL=http://127.0.0.1:9080 ADMIN_PASSWORD='…' npm run capture-docs-screenshots
```

文件清单：[assets/screenshots/README.md](./assets/screenshots/README.md)。

### git clone 中 markdown 里的图片损坏

PNG 尚未提交或尚未截取 — 请对着一个运行中的实例执行上面的脚本。

---

## 上报升级

| 级别 | 文档 |
|---------|----------|
| UI 运维人员 | [USER_GUIDE.zh.md](./USER_GUIDE.zh.md)、本 FAQ · RU: [USER_GUIDE.ru.md](./USER_GUIDE.ru.md) · ES: [USER_GUIDE.es.md](./USER_GUIDE.es.md) |
| 实例所有者 | [owner-guide.md](./owner-guide.md) |
| DevOps / 环境 | [configuration.md](./configuration.md)、[production-domain.md](./production-domain.md) |
| API 集成 | [api-integration-guide.md](./api-integration-guide.md) |
| 漏洞 | [SECURITY.md](../SECURITY.md) |

---

*当支持工作中反复出现某些问题时，请扩充本 FAQ。*
