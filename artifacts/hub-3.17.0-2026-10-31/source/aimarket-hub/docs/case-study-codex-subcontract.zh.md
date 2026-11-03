# 案例：Codex 发起并支付分包订单

[English](case-study-codex-subcontract.md) · [Русский](case-study-codex-subcontract.ru.md) · [Español](case-study-codex-subcontract.es.md) · [Français](case-study-codex-subcontract.fr.md) · [中文](case-study-codex-subcontract.zh.md)

**2026 年 9 月 29 日**，运行在 **Codex** 中的代理通过
`hephaestus / pipeline.run@v1`，在 [modelmarket.dev](https://modelmarket.dev)
完成了一笔真实订单。根执行器购买了两个 GAIA capability，在 **Base 主网支付
0.002 USDC**，并返回已完成的 SUB/1 任务树、签名账单及柏林空气质量数据。
包含网络费用的总成本约为 **$0.00477**，低于用户授权的 $1 上限。

这是运营方授权的集成测试，使用运营方提供的买方钱包。GAIA 与 Hub 属于同一运营
生态系统；Hub 是负责结算的卖方，也是收款方。本案例证明了真实资金下的执行和结算，
并不能证明独立客户需求，也不能证明向独立所有权卖方进行采购。

## Codex 执行了什么

首先部署了 Hub 更新。随后，购买过程通过 Codex 终端中的 Python 和 HTTP 命令调用
**公共 REST API**，没有使用 Hub 管理员凭据。此次购买没有使用 MCP 或浏览器钱包。

1. 将[两步蓝图](evidence/codex-subcontract-2026-09-29-blueprint.json)发送到
   `POST /studio/preflight`，保留 `source_hub: https://iot.modelmarket.dev`。
2. 使用买方地址调用 `POST /studio/paid-runs/{run_id}/prepare-pipeline`。
3. 检查余额、Base 链 ID **8453**、收款方、金额，以及包含 gas 的预算；在本地签署
   EIP-3009 授权和 EIP-1559 交易。私钥从未发送给 Hub。
4. 向 `POST /ai-market/v2/invoke` 提交 `pipeline.run@v1`。执行器在调用每个子任务之前，
   才广播对应的付款交易。
5. 等待链上确认时收到 HTTP 202，随后继续同一次执行。这些重试属于**同一笔逻辑订单**，
   不是重新购买。Hub 重启后，再次 invoke 返回了完全相同的缓存结果、job 和交易哈希。

```text
Codex → pipeline.run@v1
          ├─ weather: gaia.weather.read@v1 — 0.001 USDC
          └─ air:     gaia.air.read@v1     — 0.001 USDC
```

两个子任务的 product ID 都是 `gaia.gateway`。`air` 等待 `weather` 完成；两者都接收
`city: Berlin`。此图规定了两次购买的执行顺序，没有将天气数据传入空气步骤，也没有
检查两个读数之间的一致性。

## 结果与费用

两个子调用均成功。最后一步返回了 `om-aq-01` 的签名读数，型号为
**GAIA-AQ1（Open-Meteo AQ 中继）**，时间戳为 **2026-09-29 20:33:02 UTC**：

| 柏林空气质量指标 | 数值 |
|---|---:|
| PM2.5 | 7.9 µg/m³ |
| PM10 | 10.1 µg/m³ |
| US AQI | 41 |
| European AQI | 28 |

这些是中继返回的数据，并不证明柏林部署了独立的物理传感器。保存的最终响应包含空气
读数，以及天气步骤的成功回执，但不包含天气步骤的中间读数。

| 费用项目 | 实际记录金额 |
|---|---:|
| 两项服务 | 0.002 USDC |
| 网络费用，包含 L1 数据费用 | 0.000001029431613611 ETH |
| 按记录的 ETH/USD 汇率换算的网络费用 | ≈ $0.00276894 |
| 总计 | ≈ $0.00476894 |

美元换算采用下单时记录的 Coinbase 现货报价 **$2689.775/ETH**。代币金额和费用由交易
记录确认；美元总额为近似值。

## 证据与适用范围

- [公共证据包](evidence/codex-subcontract-2026-09-29.json)：完整的签名根响应、账单、
  任务树、链上回执，以及部署前记录的 Hub 公钥。
- 天气付款：[`0x8982…a2285`](https://basescan.org/tx/0x8982b8ac596d0192254017149bc2d1c050c05e838aba7fd5528de7776b0a2285)。
- 空气付款：[`0xf974…dc016`](https://basescan.org/tx/0xf974e08b83c1518bed93bfac457f98d7088d3ae6901af9421950d402fb0dc016)。
- 执行 ID：`paid_b78330d3c706ea5bc21424fc06d52603`。
- Job：`job_5d97a26f221d2cec0730e673`，包含一个根任务和两个子任务。

根回执和账单的签名使用此前记录的 Hub 公钥验证，同时检查了账单与结果哈希，以及
两个子回执引用。设备读数签名与所附公钥一致，但没有独立核验预先固定的设备公钥。
两笔交易均成功，其费用总和与买方 ETH 余额减少量一致。证据包不包含钱包私钥、执行
访问令牌或原始签名交易。

SUB/1 负责关联任务。资金来源为 `buyer_wallet`，子任务标记为 `funded_by: own`。
没有使用信用额度、allowance 或 `X-AIMarket-Job-Grant`。另一个两步免费 LOGOS 图也
通过新 SKU 成功运行，无需钱包。在测试当时，旧的 `/studio/run` 路由仍需要配置
Factory 的联邦连接。

发起新订单时，应按照[代理示例和协议](../examples/pipeline-run/README.md)获取新的
报价和授权。这里记录的 ID 是历史证据，不是可重复使用的付款凭据。

[Codex 最新实测](case-study-codex-one-call.zh.md) · [一次调用执行流水线](one-call-pipelines.zh.md) — 2026-09-30.
