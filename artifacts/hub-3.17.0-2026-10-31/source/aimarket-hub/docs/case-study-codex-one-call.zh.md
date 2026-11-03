# Codex：一次客户端操作，两个付费分包任务

[English](case-study-codex-one-call.md) · [Русский](case-study-codex-one-call.ru.md) · [Español](case-study-codex-one-call.es.md) · [Français](case-study-codex-one-call.fr.md) · [中文](case-study-codex-one-call.zh.md)

**2026 年 9 月 30 日**，Codex 使用新的 `await run_pipeline(...)`、同一个运营方提供的钱包及 **$1 总预算**，再次完成 GAIA 分包测试。Hub 运行 `modelmarket-hub:prod-20260930-onecall`。两个子任务均成功，客户端自动等待确认。服务费为 **0.002 USDC**，包含 gas 的实测总费用为 **≈ $0.00468270**。

## 流程与实际请求

客户端调用 `POST /studio/prepare-pipeline` 提交图和钱包，核对图、付款条件、余额及费用预留，在本地签名并私密保存付款包，然后调用 `pipeline.run@v1`。Hub 没有收到管理员凭据或私钥。购买通过 Codex 终端中的 Python 使用公共 REST API 完成，不是 MCP。调用方只等待一次 SDK 操作，无需手动运行 resume。

| 顺序 | Hub 请求 | HTTP | 状态 |
|---|---|---:|---|
| 1 | `POST /studio/prepare-pipeline` | 200 | `ready` |
| 2 | `POST /ai-market/v2/invoke` | 202 | `active` |
| 3 | `POST /ai-market/v2/invoke` | 202 | `active` |
| 4 | `POST /ai-market/v2/invoke` | 200 | `completed` |

付费测试实际发送了**四次 Hub 请求**，并非严格两次。区块链 RPC 与汇率请求另计。第一次准备响应同时给出报价与授权。每次 202 都继续同一个 run，使用完全相同的签名包。全程只有一个根 job 和两个成功子调用。完成后，`run_pipeline(resume=True, ...)` 返回相同的本地缓存结果，**额外 Hub 请求为零**。测试与证据核验共用时 11.872 秒；这是观测结果，不是延迟保证。

## 图与结果

图依次购买 `gaia.gateway` 的 `gaia.weather.read@v1` 和 `gaia.air.read@v1`，保留 `source_hub: https://iot.modelmarket.dev`，输入为 `city: Berlin`。`air` 等待 `weather` 完成，但没有接收天气数值。最终结果来自 **GAIA-AQ1（Open-Meteo AQ 中继）** 设备 `om-aq-01` 的签名读数，时间为 **2026-09-30 04:24:34 UTC**。证据记录天气步骤成功，但没有包含其中间读数。这是中继数据，并非柏林部署了独立物理传感器的证明。

| 指标 | 数值 |
|---|---:|
| PM2.5 | 8.8 µg/m³ |
| PM10 | 11.1 µg/m³ |
| US AQI | 33 |
| European AQI | 24 |

## 预算与结算

付款方为 `0x6E94c380d908531f9822035d6cc4c8D2B0186C9c`，USDC 收款方为 `0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a`。使用 Base 主网上现有的 USDC，chain ID 为 8453。买方选择 ETH/USD 上限 6000；最后记录的保守费用估算为 $0.1195256567368，低于 $1。实际美元成本按测试期间 Coinbase 报价 **$2673.555/ETH** 折算。行情与估算都不是链上强制执行的绝对美元上限。

| 费用 | 金额 |
|---|---:|
| 服务 / USDC | 0.002 USDC |
| 网络费用 (L2 + L1) | 0.000001003418744789 ETH |
| 网络费用 / USD | ≈ $0.00268270 |
| 总计 / USD | ≈ $0.00468270 |

## 附加测试与验证

