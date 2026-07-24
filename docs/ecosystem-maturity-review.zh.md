# 生态系统成熟度评审 — 外部批评与行动计划

**日期：** 2026-07-12  
**目的：** 对第三方 scorecard 做诚实的验证，并记录**当前可在仓库内执行的具体行动**（in-repo）与运营方/供应商的阻塞项之别。

**另见：** [known-issues.md](known-issues.md) · [pet-project-trust.md](pet-project-trust.md) · [oracles crypto-maturity](../oracles/docs/crypto-maturity.en.md)

---

## 这份批评公允吗？

| 组件 | 外部评分 | 结论 | 一句话理由 |
|------|---------|------|-----------|
| **1. AI-Factory** | 7.8/10 | **基本公允** | 约 2 个月内做出真正的多智能体 pipeline + gates 令人印象深刻；KI-3/KI-2/KI-4 与已交付的 MVP 与批评一致。 |
| **2. Metis** | 8.0/10 | **公允** | 设计扎实（置信度 gate、验证路径）；分布式集群与对抗性覆盖尚处早期。 |
| **3. Oracles ×17** | 6.5–6.7/10 | **公允** | 广度 > 深度；crypto 未加固（[KI-6](known-issues.md#ki-6--oracle-family-cryptographic-maturity-not-production-hardened)）。 |
| **4. ARGUS-3** | 7.5/10 | **公允** | WARDEN 是真实的，且针对明显的投毒做过测试；复杂攻击（编码、运行时外泄、模型侧绕过）尚未封堵。 |
| **5. Hub + Protocol** | 7.2/10 | **公允** | v2 规范 + 参考 hub 很扎实；大规模的联邦/微支付未经证明；外部采用 ≈ 0。 |
| **6. Alien Monitor** | 8.0/10 | **公允** | 打磨到位的可观测性；认证模型已修复；不是金融信任层。 |
| **7. 支持组件（HELIOS、DIOSCURI、桌面端、widget）** | 6.8–7.3/10 | **公允** | 有用的卫星组件；相对 Factory/Hub/ARGUS 属于次要；DIOSCURI = devrel + 参考安全演示。 |

**总体：** 该评审在**方向上是正确的**。评分是主观的，但*所点名的风险*与我们已在 KI-* 和 pet-project trust 文档中跟踪的一致。这里没有任何 FUD — 就是我们公开声明的那套 pre-mainnet 姿态。

---

## 行动矩阵

| ID | 组件 | 行动 | 负责人 | 状态 |
|----|------|------|-------|------|
| **A-1** | Factory | 记录 **minimal vs full** pipeline 配置；为 MVP landing 推荐 minimal | in-repo | [`factory-pipeline-profiles.md`](factory-pipeline-profiles.md) |
| **A-2** | Factory | 将示例产出标注为 **MVP 层级**；链接 build 回放 | in-repo | [`sample-output/README.md`](sample-output/README.md) |
| **A-3** | Factory | 明确跟踪生产化差距 | in-repo | known-issues 中的 **KI-7** |
| **A-4** | Metis | 记录分布式 + 对抗性差距 | in-repo | [`metis/docs/en/MATURITY.md`](../metis/docs/en/MATURITY.md) |
| **A-5** | Metis | 播种对抗性 gate 回归测试 | in-repo | `metis/tests/test_adversarial_gates.py` |
| **A-6** | Metis | 跟踪集群 soak + red-team 基准 | in-repo | **KI-8** |
| **A-7** | Oracles | Crypto 诚实度（Chronos、混合 PQC、原型层级） | in-repo | **KI-6** + crypto-maturity 文档 ✅ |
| **A-8** | ARGUS | WARDEN 的局限 + 复杂攻击差距 | in-repo | [`argus/docs/security-warden.md`](../argus/docs/security-warden.md) §Limitations |
| **A-9** | ARGUS | 对抗性 fixture 测试（混淆注入） | in-repo | `argus/test/adversarial-warden.test.ts` |
| **A-10** | ARGUS | 跟踪 red-team / bug bounty 路径 | in-repo | **KI-9** |
| **A-11** | Hub | 联邦/采用诚实度 + 边界情况计划 | in-repo | [`aimarket-hub/docs/MATURITY.md`](../aimarket-hub/docs/MATURITY.md) + **KI-10** |
| **A-12** | Monitor | 不变 — 维持层级标签「可观测性，而非信任」 | — | pet-project-trust 表 |
| **A-13** | 支持组件 | 在 pet-project-trust 中标为 **次要 / devrel** 层级 | in-repo | pet-project-trust.md |
| **A-14** | All | 从 ROADMAP + README 链接 | in-repo | ROADMAP.md |

**仅限运营方（无法仅靠文档解决）：** KI-2 审计、KI-3 负载测试、KI-4 multisig、KI-6 crypto 审计、在第三方 hub 上的生产化采用。

---

## 逐组件细节

### 1. AI-Factory (7.8)

**批评成立：** pipeline 是最大的子系统；条件式 agents/director/gates 增加了运维面；Docker self-host 是一项优势；生产化 checklist（负载、multisig、审计）明确处于开放状态；公开演示偏向 landing/MVP 店面（[`docs/sample-output/`](sample-output/)）。

**我们不反对把它称为面向 pet project 的「over-engineered」** — 默认的 fragment 栈会跑 PM → 架构师 → dev → QA → 安全 → 部署 → 营销。这对于展示型 build 是合适的，对单个 landing page 则过重。

**行动：** A-1、A-2、A-3，`./scripts/quickstart.sh` 提供一条命令的演示。

### 2. Metis (8.0)

**批评成立：** 分布式模式存在（[`metis/docs/en/DISTRIBUTED.md`](../metis/docs/en/DISTRIBUTED.md)），但多区域集群需要 soak 测试；置信度 gate 对*结构化*信号是 fail-closed 的，但信任 council 赋予的 `confidence` — 自评分很高的细微幻觉可能通过；除非 Factory 强制扣费，否则经济计量只是建议性的。

**行动：** A-4、A-5、A-6；基准已注明「置信度信号，而非精度上限」（[`metis/docs/benchmarks/`](../metis/docs/benchmarks/)）。

### 3. Oracles (6.5–6.7)

**批评成立：** 已在 [crypto-maturity.en.md](../oracles/docs/crypto-maturity.en.md) 中处理。Platon 随机性 + Lumen 声誉需要与 Chronos VDF 同等级别的外部评审。

### 4. ARGUS (7.5)

**批评成立：** WARDEN 能抓住教科书式的投毒（[`argus/test/warden.test.ts`](../argus/test/warden.test.ts)）；测试中的 `allowUnknownServers: true` 反映了真实的宽松默认值；当 LUMEN 不可达时声誉退化为中性（自治优先于 fail-closed）。

**行动：** A-8、A-9、A-10。

### 5. Hub + Protocol (7.2)

**批评成立：** 协议 v2 是正确的基础；联邦爬虫 + 通道在参考部署中可用；没有有意义的第三方 hub 网格或生产化的调用量 → 边界情况（罚没同步、通道竞态、过期 manifest）大多停留在理论层面。

**行动：** A-11、KI-10。

### 6. Alien Monitor (8.0)

**批评成立：** 强大的 UX 与 LIVE 拓扑；批评有限。不能替代经济安全。

### 7. 支持工具 (6.8–7.3)

**批评成立：** HELIOS、widget、桌面端集成是真实的，但**次要**。DIOSCURI（Castor/Pollux）是公开聊天上的 **devrel + 参考加固** — 有价值，但不是生产化的智能体基础设施。

**行动：** A-13 — 层级标签，不在生态系统 landing 上过度推销。

---

## 对外口径（供公开使用）

> *自托管的 AI 智能体经济 — 研究/原型层级。演示与协议接线扎实；在达到 mainnet 规模的 TVL 之前，需要外部审计、负载测试与 crypto 评审。*

---

> 🌐 语言： [English](ecosystem-maturity-review.en.md) · [Русский](ecosystem-maturity-review.ru.md) · [Français](ecosystem-maturity-review.fr.md) · [Español](ecosystem-maturity-review.es.md) · **中文**
