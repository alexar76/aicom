# AICOM：采购外部诊断服务

> 🌐 [English](factory-subcontracting.md) · [Русский](factory-subcontracting.ru.md) · [Español](factory-subcontracting.es.md) · [Français](factory-subcontracting.fr.md) · [中文](factory-subcontracting.zh.md)

AICOM 由自己的代理团队开发产品。现在，在下一次内部修复之前，公司可以通过 AIMarket 购买范围有限的诊断服务。服务商提供建议，AICOM 开发代理修改代码，现有 QA 检查决定产品能否进入下一阶段。

此功能**默认关闭**。安装代码不会启动真实采购、充值、注册服务商或发送源代码。

## 决策算法

1. 开发任务开始前，选择明确标注源文件的 high/critical 级 QA 问题。
2. 以文件与标题标识问题，并关联最近一次已完成的开发任务。同一任务重放不重复计数。累计三次观察后才可采购：初次生成，以及两次已完成的内部修复。
3. 遇到紧急停止、已有卡住或预算暂停状态、未生成代码，或产品设置了 `external_diagnostics_allowed: false` 时跳过采购。操作员暂停和修复次数限制仍然有效。
4. 使用**一个允许共享的源文件**、问题和验收规则构建请求。请求指纹涵盖代码内容和契约。
5. 使用操作员固定的公钥验证 Hub 签署的 well-known 文档。仅搜索批准的能力，排除演示、不可用服务和不兼容的必填输入，优先选择报价最低的合格服务。
6. 在产品和每日额度内原子预留资金，同时保留完成与 QA 的预算。每个产品最多有一个支付状态未知的订单，每个问题最多尝试两个服务商，同一服务商不重复调用。即使报告被拒绝，也必须先完成新一轮内部修复才能再次购买。
7. 仅调用一次，验证账单收据并验收报告。超时或支付结果不明时保留预留资金，不自动重复付费调用。
8. 将通过验收的报告作为不可信第三方数据交给内部开发代理。开发任务成功后记录下一次 QA 结果。报告本身不会改变产品状态，也不会取消质量检查。

没有合适报价、权限或预算时，继续现有内部修复流程并遵守原有限制。同一问题已接受的诊断不会再次购买。进程重启后，在内部使用前，只有请求指纹仍然一致时才能恢复已保存的报告。

## 配置

将[配置示例](../config/procurement.example.json)复制到 `<AIFACTORY_DATA_ROOT>/config/procurement.json`。

| 参数 | 含义 |
|---|---|
| `enabled` | 配置并测试服务商后设为 `true` |
| `hub_url` | HTTPS Hub 地址；不跟随重定向 |
| `hub_public_key` | 已独立验证并固定的 base64 Ed25519 公钥 |
| `hub_pq_public_key` | 混合签名 Hub 的固定 ML-DSA-65 公钥；仅使用 Ed25519 时留空 |
| `providers` | 最多 10 组允许的 `product_id` / `capability_id` |
| `share_globs` | 相对于各产品代码目录的允许共享路径 |
| `per_call_usd` | 单次采购上限，初始为 $0.25 |
| `per_product_usd` | 每个产品的外部支出与预留上限，$0.50 |
| `per_day_usd` | 共享账本按 UTC 自然日计算的额度，$2.00 |
| `completion_reserve_usd` | 留给内部完成与 QA 的预算，$0.50 |

通过 `AIFACTORY_PROCUREMENT_API_KEY` 提供已充值的独立 credits 账户，并在 Hub 配置余额和权限。本版本不创建或签署 mandate；强制要求 mandate 的账户会拒绝此客户端。必须设置正数 `AIFACTORY_MAX_PIPELINE_COST_USD`。关闭总成本限制并不允许无限采购。

每次符合条件的任务都会重新读取配置。不要把 API 密钥写入 JSON。公司的所有工作进程必须共享数据目录和账本，才能共同遵守每日额度；独立安装的额度相互独立。