两步免费 LOGOS 图通过同一 SDK 成功执行，无需钱包、RPC 或汇率上限，只发送两次 Hub 请求。总预算 $0.003 的付费图通过服务报价检查，但因手续费预留不足被客户端拒绝：只有一次准备请求，没有根调用或付款。**84 项本地测试**与 **4 项 Anvil 付款测试**通过，覆盖响应丢失、相同请求重试、签名后无签名器恢复、gas 预算拒绝、错误链或授权、文件锁，以及子任务失败终态。

CLI 也在生产环境完成了免费图，随后在不提供钱包私钥的情况下恢复执行，返回完全相同的已保存结果。

两笔链上交易均成功。USDC 金额与网络费用同买方余额变化一致。根回执和账单签名使用测试前记录的 Hub 公钥验证，并核对账单/结果哈希和两个子回执引用。空气读数签名按所附公钥验证，没有独立固定设备身份公钥。公共证据包含签名结果与链上回执，不含私钥、执行访问令牌或原始签名付款交易。

这仍是运营方授权的集成测试：GAIA 与 Hub 属于同一运营生态，Hub 是负责收款的卖方。它证明真实付款与分包执行，不证明独立客户需求。SUB/1 关联任务，资金来源为 `buyer_wallet`，子任务为 `funded_by: own`，未使用信用 allowance。没有重新部署智能合约。免费 SDK 测试不代表单独配置的旧 `/studio/run` 路由也已验证通过。

## 证据与复现

- [JSON](evidence/codex-one-call-2026-09-30.json) · [Blueprint](evidence/codex-one-call-2026-09-30-blueprint.json)
- [API / SDK](one-call-pipelines.zh.md)
- `run_id`: `paid_ce7dfb28ec21c0ffbc6f65884929aeec`
- `job_id`: `job_dd54651f9104c5c5ac31cc4e`
- `weather`: [0x5ecc8cf51aec0618e730d130ce9d61003cbdccc0b1814d5a39d6c67228c2543e](https://basescan.org/tx/0x5ecc8cf51aec0618e730d130ce9d61003cbdccc0b1814d5a39d6c67228c2543e)
- `air`: [0x5ef82ffce3e6d7a5a4866cf492ae2db5b44df238b85ad361ab4641de61304fa1](https://basescan.org/tx/0x5ef82ffce3e6d7a5a4866cf492ae2db5b44df238b85ad361ab4641de61304fa1)

---

外部代理接入更新（3.9.0）的后续验证：175 项针对性测试与 4 项本地 Anvil 支付测试通过。干净安装的客户端通过 SDK 用两次 Hub 请求完成免费图；MCP prepare/invoke/status 完成另一个免费图。原付费订单仅通过两次 GET（清单与根状态）恢复，无需钱包私钥或 RPC。Hub 收据由 SDK 自身验证。本轮未新增 mainnet 支付。wheel 由 Hub 分发，其 SHA-256 位于已签名清单中；尚未发布到 PyPI。

[JSON](evidence/agent-rails-2026-09-30.json)

## 后续：独立卖家协议，3.10.1

Codex 添加了 SELLER-OP/1，并部署 Hub 及迁移 44–45。链操作指南详细说明协议和边界。**223 项针对性测试及 6 个本地 Anvil 场景通过**，其中两个场景使用一次性代币，在独立 Hub 间结算，一个模拟卖家响应丢失。每个独立卖家场景中，买家仅支付一次，恰好 4,000 个代币最小单位；卖家创建并核销账单。这是本地链集成测试，不是新的主网购买。

生产验证包括签名清单、wheel、五种语言指南、免费 MCP 链、使用两个主要请求的免费 SDK 链，以及仅通过 GET 恢复原付费订单。测试钱包没有新增主网付款。本地 weather.witness listing 没有兼容的直接收款路径：准备现在于执行和付款前返回 409/settlement_route_unsupported，而不是 500；该 SKU 原有基于信用的 SUB/1 协议不变。本次未升级或购买独立的生产 peer；该路径在两个受控 Hub 和 Anvil 上验证。

[脱敏验证证据](evidence/seller-operations-2026-09-30.json)。不公开私钥、操作 token 或签名付款包。
