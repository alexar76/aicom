# AI-Factory 用户指南（详细版）

> **适用人群：** 使用**店面**和**管理面板**的运维人员、产品负责人和支持人员。  
> **语言：** [English](./USER_GUIDE.md) · [Русский](./USER_GUIDE.ru.md) · [Español](./USER_GUIDE.es.md) · [Français](./USER_GUIDE.fr.md) · **中文** · **FAQ：** [FAQ.md](./FAQ.md) · [FAQ.ru.md](./FAQ.ru.md) · [FAQ.es.md](./FAQ.es.md)

> **截图**位于 [`docs/assets/screenshots/`](./assets/screenshots/)。如果你的克隆中缺少 PNG，请启动整个栈并运行：
>
> ```bash
> cd web/frontend
> DOCS_SCREENSHOT_BASE_URL=http://127.0.0.1:9080 ADMIN_PASSWORD='你的管理员密码' npm run capture-docs-screenshots
> ```

---

## 目录

1. [你所看到的是什么](#你所看到的是什么)
2. [该去哪里查看 — 场景速查表](#该去哪里查看--场景速查表)
3. [点击任何东西之前的五个要点](#点击任何东西之前的五个要点)
4. [你的前 15 分钟](#你的前-15-分钟)
5. [公开店面（无需登录）](#公开店面无需登录)
6. [公开文档 `/docs`](#公开文档-docs)
7. [管理员登录与安全](#管理员登录与安全)
8. [管理后台导航图](#管理后台导航图)
9. [Dashboard](#dashboard)
10. [Live Monitor](#live-monitor)
11. [New Product — 向导与模板](#new-product--向导与模板)
12. [Pipeline Monitor — 事实来源](#pipeline-monitor--事实来源)
13. [Workshop](#workshop)
14. [Discovery](#discovery)
15. [LLM Providers & LLM Logs](#llm-providers--llm-logs)
16. [Settings](#settings)
17. [场景手册](#场景手册)
18. [界面中可操作的错误](#界面中可操作的错误)
19. [截图索引](#截图索引)
20. [相关手册](#相关手册)

---

## 你所看到的是什么

**AI-Factory** 接受一个**用自然语言描述的想法**，并运行一条**固定的多智能体 pipeline**（带质量门禁），将产物保存在 `/app/data` 下（规格、架构、代码、营销）。

| 界面 | URL | 角色 |
|------|-----|------|
| 店面 | `/` | 买家、演示 |
| 产品页 | `/product/{id}` | 单次运行的公开状态 |
| Admin | `/admin` | 运维人员 |
| 应用内文档 | `/docs` | 相同的指南，内嵌图片 |

---

## 该去哪里查看 — 场景速查表

| 情况 | 先去哪里 | 检查什么 | 截图 |
|------|----------|----------|------|
| 站点无法加载 | 主机健康状况、`docker compose ps`、`:9081/api/health` | 容器 `app` 是否健康 | — |
| 无法登录 | `/admin/login`、[security.md](./security.md) | bootstrap 密码，而非 `admin123` | ![Login](./assets/screenshots/admin-login.png) |
| 创建了产品 — 它在哪里？ | **Pipeline** | 搜索 `prod-…`，按 *shipped first* 排序 | ![Pipeline](./assets/screenshots/admin-pipeline.png) |
| Pipeline 显示 "try N of 8" | **Pipeline**（等待；每次尝试最多 5 分钟） | *Connection phase* = HTTP 重试；随后 *X / total* | ![Pipeline](./assets/screenshots/admin-pipeline.png) |
| 产品卡在某个阶段 | **Pipeline** → 点击阶段块 | 任务 `running` / `failed`、错误 | ![Pipeline](./assets/screenshots/admin-pipeline.png) |
| LLM / 模型错误 | **LLM Providers** → **LLM Logs** | 密钥、路由、超时 | ![Providers](./assets/screenshots/admin-providers.png) |
| COMPLETED 但未出现在店面 | **Pipeline** 卡片 | `storefront_gate_reasons` | ![Pipeline](./assets/screenshots/admin-pipeline.png) |
| 仅需快速落地页 | **New product** → landing-only | `marketing_landing` | ![New product](./assets/screenshots/admin-new-product.png) |
| 对比两份规格 | **Workshop** diff | 两个产品 id | ![Workshop](./assets/screenshots/admin-workshop.png) |
| 自主生成的想法 | **Discovery** | 排序队列，在 Settings 中自动入队 | ![Discovery](./assets/screenshots/admin-discovery.png) |
| 快速健康快照 | **Dashboard** | KPI、任务数 | ![Dashboard](./assets/screenshots/admin-dashboard.png) |
| 首次配置 / 公开 URL | **Setup wizard** | 实例检查清单 | ![Setup](./assets/screenshots/admin-setup.png) |
| 实时指标 / 演示视频 | **Live Monitor** | SSE、demo replay | ![Live Monitor](./assets/screenshots/admin-live-monitor.png) |
| 会话过期 | **/admin/login** | 401 | ![Login](./assets/screenshots/admin-login.png) |
| 权限被拒 | [admin-panel-rbac.md](./admin-panel-rbac.md) | 你的角色 | — |

更多问答：**[FAQ.md](./FAQ.md)** · **[FAQ.ru.md](./FAQ.ru.md)**

---

## 点击任何东西之前的五个要点

1. **Product** = pipeline 中的一行（`prod-xxxxxxxx`）。
2. **State** = pipeline 阶段 — 与店面可见性不是一回事。
3. **Delivery profile** = `full_software` | `marketing_landing` | `infer`。
4. **Sandbox** = `/api/sandbox/…` 下的预览。
5. **LLM Providers** 必须正常工作，否则智能体会失败 — UI 会从错误卡片链接到那里。

---

## 你的前 15 分钟

1. 打开 `/` 和 `/docs`。
2. 在 `/admin/login` 登录（密码见 [security.md](./security.md)）。
3. 阅读后关闭蓝色的 **Get oriented** 卡片。
4. **New product** → 模板或自定义想法 → 提交。
5. **Pipeline** → 找到你的 id → 观察阶段条。

---

## 公开店面（无需登录）

**场景 — 访客提交一个想法**

1. `/` 上的 hero 表单（若已启用）。
2. 收到 `prod-…` 和 `/product/{id}`。
3. 运维人员在 **Pipeline** 中找到同一个 id。

![Storefront home](./assets/screenshots/public-home.png)

**场景 — 买家浏览目录**

只有通过 **marketplace gates** 的产品才会出现（数量可能少于 Dashboard 的 **Completed**）。

主页的 **Products** 区块包含两个网格：

| 区块 | 显示什么 |
|------|----------|
| **Marketing landing pages** | `delivery_profile = marketing_landing` |
| **Full products** | `full_software` 及其他非 landing 的 profile |

**目录加载：** 浏览器首先从 **`localStorage`**（`aicom_storefront_catalog_v1_all` 或 `_<category>`）渲染，然后在后台从 API 刷新（*"Showing cached catalog — updating…"*）。这与 Admin Pipeline Monitor 的缓存（`aicom_pipeline_catalog_v2_*`）**不是**同一个缓存。

---

## 公开文档 `/docs`

与利益相关方分享 `/docs` — 其中包含快速上手内容以及与本文件相同的截图集。

![Public docs](./assets/screenshots/public-docs.png)

---

## 管理员登录与安全

1. URL：**`/admin/login`**，用户 **`admin`**。
2. **没有默认的 `admin123`。** 首次安装时：
   - 交互式：`docker compose run -it app` — 密码会在控制台中询问；
   - 无界面（headless）：文件 **`data/secrets/bootstrap_admin.txt`**（读取一次后即删除或更改）。
3. 生产环境中仅使用 **HTTPS**，并在第一天就轮换密码。
4. JWT 存放在 `localStorage` 中 — 切勿在共享机器上保持会话打开。
5. 可用时启用 **2FA**。

![Admin login](./assets/screenshots/admin-login.png)

---

## 管理后台导航图

左侧菜单是位于 `/admin` 的单个 SPA；标签页通过 `?tab=…` 切换。

![Sidebar](./assets/screenshots/admin-sidebar.png)

| 标签页 | 运维用途 |
|--------|----------|
| **Dashboard** | 打开即显示 KPI 快照 |
| **Setup wizard** | 初始 URL 与 LLM 配置 |
| **Live Monitor** | 流式指标、Director、演示视频 |
| **Pipeline** | 所有 `prod-…`、阶段、店面、错误 |
| **New product** | 将新工作入队 |
| **Workshop** | 规格/架构 diff、canvas、patterns |
| **LLM Providers** | 模型密钥与路由 |
| **LLM Logs** | 调试 LLM 调用失败 |
| **Discovery** | 外部信号 → 想法 |
| **Settings** | Autopilot、CORS、demo replay、Railway … |
| **Corporate Chat / Brainstorming** | 讨论，非 pipeline | ![Chat](./assets/screenshots/admin-corporate-chat.png) · ![Brainstorming](./assets/screenshots/admin-brainstorming.png) |

完整标签页参考：[admin-guide.md](./admin-guide.md)。

---

## Dashboard

**何时：** 早晨快速检查、部署之后。

| 区块 | 含义 |
|------|------|
| Total / Active / Completed / Failed | 队列规模 |
| Pending / Running tasks | worker 积压 |
| CPU / Memory / Disk | 主机资源 |
| Revenue | 若已启用商务 |

**注意：** Dashboard 的 **Completed** ≠ 店面上架数量。

![Dashboard](./assets/screenshots/admin-dashboard.png)

---

## Live Monitor

**何时：** 演示、自主 Director、实时升级。

![Live Monitor](./assets/screenshots/admin-live-monitor.png)

- **Connected** 指示灯（SSE）。
- **Demo replay** — 一段内嵌的 pipeline 运行视频（在 Settings 中配置）。
- 升级事件与智能体信息流。

详情：[pipeline-operations.md](./pipeline-operations.md)（Live Monitor 的 demo replay 部分）。

### Setup wizard（首次访问）

![Setup wizard](./assets/screenshots/admin-setup.png)

**Setup wizard** 标签页涵盖公开 URL、LLM 密钥，以及进入自主模式前所需的检查。另见 Dashboard 上的蓝色引导卡片。

---

## New Product — 向导与模板

路径：`/admin?tab=new-product`

![New product](./assets/screenshots/admin-new-product.png)

### 案例：带 dashboard 的 SaaS（full_software）

| 步骤 | 操作 |
|------|------|
| Idea | "SaaS for remote team standups with auth and API" |
| Options | **Full product**；文案语言 **Auto** 或 **English** |
| Review | **Start building** → 记下 `prod-…` id |

### 案例：仅落地页（快速）

| 步骤 | 操作 |
|------|------|
| Options | **Marketing landing page only** |
| Review | 预期阶段更少、`COMPLETED` 更快 |

### 案例：为团队保存预设

- **Save current to cloud** — 模板存储在服务器上（登录后可从另一个浏览器看到）。
- 本地模板 — 仅保留在当前浏览器中。

### 案例：AI 预填充

- 勾选**同意复选框** — 未勾选则不会调用 LLM。
- 失败时 — 出现红色 **Actionable failure** 面板，带 **Retry** 及指向 Providers 的链接。

---

## Pipeline Monitor — 事实来源

路径：`/admin?tab=pipeline`

![Pipeline](./assets/screenshots/admin-pipeline.png)

### 目录加载（重要）

1. **Cold start**（该排序没有 `localStorage` 快照）：你可能看到 *Fetching first catalog page…* 和 *Server request N / M*。
2. 每个 **N** 都是一次真实的 **HTTP 尝试**（首页最多 8 次）。之前的尝试失败或超时 — 客户端以退避方式重试。
3. **每次尝试的超时：** 最多 **5 分钟**（`300_000` ms）。
4. **Connection phase** 进度条 ≈ 重试序号；行返回后，**目录 %** 以 **X / total** 形式出现在标题栏。
5. **缓存：** 成功后，精简目录会存入 **localStorage**（`aicom_pipeline_catalog_v2_*`）— 下次访问立即渲染，然后在后台刷新。

### 卡片剖析

| UI | 用途 |
|----|------|
| 阶段条（Anl、Pm、Dev、Qa…） | 每个智能体的任务状态；**点击**打开任务弹窗 |
| **Spec** | PM 规格 |
| **Dev handoff** | 移交给开发者 |
| state / category 徽章 | 过滤与搜索 |
| Storefront / follow-up | 手动标签与店面 gates |

### 值得了解的筛选器

- **Sort: shipped first** — 已完成的工作置顶。
- **Search** — id、标题、描述、follow-up 文本。

---

## Workshop

![Workshop](./assets/screenshots/admin-workshop.png)

Board、材料 diff（spec/arch）、迭代 canvas、pattern 库、Web Push 实验室 — 场景细节见 [USER_GUIDE.ru.md](./USER_GUIDE.ru.md)。

---

## Discovery

![Discovery](./assets/screenshots/admin-discovery.png)

排序后的外部想法、摘要与来源健康状况。只有在 **Settings** / env（`AIFACTORY_DISCOVERY_AUTO_ENQUEUE`）中显式启用时，自动入队才会运行 — 见 [configuration.md](./configuration.md)。

---

## LLM Providers & LLM Logs

![Providers](./assets/screenshots/admin-providers.png)

![LLM Logs](./assets/screenshots/admin-llm-logs.png)

任何提及模型、token 或超时的智能体失败，都先来这里。

| 症状 | 操作 |
|------|------|
| 每个智能体都因认证失败 | 在 Providers 中检查密钥 |
| 只有一个智能体失败 | 路由规则、模型 id |
| 超时 / 速率限制 | Logs + 在 provider 的 yaml 中调高超时 |
| 更改密钥之后 | 保存，然后 **Retry** 任务或等待返工 |

---

## Settings

![Settings](./assets/screenshots/admin-settings.png)

自主模式、demo replay、自动发布、Railway、CORS — 见 [configuration.md](./configuration.md)。

---

## 场景手册

### 1 — 第一个产品端到端

Providers（密钥）→ New product → Pipeline 观察阶段 → sandbox URL → 若在意上架则检查店面 gates。

### 2 — Pipeline 目录缓慢或重试

检查 `/api/health` → 等待当前尝试（最多 5 分钟）→ 在 DevTools Network 中查看 `pipeline/products?light=1` → 若出现 502 则调高 proxy 超时 → 见 [FAQ.md](./FAQ.md)。

### 3 — 从店面移除但不删除

Pipeline → 产品 → 店面控件 / 将 follow-up 标记为 **not pursuing**（见 admin-guide）→ 在隐身窗口中验证公开店面。

### 4 — 五分钟投资人演示

预先准备一张绿色的 **Pipeline** 卡片 + sandbox；在 Live Monitor 上启用 **demo replay**；Dashboard KPI。

### 5 — 产品未通过 QA

Pipeline → 失败的 **Qa** 块 → 任务错误 → QA 报告位于服务器上的 `data/bugs/{id}/`。

### 6 — 策略审计重新打开了旧产品

产品可能显示修复状态但仍保持上架 — [pipeline-operations.md](./pipeline-operations.md)。

---

## 界面中可操作的错误

| 症状 | UI 操作 | 另需检查 |
|------|---------|----------|
| 网络 / 超时 | Retry、Settings | Compose、proxy |
| 401 | 重新登录 | JWT 过期 |
| 403 | — | RBAC |
| LLM 错误 | Providers、LLM Logs | 密钥 |
| 目录不完整 | Retry catalog | FAQ "try N of 8" |
| 预填充被阻止 | Consent checkbox | New product |

---

## 截图索引

| 文件 | 内容 |
|------|------|
| `public-home.png` | 店面 `/` |
| `public-docs.png` | `/docs` |
| `admin-login.png` | 登录 |
| `admin-dashboard.png` | Dashboard |
| `admin-sidebar.png` | 完整侧边栏 |
| `admin-setup.png` | Setup wizard |
| `admin-live-monitor.png` | Live Monitor |
| `admin-pipeline.png` | Pipeline Monitor |
| `admin-new-product.png` | New product 向导 |
| `admin-workshop.png` | Workshop |
| `admin-providers.png` | LLM Providers |
| `admin-llm-logs.png` | LLM Logs |
| `admin-discovery.png` | Discovery |
| `admin-settings.png` | Settings |
| `admin-corporate-chat.png` | Corporate Chat |
| `admin-brainstorming.png` | Brainstorming |

刷新：`cd web/frontend && npm run capture-docs-screenshots` — 详情见 [assets/screenshots/README.md](./assets/screenshots/README.md)。

---

## 相关手册

| 文档 | 何时使用 |
|------|----------|
| [FAQ.md](./FAQ.md) / [FAQ.ru.md](./FAQ.ru.md) / [FAQ.es.md](./FAQ.es.md) | 常见问题 |
| [USER_GUIDE.ru.md](./USER_GUIDE.ru.md) | 俄语讲解 |
| [USER_GUIDE.es.md](./USER_GUIDE.es.md) | 西班牙语讲解 |
| [owner-guide.md](./owner-guide.md) | 生产环境所有者 |
| [admin-guide.md](./admin-guide.md) | 每个 admin 标签页 |
| [admin-panel-rbac.md](./admin-panel-rbac.md) | 角色 |
| [pipeline-operations.md](./pipeline-operations.md) | worker 行为 |
| [configuration.md](./configuration.md) | 环境变量 |

---

*AI-Factory v2.1 — 带情景索引和 FAQ 链接的详细用户指南。UI 发生重大变更后请重新生成截图。*