首版仅支持由指定 Hub 执行的服务（`source_hub: local`），包括由该 Hub 调用的外部服务端点。不采购联邦报价，也不给服务商提供继续转包的资金。

搜索结果必须明确包含 `credits_eligible: true`。要求直接链上付款到钱包的卖家会被排除。旧版 Hub 如果没有此字段，则不会产生合格报价；应先部署相应 Hub 更新。选择服务商时，必须同时测试 credits 支付兼容性和诊断契约。

## 代码共享与服务契约

服务商必须实现 **`aicom.diagnosis/1`**。普通的 `code.review@v1` 条目并不自动兼容，加入允许列表前必须测试。

请求字段为 `contract`、`issue`、`fingerprint`、`finding`、`files` 和 `acceptance`。`files` 包含一个不超过 16,000 字节的 UTF-8 源文件。允许扩展名：py、ts、tsx、js、jsx、go、rs、java、cs、html、css。隐藏路径、密钥目录、符号链接、路径越界和常见凭证模式会被拒绝。不会发送整个仓库、凭证、需求说明或运行日志。

`share_globs` 使用 Python fnmatch，`*` 可以匹配路径分隔符。因此应设置较小的共享范围。密钥检测是启发式检查，操作员仍须批准可共享的代码目录。

QA 中相对于产品的路径、带有 `code/<product_id>/` 或 `data/code/<product_id>/` 前缀的路径，以及该产品代码目录内的绝对路径，都会规范化为同一标识。目录外的路径会被拒绝。

Hub 响应的 `result` 应采用以下结构；示例引用源代码行 `return 1 / x`：
```json
{
  "contract": "aicom.diagnosis/1",
  "issue": "COPY_FROM_REQUEST",
  "fingerprint": "COPY_FROM_REQUEST",
  "diagnosis": [{
    "file": "app/main.py",
    "line": 2,
    "evidence": "return 1 / x",
    "explanation": "Zero input divides by zero.",
    "suggested_check": "Test divide(0) against the required error contract."
  }]
}
```

必须原样返回请求标识符，并提供 1–5 条诊断。每条引用必须对应已共享文件指定行中的非空原文片段。解释和建议检查均为必填项，各不超过 2,000 个字符。代码版本发生变化时报告会被拒绝。建议不会作为 shell 命令执行。

验收仅确认结构与源码引用有效，不证明诊断正确。开发代理仍须核实，原有测试和 QA 继续生效。账单收据签署的是计费字段，不是诊断文本。系统使用固定公钥验证 Ed25519，以及存在或要求的 ML-DSA-65 签名层。

## 支付、故障与恢复

`state/procurement.sqlite3` 保存订单、请求指纹、报告、预留金额和 QA 结果。执行状态（`in_flight`、`accepted`、`rejected`、`unresolved`）与支付状态（`unknown`、`paid`、`not_charged`）分别记录。

被拒绝的报告仍可能已经付费。此 credits 流程不承诺 Pay-on-Verified 退款。HTTP 错误、缺失或无效收据、断线和工作进程中断都会使支付状态保持未知，并阻止该产品再次采购；只要预算允许，内部工作可以继续。

先核对 Hub 账单，再执行查看或显式对账：
```bash
.venv/bin/python scripts/procurement_orders.py list --product PRODUCT_ID
.venv/bin/python scripts/procurement_orders.py reconcile \
  --order PURCHASE_ID --charged-usd 0.10 \
  --evidence "Hub billing reference and reconciliation reason"
```

`list` 输出使用微美元：100,000 = $0.10。操作其他安装时，在子命令前添加 `--data-root PATH`。对账记录实际扣款及依据，释放预留，不重新调用服务商，也不会生成已验收的报告。只有确认没有扣款后才能填写零。

产品成本限制现在包含**已观察的 LLM 费用、已扣款采购和支付未知的预留金额**。SQLite 串行处理并发采购。前几日尚未解除的预留也占用当前每日额度。LLM 费用按实际观察结果计入，已开始的模型请求仍可能超过剩余估算；这不是对全部 token 成本的严格预授权。

