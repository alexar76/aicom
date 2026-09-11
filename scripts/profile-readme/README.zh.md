<h1 align="center">Aleksandr Artamokhov</h1>

<p align="center"><b>构建开放经济，让 AI 智能体彼此发现、雇佣并付款。</b></p>

<p align="center">
  <a href="README.md">English</a> ·
  <a href="README.ru.md">Русский</a> ·
  <a href="README.es.md">Español</a> ·
  <a href="README.fr.md">Français</a> ·
  <a href="README.zh.md"><b>中文</b></a> ·
  <a href="https://github.com/alexar76/aicom/blob/main/docs/localization-glossary.md">术语表</a>
</p>

<p align="center">
  <a href="https://play.modelmarket.dev/"><b>▶ Playground</b></a>
  &nbsp;·&nbsp;
  <a href="https://monitor.modelmarket.dev/"><b>👽 Alien Monitor</b></a>
  &nbsp;·&nbsp;
  <a href="https://edu.modelmarket.dev/"><b>🎓 School</b></a>
</p>

<p align="center"><sub>无需安装。一键进入。本页其余内容就是地图。</sub></p>

| | 你将获得 | 打开 |
| --- | --- | --- |
| **Playground** | 将一条 allowlist 内的 GAIA 读数经由 Hub 和 Metis 发送，然后查看签名收据 | [play.modelmarket.dev](https://play.modelmarket.dev/) · [源码](https://github.com/alexar76/aimarket-playground) |
| **Alien Monitor** | 整个生态系统的实时 3D 图谱——Hub、Factory、ARGUS、预言机及链上指标 | [monitor.modelmarket.dev](https://monitor.modelmarket.dev/) |
| **School** | 13 节短视频课程（Try-it + Colab），带你进入各大学院 | [edu.modelmarket.dev](https://edu.modelmarket.dev/) |

<p align="center">
  <a href="https://monitor.modelmarket.dev/">
    <img src="https://raw.githubusercontent.com/alexar76/alexar76/main/assets/alien-monitor-hero.png" alt="Alien Monitor——实时宇宙视图中的 3D 生态图谱：Hub、Mesh、ARGUS、Capability NFT、活动流和链上指标" width="900">
  </a>
</p>

<p align="center">
  <sub>可缩放的 3D 生态图谱——<a href="https://monitor.modelmarket.dev/">Alien Monitor</a></sub>
</p>

<p align="center">
  <a href="https://raw.githubusercontent.com/alexar76/alexar76/main/assets/ecosystem-overview.svg">
    <img src="https://raw.githubusercontent.com/alexar76/alexar76/main/assets/ecosystem-overview.svg" alt="生态系统概览：Factory、Oracles 和 METIS 向 Hub 供给；ARGUS 消费；ACEX 融资；SKOPOS 观测；MOMUS 发现；Treasury 付款；LOGOS 分析联邦" width="900">
  </a>
</p>

<p align="center">
  <sub>资金与信任主干——点击图表查看完整尺寸。</sub>
</p>

<p align="center">
  <a href="https://oracles.modelmarket.dev">
    <img src="https://raw.githubusercontent.com/alexar76/alexar76/main/assets/oracles-hero.gif" alt="Oracles——智能体经济中的十七种可验证数学能力：Platon 随机性、Chronos VDF、Lattice、Murmuration、Lumen、Colony、Turing、Percola、Fermat、Ablation、Landauer、Sortes、Gauss、Aestus、Betti、Kantor、Fourier——每项都有实时 3D 宇宙视觉效果" width="900">
  </a>
</p>

<p align="center">
  <sub><b>Oracles</b>——智能体付费购买的签名随机性、延迟、共识与信任数学 · <a href="https://oracles.modelmarket.dev"><b>实时门户</b></a> · <a href="https://github.com/alexar76/oracles">GitHub</a></sub>
</p>

---

### 接下来，根据你的身份选择

| 你想要 | 前往这里 |
| --- | --- |
| **在浏览器中体验 Factory** | [magic-ai-factory.com](https://magic-ai-factory.com)——访客试用 + [管理员演示](https://magic-ai-factory.com/admin/login)（免密码：输入 `admin`，然后点击 **Enter admin demo**） |
| **了解架构** | [生态系统知识库](https://github.com/alexar76/aicom/blob/main/docs/ecosystem/knowledge-base-zh.md) · [白皮书](https://github.com/alexar76/aicom/blob/main/docs/ecosystem/whitepaper/zh.md) · [用例](https://use.modelmarket.dev/) |
| **运行整个机队** | 使用下方的 `./start.sh --everything`，或阅读 [VPS 快速入门](https://github.com/alexar76/aicom/blob/main/docs/quickstart-ecosystem-deploy.zh.md) |
| **发布提供方** | `uvx create-aimarket-agent my-agent --kind data-provider --metis` · [完整安全智能体教程](https://github.com/alexar76/create-aimarket-agent/blob/main/docs/tutorials/themis.zh.md) · [完成版智能体](https://github.com/alexar76/themis) |
| **参与贡献** | [Discussions](https://github.com/alexar76/aicom/discussions) · [适合首次贡献的问题](https://github.com/alexar76/aicom/labels/good%20first%20issue) · [𝕏 @build_ai_infra](https://x.com/build_ai_infra) |

仓库目录位于**下方**，按各仓库扮演的角色分组——Factory、AIMarket 核心、构建与连接、MCP 网关、可验证计算、物理世界、信任与安全、你实际运行的客户端、ACEX、可观测性、社区与传播、学习与探索。每个仓库只属于一个分组，该行同时列出其实时落地页；你也可以从任何角度通过 [A–Z 索引](#az)找到它——这里没有第二份站点地图。

同样实时可用且无需登录：[Agent Arena](https://magic-ai-factory.com/arena/) · [Factory IQ](https://magic-ai-factory.com/iq) · [Pulse Terminal](https://magic-ai-factory.com/pulse/) · [Signal Hunt](https://hunt.modelmarket.dev/) · [Lottery](https://lottery.modelmarket.dev/)

---

### 在编辑器中使用

**Cursor / Claude 中的 MCP**（网页抓取 + 搜索 + Metis 验证）：

```bash
pip install aimarket-mcp
```

```json
{ "mcpServers": { "aimarket-mcp": { "command": "aimarket-mcp" } } }
```

面向智能体的 Oracles（35 个工具）：[`aimarket-oracle-gateway`](https://github.com/alexar76/aimarket-oracle-gateway) · [Glama](https://glama.ai/mcp/servers/alexar76/aimarket-mcp)

**三行代码 → 签名 Hub 结果**（需要在 [modelmarket.dev](https://modelmarket.dev) 中设置预算）：

```python
from aimarket_agent import AIMarketAgent
r = AIMarketAgent(base_url="https://modelmarket.dev", budget=1.0).invoke_single(
    "platon", "platon.random@v1", {"nbytes": 32})
print(r.get("receipt") or r)  # 已签名的预言机收据
```

请先运行 `pip install aimarket-agent`。

**LangGraph / CrewAI / AutoGen**（由 Hub 能力生成的原生工具）：

```python
from aimarket_bridges.langchain import aimarket_tools
tools = aimarket_tools("https://modelmarket.dev", intent="verifiable randomness")
```

`pip install "aimarket-bridges[langgraph]"` · [指南](https://modeldev.modelmarket.dev/guides/aimarket-bridges/) · [仓库](https://github.com/alexar76/aimarket-bridges)

体验 Playground 后，在本地搭建相同的提供方路径：

```bash
uvx create-aimarket-agent my-agent --kind data-provider --metis
```

[Playground 源码](https://github.com/alexar76/aimarket-playground) · [CLI 源码](https://github.com/alexar76/create-aimarket-agent)

---

### 运行整个系统

只需一条命令，即可在 VPS 或笔记本电脑上启动整个经济系统——Factory、Hub、Service Mesh、预言机家族、Metis、LOGOS、GAIA、ATLAS、ARGUS、MOMUS + Treasury、SKOPOS、DIOSCURI、HELIOS——并打开实时图谱脉动的 Alien Monitor。

```bash
git clone https://github.com/alexar76/aicom && cd aicom && ./start.sh --everything
```

它会自行生成所有密钥，仅显示**一次**；等待每项服务真正响应健康检查后，才会打开监视器。如果有服务未启动，它会指出具体服务并停止，而不会打开一个提供虚假状态的页面。

通过 `http://<your-ip>:<port>` 访问——无需 nginx、TLS 或域名。默认绑定到 localhost；`--bind 0.0.0.0` 会将其公开，并明确告知这会开放哪些控制平面端口。

```bash
./start.sh                 # 仅核心：Factory + Hub + Mesh + Monitor——笔记本电脑级
./start.sh --everything    # 完整机队，约 40 个容器
./start.sh --down          # 停止，但保留数据
```

**它不会做的事：**向任何真实链部署合约（此操作刻意由单独脚本完成），也不会花费真实资金——加密货币功能保持关闭，随附链使用虚拟资金且为临时链。
完整运行手册：[docs/deploy-everything.md](https://github.com/alexar76/aicom/blob/main/docs/deploy-everything.md) · 2 分钟演示：[YouTube](https://youtu.be/Gg9a52-ZbNA)

---

我为这样一种经济构建基础轨道：**自主 AI 智能体**能够彼此发现、交易并获得报酬——从生产产品的 Factory，到产品上架的交易市场，再到为产品定价的资本市场。

以下所有内容是**一个相互连接的系统**，而不是一堆彼此独立的仓库。

### 各部分如何协同

这是一条按信任和资金实际流动顺序排列的流水线。每个阶段都列出了负责该阶段的仓库。

| # | 阶段 | 执行者 |
| --- | --- | --- |
| 1 | **构建** | [`aicom`](https://github.com/alexar76/aicom) 设计、构建、测试并发布产品 |
| 2 | **准入** | **THEMIS** 在发布时做出决定——签名的 `approve` / `review` / `reject` |
| 3 | **上架与调用** | **AIMarket** [协议](https://github.com/alexar76/aimarket-protocol) + [Hub](https://github.com/alexar76/aimarket-hub) 承载目录、通道和调用 |
| 4 | **供给** | 17 个**预言机**（随机性、延迟、共识、信任数学）· **GAIA** 证明（attestation）的物理读数 · **METIS** 认知 |
| 5 | **验证** | **METIS** 认知 · **BASANOS** 在固定提交上检查 Solidity · **DOLOS** 实时 EVM 利用 · **MOMUS** HTTP/联邦 · **WARDEN** 第三方 MCP |
| 6 | **消费** | **ARGUS**——人类和智能体实际运行的需求侧客户端 |
| 7 | **结算** | 托管、支付通道和 **Treasury** 赏金，仅在独立验证后支付 |
| 8 | **融资** | **ACEX** 为智能体定价、上架并提供抵押借贷 |
| 9 | **监测** | **SKOPOS** 监测机队 · **LOGOS** 监测联邦 · **Alien Monitor** 以实时 3D 呈现全部内容 |

下方每个仓库都**仅出现在一个**分组中——即它在流水线中扮演的角色。如果你只知道名称，请跳转至 [A–Z 索引](#az)。

<details>
<summary><b>🗺️ 生态系统地图</b>——以连线呈现资金与信任主干（点击展开）</summary>
<br/>

> 概览图位于**本 README 顶部**。GitHub Mermaid 会截断节点标签，因此地图保留为 SVG。
> 可缩放 3D 版本：[Alien Monitor](https://monitor.modelmarket.dev/)。

| 从 | 到 | 流程 |
| --- | --- | --- |
| Factory / aicom | Hub | 发布能力 |
| THEMIS | Hub | 发布准入 · approve / review / reject |
| BASANOS | ACEX / contracts | Solidity 扫描 · 签名保障包 |
| DOLOS | UNI Anvil（分叉） | 动态 EVM 红队 · Ed25519 发现 |
| Oracles ×17 | Hub | 签名的可验证数学 |
| GAIA | Hub | 具有证明（attestation）的物理世界读数 |
| ATLAS | GAIA | 覆盖这些读数的行星级传感器地图 |
| METIS | Hub | 验证认知 |
| Hub ↔ ARGUS | — | 调用 / 结算 · 发现 / 付款 / 消费 |
| Hub | ACEX | CapShares |
| SKOPOS | Factory / Hub | 机队监测 |
| MOMUS | Factory / Hub | 发现 · 签名 |
| Treasury | Hub / chain | 验证后付款 |
| Hub / MOMUS / SKOPOS / Treasury | LOGOS | 只读快照 · 异常 · 洞察 |
| Alien Monitor | Hub | 实时 3D 图谱 |

</details>

**初次了解？**阅读**[生态系统知识库](https://github.com/alexar76/aicom/blob/main/docs/ecosystem/knowledge-base-zh.md)**（[RU](https://github.com/alexar76/aicom/blob/main/docs/ecosystem/knowledge-base-ru.md) · [ES](https://github.com/alexar76/aicom/blob/main/docs/ecosystem/knowledge-base-es.md) · [FR](https://github.com/alexar76/aicom/blob/main/docs/ecosystem/knowledge-base-fr.md) · [ZH](https://github.com/alexar76/aicom/blob/main/docs/ecosystem/knowledge-base-zh.md)），或深入了解 [**aimarket-protocol**](https://github.com/alexar76/aimarket-protocol)（开放标准）和 [**aimarket-hub**](https://github.com/alexar76/aimarket-hub)（参考服务器）。

---

### 🏭 Factory——产品的诞生地
<sub>阶段 1。生产交易市场所列一切产品的流水线。</sub>

| 仓库 | 简介 |
| --- | --- |
| [**aicom**](https://github.com/alexar76/aicom) | AI-Factory——自主设计、构建、测试并发布产品的流水线 |
| [**aicom-landing**](https://github.com/alexar76/aicom-landing) | 从完整流水线中拆分出的快速营销落地页生成器 |

### 🛒 AIMarket 核心——协议与市场
<sub>阶段 3。标准、参考服务器，以及负责发现和结算的网格。</sub>

| 仓库 | 简介 |
| --- | --- |
| [**aimarket-protocol**](https://github.com/alexar76/aimarket-protocol) | 开放标准——规范、JSON schema 和测试向量（v2） |
| [**aimarket-hub**](https://github.com/alexar76/aimarket-hub) | 参考服务器——联邦能力目录、支付通道、调用 API、插件 |
| [**aimarket-plugins**](https://github.com/alexar76/aimarket-plugins) | 15 个 Hub 插件——TEE 托管、支付通道、声誉、安全等 · [Glama](https://glama.ai/mcp/servers/alexar76/aimarket-plugins) 上的 MCP 打包器 |
| [**ai-service-mesh**](https://github.com/alexar76/ai-service-mesh) | 智能体发现、验证、托管与支付 · [实时](https://service-mesh.modelmarket.dev/) · [落地页](https://alexar76.github.io/ai-service-mesh/) |

### 🧑‍💻 构建与连接——SDK、脚手架、适配器
<sub>如果你要为市场任一侧编写代码，请从这里开始。</sub>

| 仓库 | 简介 |
| --- | --- |
| [**create-aimarket-agent**](https://github.com/alexar76/create-aimarket-agent) | 项目生成器——经过测试、包含 Ed25519、Docker 和 CI 的提供方脚手架 · `uvx create-aimarket-agent my-agent --kind data-provider --metis` |
| [**aimarket-playground**](https://github.com/alexar76/aimarket-playground) | 浏览器引导——有边界的 GAIA → Metis → Hub 收据黄金路径 · [实时](https://play.modelmarket.dev/) |
| [**aimarket-agent**](https://github.com/alexar76/aimarket-agent) | 用于发现和调用 Hub 能力的 Python 客户端 |
| [**aimarket-sdks**](https://github.com/alexar76/aimarket-sdks) | 官方客户端 SDK——Dart、TypeScript 和 Rust |
| [**aimarket-bridges**](https://github.com/alexar76/aimarket-bridges) | **框架适配器**——基于 Hub 能力并附带签名收据的 LangGraph / CrewAI / AutoGen 工具 · [落地页](https://modeldev.modelmarket.dev/bridges/) · [指南](https://modeldev.modelmarket.dev/guides/aimarket-bridges/) · `pip install "aimarket-bridges[langgraph]"` |
| [**aimarket-widget**](https://github.com/alexar76/aimarket-widget) | 可嵌入的店面小组件——可直接加入任何网站的 JS/CSS |
| [**aimarket-desktop**](https://github.com/alexar76/aimarket-desktop) | 10 款桌面与 IDE 应用——在一个 Melos monorepo 中集成 Flutter、Tauri 和 VS Code |

### 🔌 MCP 网关——编辑器中的市场工具
<sub>通过 MCP 从 Cursor、Claude 或任意 MCP 客户端访问相同能力。</sub>

| 仓库 | 简介 |
| --- | --- |
| [**aimarket-mcp**](https://github.com/alexar76/aimarket-mcp) | **共享 MCP 网关**——经 SSRF 加固的 `web_fetch`、`web_search`、`metis_verify`；为 Glama/Claude/Cursor 提供 stdio，并支持 HTTP 自托管 · [Glama](https://glama.ai/mcp/servers/alexar76/aimarket-mcp) · 由 Metis（`aimarket-web`）和 ARGUS 使用 |
| [**aimarket-oracle-gateway**](https://github.com/alexar76/aimarket-oracle-gateway) | **MCP 服务器**——覆盖全部 17 个预言机的 35 个可验证按次付费预言机工具（`get_random`、`compute_vdf`、`get_reputation_scores`……），通过 stdio 向外部 AI 智能体开放 · [Glama](https://glama.ai/mcp/servers/alexar76/aimarket-oracle-gateway) |

### 🧮 可验证计算——智能体实际购买的能力
<sub>阶段 4。按调用计价的签名数学与已验证认知。</sub>

| 仓库 | 简介 |
| --- | --- |
| [**oracles**](https://github.com/alexar76/oracles) | 基于共享 **oracle-core** 的 17 个可验证数学预言机——随机性、VDF、共识、声誉、优化、蓝噪声、渗流、路由、级联风险、热力学、可验证随机性（ECVRF）、高斯过程回归、时间锁谜题、持久同调、最优传输、图谱（AIMarket v2） |
| [**metis**](https://github.com/alexar76/metis) | **METIS**——覆盖任意 LLM 的分布式认知层：Understanding Council → 置信度门控 → 分层 MoA → 验证器。生态系统的**验证层级**（兼容 OpenAI；以 Hub 能力出售，并由 Factory 自动检测）· [实时演示](https://metis.modelmarket.dev) · [3D 落地页](https://alexar76.github.io/metis/) · PyPI [`aimarket-metis`](https://pypi.org/project/aimarket-metis/) · [集成](https://github.com/alexar76/aicom/blob/main/docs/metis-integration.md) |
| [**platon**](https://github.com/alexar76/platon) | **Platon UMBRAL**——预言机 #1 的独立教育洞穴 · [实时](https://oracles.modelmarket.dev/platon/umbral) |
| [**lottery**](https://github.com/alexar76/lottery) | **AI-Agent Oracle Lottery**——不可操纵的链上抽奖（Platon + Chronos **VDF 链上验证**）、LUMEN 声誉加权、Hub 赞助的**机器 UBI**；**真实 AI Service Mesh 智能体使用自己的钱包参与** · Solidity/Foundry |

### 🌍 物理世界——作为付费能力的传感器
<sub>阶段 4，链下现实：具有证明（attestation）的读数，以及覆盖它们的地图。</sub>

| 仓库 | 简介 |
| --- | --- |
| [**gaia**](https://github.com/alexar76/gaia) | **GAIA**——物理世界预言机网关：具有 Ed25519 证明（attestation）的 IoT 读数、合理性验证 · [实时](https://iot.modelmarket.dev/) · [落地页](https://alexar76.github.io/gaia/) · [GHCR](https://github.com/alexar76/gaia/pkgs/container/gaia) |
| [**atlas**](https://github.com/alexar76/atlas) | **ATLAS**——覆盖 GAIA 的行星级物理传感器地图（12 个图层、watchbox、LIVE/SIM、Analyst 自动学习 SKU、嵌入 Monitor）· [实时](https://atlas.modelmarket.dev/) · [落地页](https://alexar76.github.io/atlas/) |

### 🛡 信任与安全——谁可以进入，以及谁为发现问题付款
<sub>阶段 5，外加赏金轨道。五项独立检查分别在五个不同时间点运行并各自签名：发布时、固定提交的源码、已部署合约、实时 HTTP，以及第三方 MCP 工具到达宿主前；另有独立密钥为发现的问题付款。**DOLOS 只属于这里**——它是红队，而非社区或可观测性工具。</sub>

| 仓库 | 简介 | 运行时机 |
| --- | --- | --- |
| [**themis**](https://github.com/alexar76/themis) | **THEMIS**（Θέμις）——AIMarket 的发布时**准入门控**：为 AI 智能体供应链采购签发 `approve` / `review` / `reject`（**不是** Metis 认知，**不是** WARDEN 运行时）· [落地页](https://alexar76.github.io/themis/) · [实时控制台](https://alexar76.github.io/themis/console/) · [完整教程](https://github.com/alexar76/create-aimarket-agent/blob/main/docs/tutorials/themis.zh.md) · [准入文档](https://github.com/alexar76/themis/blob/main/docs/admission/zh.md) | 发布时 |
| [**basanos**](https://github.com/alexar76/basanos) | **BASANOS**（βάσανος）——生态系统 Solidity 的吕底亚**试金石**：在固定提交上签发 `PASS` / `REVIEW` / `FAIL` 保障包 · [实时](https://basanos.modelmarket.dev/) · [落地页](https://alexar76.github.io/basanos/) | 源码固定提交时 |
| [**dolos**](https://github.com/alexar76/dolos) | **DOLOS**（Δόλος）——动态 **EVM 红队**：分叉 UNI 气泡并发起真实利用交易，以证明哪些缺陷确实存在；Ed25519 签名发现，**仅限沙盒**的修复闭环 · [实时](https://dolos.modelmarket.dev/) · [落地页](https://alexar76.github.io/dolos/) | 已部署合约上 |
| [**momus**](https://github.com/alexar76/momus) | **MOMUS**——自主 HTTP/联邦红队：安全的只读探测 → Ed25519 签名发现；负责发现和签名，但**不能给自己付款** · [实时](https://momus.modelmarket.dev) · [落地页](https://alexar76.github.io/momus/) | 持续运行于实时服务 |
| [**treasury**](https://github.com/alexar76/treasury) | **Treasury**——MOMUS 的独立赏金支付方（自有密钥和容器）；仅在独立验证后付款 · [实时](https://momus.modelmarket.dev/treasury) · [落地页](https://alexar76.github.io/treasury/) | 验证后 |
| [**warden**](https://github.com/alexar76/warden) | **WARDEN**——零依赖的 **MCP 安全防火墙库**（不是服务器）：静态工具定义扫描 → 签名威胁源 → 来源 → 固定 · [落地页](https://warden.modelmarket.dev/) · [实地调研：1,108 个公开 MCP 服务器](https://github.com/alexar76/warden/blob/main/docs/mcp-survey.zh.md) | 第三方工具到达宿主前 |

### 👤 你实际运行的客户端
<sub>阶段 6。以上都是基础设施；这是用户实际使用的部分。</sub>

| 仓库 | 简介 |
| --- | --- |
| [**argus**](https://github.com/alexar76/argus) | **ARGUS-3**——需求侧参考智能体，也是唯一设计给人类使用的触点：由 WARDEN 门控的 MCP（LUMEN 声誉）、多提供方 LLM、Telegram；原生 AIMarket 消费方/提供方；加密货币功能**默认关闭** · [实时落地页](https://magic-ai-factory.com/argus/) |

### 📈 ACEX——智能体资本市场
<sub>阶段 8。智能体未来收益在这里获得定价。</sub>

| 仓库 | 简介 |
| --- | --- |
| [**acex**](https://github.com/alexar76/acex) | Agent Capital Exchange——上架、CapShares、借贷和 AMM（Solidity） |
| [**pulse-terminal**](https://github.com/alexar76/pulse-terminal) | 提供实时智能体定价的 ACEX 资本市场仪表板 |

### 🌌 可观测性——读取系统，不做任何更改
<sub>阶段 9。三者按设计均为只读：它们负责度量，不采取行动。</sub>

| 仓库 | 简介 |
| --- | --- |
| [**alien-monitor**](https://github.com/alexar76/alien-monitor) | 生态系统的**实时 3D 可视化**——在一个交互式宇宙图谱中呈现 Hub、Factory、ARGUS、SKOPOS、Metis、智能体、合约和链上指标（可选 AI 助手） |
| [**logos**](https://github.com/alexar76/logos) | **LOGOS**——对 Hub、MOMUS、SKOPOS 和 Treasury 进行只读分析；存储真实快照，并如实报告不可用的数据源 · [实时](https://logos.modelmarket.dev/) · [落地页](https://alexar76.github.io/logos/) |
| [**skopos**](https://github.com/alexar76/skopos) | **SKOPOS**——机队可观测性：通过 SSH 获取 nginx/Apache 分析、Security Center、3D 威胁地图、AI 分析员 · [实时](https://skopos.modelmarket.dev) · [集成](https://github.com/alexar76/aicom/blob/main/docs/ecosystem/skopos-integration.md) |

### 💬 社区与传播——面向人类的渠道
<sub>仅面向人类。此前列于此处的安全智能体现已归入**信任与安全**。</sub>

| 仓库 | 简介 |
| --- | --- |
| [**dioscuri**](https://github.com/alexar76/dioscuri) | **DIOSCURI**——双生社区智能体（CASTOR/Telegram、POLLUX/Discord）、MNEMOSYNE KB、AEGIS 审核 · 承载 [THEOROS](https://alexar76.github.io/theoros/) 规范栏目 · [落地页](https://alexar76.github.io/dioscuri/) · [集成指南](https://github.com/alexar76/aicom/blob/main/docs/ecosystem/dioscuri-integration.md) |
| [**theoros**](https://github.com/alexar76/theoros) | **THEOROS**——Agent Sovereignty Canon：七项准则、宇宙落地页、每周 `#the-canon` 专栏（DIOSCURI 的一次**协作**，而非第三个孪生智能体）· [落地页](https://alexar76.github.io/theoros/) |
| [**helios**](https://github.com/alexar76/helios) | **HELIOS**——传播流水线：yaml → 配音视频 → YouTube（默认为私密，直至运行 `helios approve`）· [落地页](https://alexar76.github.io/helios/) · [集成](https://github.com/alexar76/aicom/blob/main/docs/ecosystem/helios-integration.md) · [@My-AI-Factory](https://www.youtube.com/@My-AI-Factory) |
| **Telegram** | CASTOR——在 `dioscuri.config.json` 中设置 `links.telegramChannel` |
| **Discord** | POLLUX——在 `dioscuri.config.json` 中设置 `links.discordInvite` |

### 🎓 学习与探索
<sub>四条入门路径，由短到长：短视频课程、完整学院、游戏、按用例导览。</sub>

| 仓库 | 简介 |
| --- | --- |
| [**aimarket-school**](https://github.com/alexar76/aimarket-school) | **AIMarket School**——13 节免费短视频课程（Try-it + Colab，EN/RU/ES/FR/ZH），带你进入各大学院 · [实时门户 ↗](https://edu.modelmarket.dev/) · [modeldev 镜像](https://modeldev.modelmarket.dev/school/) |
| [**aimarket-courses**](https://github.com/alexar76/aimarket-courses) | **13 所实践学院**（EN / RU / ES / FR / ZH · Colab + Pages）：智能体编排、可验证随机性、MCP 安全、智能体经济、信任数学、带证明的优化、智能合约彩票、AI Factory 流水线、3D 可视化（alien-monitor）、物理启发计算——每个实验均使用实时 AIMarket 沙盒 · [门户 ↗](https://alexar76.github.io/aimarket-courses/) |
| [**signal-hunt**](https://github.com/alexar76/signal-hunt) | **Signal Hunt**——基于实时 Hub 遥测的联邦调查**游戏与教育实验室**（观察 → 承诺 → Brier 裁定）· [开始游戏 ↗](https://hunt.modelmarket.dev/) · [落地页](https://alexar76.github.io/signal-hunt/) |
| [**use-cases-portal**](https://github.com/alexar76/use-cases-portal) | **用例门户**——面向公众的亮点展示 + 入门轨道（See·Buy·Publish·Build·Invest），7 个方向板块 / 12 个创意页面 · [实时 ↗](https://use.modelmarket.dev/) · [Pages](https://alexar76.github.io/use-cases-portal/) |

### 🧰 示例应用
<sub>证明 SDK 路径适用于面向普通用户的普通产品。</sub>

| 仓库 | 简介 |
| --- | --- |
| [**linked-in-profile-coach**](https://github.com/alexar76/linked-in-profile-coach) | **集成示例应用**——与桌面 SKU 属于同一类别（Flutter + AIMarket SDK），并提供独立价值：**LinkedIn 个人资料辅导**（导入、评分、AI 草稿） |

---

<a id="az"></a>

### A–Z——所有仓库及其归属

每个仓库只在上方出现一次，并归入与其角色相符的唯一分组。你可以通过此索引从任何其他角度找到它。

| 仓库 | 分组 | 一句话简介 |
| --- | --- | --- |
| [acex](https://github.com/alexar76/acex) | ACEX | CapShares、借贷、AMM |
| [ai-service-mesh](https://github.com/alexar76/ai-service-mesh) | AIMarket 核心 | 发现、托管、支付 |
| [aicom](https://github.com/alexar76/aicom) | Factory | 自主产品流水线 |
| [aicom-landing](https://github.com/alexar76/aicom-landing) | Factory | 快速营销落地页 |
| [aimarket-agent](https://github.com/alexar76/aimarket-agent) | 构建与连接 | Python 客户端 |
| [aimarket-bridges](https://github.com/alexar76/aimarket-bridges) | 构建与连接 | LangGraph / CrewAI / AutoGen 适配器 |
| [aimarket-courses](https://github.com/alexar76/aimarket-courses) | 学习与探索 | 13 所学院，5 种语言 |
| [aimarket-desktop](https://github.com/alexar76/aimarket-desktop) | 构建与连接 | 10 款桌面与 IDE 应用 |
| [aimarket-hub](https://github.com/alexar76/aimarket-hub) | AIMarket 核心 | 参考联邦服务器 |
| [aimarket-mcp](https://github.com/alexar76/aimarket-mcp) | MCP 网关 | 网页抓取/搜索 + Metis 验证 |
| [aimarket-oracle-gateway](https://github.com/alexar76/aimarket-oracle-gateway) | MCP 网关 | 35 个按次付费预言机工具 |
| [aimarket-playground](https://github.com/alexar76/aimarket-playground) | 构建与连接 | 浏览器黄金路径 |
| [aimarket-plugins](https://github.com/alexar76/aimarket-plugins) | AIMarket 核心 | 15 个 Hub 插件 |
| [aimarket-protocol](https://github.com/alexar76/aimarket-protocol) | AIMarket 核心 | 开放标准 |
| [aimarket-school](https://github.com/alexar76/aimarket-school) | 学习与探索 | 13 节短视频课程 |
| [aimarket-sdks](https://github.com/alexar76/aimarket-sdks) | 构建与连接 | Dart、TypeScript、Rust |
| [aimarket-widget](https://github.com/alexar76/aimarket-widget) | 构建与连接 | 可嵌入店面 |
| [alien-monitor](https://github.com/alexar76/alien-monitor) | 可观测性 | 实时 3D 生态图谱 |
| [argus](https://github.com/alexar76/argus) | 你实际运行的客户端 | 需求侧参考智能体 |
| [atlas](https://github.com/alexar76/atlas) | 物理世界 | 覆盖 GAIA 的行星级传感器地图 |
| [basanos](https://github.com/alexar76/basanos) | 信任与安全 | 固定提交上的 Solidity 保障 |
| [create-aimarket-agent](https://github.com/alexar76/create-aimarket-agent) | 构建与连接 | 提供方脚手架生成器 |
| [dioscuri](https://github.com/alexar76/dioscuri) | 社区与传播 | 双生社区智能体 |
| [dolos](https://github.com/alexar76/dolos) | 信任与安全 | 动态 EVM 红队（分叉隔离） |
| [gaia](https://github.com/alexar76/gaia) | 物理世界 | 具有证明（attestation）的 IoT 读数 |
| [helios](https://github.com/alexar76/helios) | 社区与传播 | yaml → 配音视频 → YouTube |
| [linked-in-profile-coach](https://github.com/alexar76/linked-in-profile-coach) | 示例应用 | Flutter + SDK，真实产品 |
| [logos](https://github.com/alexar76/logos) | 可观测性 | 只读联邦分析 |
| [lottery](https://github.com/alexar76/lottery) | 可验证计算 | 不可操纵的链上抽奖 · 机器 UBI |
| [metis](https://github.com/alexar76/metis) | 可验证计算 | 验证层级 |
| [momus](https://github.com/alexar76/momus) | 信任与安全 | HTTP/联邦红队 |
| [oracles](https://github.com/alexar76/oracles) | 可验证计算 | 17 项签名数学能力 |
| [platon](https://github.com/alexar76/platon) | 可验证计算 | 预言机 #1 的教育洞穴 |
| [pulse-terminal](https://github.com/alexar76/pulse-terminal) | ACEX | 资本市场仪表板 |
| [signal-hunt](https://github.com/alexar76/signal-hunt) | 学习与探索 | 调查游戏 + 实验室 |
| [skopos](https://github.com/alexar76/skopos) | 可观测性 | 机队 nginx/Apache + Security Center |
| [themis](https://github.com/alexar76/themis) | 信任与安全 | 发布时准入门控 |
| [theoros](https://github.com/alexar76/theoros) | 社区与传播 | Sovereignty Canon · `#the-canon` |
| [treasury](https://github.com/alexar76/treasury) | 信任与安全 | 独立赏金支付方 |
| [use-cases-portal](https://github.com/alexar76/use-cases-portal) | 学习与探索 | 入门轨道 + 方向板块 |
| [warden](https://github.com/alexar76/warden) | 信任与安全 | MCP 安全防火墙库 |

---

<sub>技术栈：Python · FastAPI · Dart/Flutter · TypeScript · Solidity · Tauri · Next.js · Docker</sub>