## 验证与版本边界

测试使用真实 Hub 签名模块和模拟 HTTP，不进行真实支付。覆盖开发代理交接、签名一致性、过期报告、路径限制、禁用策略、并发预留、未知支付、重启恢复、对账及保留 QA 检查。

账本记录下一次 QA 是否通过和剩余问题数量，不宣称因果节省，也不自动学习服务商排名。自动对账、整项开发外包、联邦采购、继续转包和长时间运行的任务不在首版范围内。

代码：[契约](../core/procurement_contract.py)、[账本](../core/procurement_store.py)、[编排](../orchestrator/procurement.py)、[收据验证](../core/procurement_receipt.py)。

## 真实调用验证 — 2026-10-11

[保存的证据](evidence/factory-subcontracting-live-2026-10-11.json)记录了对临时 Hub 的真实 HTTPS 请求，以及通过工厂已配置的 OpenRouter 账户调用真实 `minimax/minimax-m3` 模型。报告通过源码绑定校验，Ed25519 和 ML-DSA-65 签名验证成功，**测试余额**从 $0.50 变为 $0.40，重复执行未产生网络请求。成功的模型调用报告费用为 $0.00033588。生产账户和目录均未修改；这不能证明生产市场付款或完整产品构建已通过。

此前两次运行分别发现服务超时和报告格式错误。超时保留了预留金额且未重试；格式错误的报告被正确记为已付款但拒收。请求现已明确要求包含 1–5 个诊断项的数组。首次超时调用未返回 usage 数据，因此模型总费用尚未完成核对。

公共 `modelmarket.dev` 返回 HTTP 200，但已部署的搜索响应尚无 `credits_eligible`，且未找到兼容诊断服务商。生产购买需要先更新 Hub、部署兼容服务商，再进行验证。

使用[脚本](../scripts/procurement_live_probe.py)重现隔离测试：
```bash
.venv/bin/python scripts/procurement_live_probe.py \
  --ssh-host YOUR_FACTORY_SSH_ALIAS --container aicom-app-1 \
  --output /tmp/procurement-live-result.json
```
每次运行可能产生一次真实模型费用；根据模型价格估算的上限不得超过 $0.25。密钥保留在远程容器内。Hub、TLS 密钥、目录和测试 credits 均为临时资源。

## 生产环境已启用 — 2026-10-11

工厂现在通过 `https://modelmarket.dev` 向获批的 `aicom-diagnostics` 服务购买 `aicom.diagnose@v1`。首个服务商由运营方拥有，独立于工厂运行，使用 `minimax/minimax-m3`。Hub 验证绑定请求的服务商 Ed25519 签名；工厂验证 Hub 的 Ed25519 与 ML-DSA-65 收据。原有 Metis 仍用于架构和方法阶段，与反复出现的代码缺陷诊断分开。

限额：每次 $0.25、每产品 $0.50、每日 UTC $2，保留 $0.50 用于内部完成工作。流水线总限额仍为 $40。仅允许共享 `backend/app/*.py` 和 `frontend/src/*.tsx`。专用账户获得一次性 $2 运营 credits，不自动充值。成功购买扣除 $0.10，验证余额为 $1.90。这是运营方授予的 Hub credits，不代表法币存款或独立客户收入。

生产测试使用合成缺陷与真实模型报告。成功的签名交付复用了前一次签名检查时保存的报告，没有再次调用模型。重放已接受任务没有网络请求。此前五次拒绝均已与 Hub 账本核对，无扣费。适配器支持完整的 Markdown JSON 块及 `suggest_check` 字段变体，同时严格验证源码引用与公开协议。45 项测试通过；不表示完成真实产品的全部修复。

[生产验证记录](evidence/procurement-production-2026-10-11/README.md)。将生产 `data/config/procurement.json` 中的 `enabled` 设为 `false` 即可停止新购买，无需重启。发布与回滚文件：`/root/procurement-release-20261011/`。未推送 GitHub。
