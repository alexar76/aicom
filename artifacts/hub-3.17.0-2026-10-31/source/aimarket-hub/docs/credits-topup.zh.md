# 用 USDC 购买额度（充值）

> **English:** [credits-topup.md](./credits-topup.md) · **Русский:** [credits-topup.ru.md](./credits-topup.ru.md) · **Español:** [credits-topup.es.md](./credits-topup.es.md) · **Français:** [credits-topup.fr.md](./credits-topup.fr.md)
>
> 代码：[`topup.py`](../aimarket_hub/topup.py) · [`credits.py`](../aimarket_hub/credits.py)（`deposit`） · [`settle.py`](../aimarket_hub/settle.py)（`verify_transfer`） · [`channels.py`](../aimarket_hub/channels.py)（`claim_deposit_as`） · SDK [`aimarket_agent/topup.py`](https://github.com/alexar76/aimarket-agent/blob/main/aimarket_agent/topup.py)

没有钱包？个人可以用银行卡购买同样的额度：[card-topup.zh.md](card-topup.zh.md)。

在枢纽额度轨道上运行的一切——带分包额度的[分包](subcontracting.zh.md)、[授权书](mandates.zh.md)、通过 REST 或 [A2A](a2a.md) 并携带 `X-API-Key` 的付费调用——都需要账户上有额度。不属于运营者的智能体可以开设账户，但此前没有办法往账户里存钱：只有运营者才能为账户入账（`POST /accounts/{id}/credit`）。本页介绍的入口让任何智能体都能**自行用 USDC 购买额度**：开设账户、获取报价、从自己的钱包在链上支付，然后兑付这笔付款。

它就是枢纽在直付卖家销售中早已使用的 x402 “exact” 方案，只是收款方换成了运营者钱包。枢纽不持有任何密钥、不提交任何交易，也不支付 gas；它读取链上数据，并为报价所针对的账户入账。

**状态。** 自 2026-09-28 起包含在枢纽中，**默认关闭**（`AIMARKET_TOPUP_ENABLED`）。已在本地链（anvil）上使用真实的 EIP-3009 代币合约完成端到端验证（`tests/test_topup_chain.py`），覆盖 SQLite 和 PostgreSQL，并经过了对资金路径的独立审查。枢纽会在其 well-known 中公布该入口是否开放——见[运营者](#运营者)。

## 目录

- [简要版本](#简要版本)
- [谁持有什么](#谁持有什么)
- [端到端流程](#端到端流程)
- [资金去向](#资金去向)
- [使用额度：预留、过期与退款](#credit-lifecycle)
- [充值报价](#充值报价)
- [支付报价](#支付报价)
- [兑付一笔付款](#兑付一笔付款)
- [报价的生命周期](#报价的生命周期)
- [为什么兑付不需要秘密值](#为什么兑付不需要秘密值)
- [一笔付款，一次入账](#一笔付款一次入账)
- [无需任何人出示即可入账](#无需任何人出示即可入账)
- [错误](#错误)
- [运营者](#运营者)
- [如何测试](#如何测试)
- [容易忽略的规则](#容易忽略的规则)

## 简要版本

```bash
HUB=https://example-hub.net
# 1. Open an account (hubs with open signup). The key is shown once — keep it.
curl -s -X POST $HUB/ai-market/v2/accounts -H 'Content-Type: application/json' -d '{"label":"my agent"}'
# 2. Ask for 5 USDC of credit: the answer is a 402 with x402 terms and a nonce.
curl -s -X POST $HUB/ai-market/v2/account/topup -H "X-API-Key: $KEY" \
     -H 'Content-Type: application/json' -d '{"amount_usd": 5}'
# 3. Sign transferWithAuthorization over that nonce with your wallet and send it (you pay gas).
# 4. Redeem the mined transaction; anyone may do this, the credit goes to your account.
curl -s -X POST $HUB/ai-market/v2/topups/$NONCE -H "X-API-Key: $KEY" \
     -H 'Content-Type: application/json' -d "{\"tx_hash\": \"$TX\"}"
```

## 谁持有什么

| 参与方 | 持有 | 职责 |
|---|---|---|
| **买家智能体** | 其账户的 `X-API-Key` | 请求报价、兑付、花费额度 |
| **买家钱包** | 私钥和 USDC | 签署 EIP-3009 授权并发送交易，支付 gas |
| **运营者钱包**（`payTo`） | 支付给它的 USDC | 什么也不做：它只是一个地址 |
| **枢纽** | 不持有密钥；持有报价和账本 | 生成报价、读取链上数据、为账户入账 |
| **链** | 代币合约 | 检查签名，记录 `AuthorizationUsed(payer, nonce)` 日志和转账 |

## 端到端流程

```mermaid
sequenceDiagram
    participant A as 买家智能体
    participant W as 买家钱包
    participant H as 枢纽
    participant C as USDC 合约（Base）

    A->>H: POST /ai-market/v2/accounts
    H-->>A: account_id + api_key（只显示一次）
    A->>H: POST /ai-market/v2/account/topup {"amount_usd": 5}<br/>X-API-Key
    Note over H: 生成一个随机 nonce<br/>把它绑定到这个账户和 5.00 USDC
    H-->>A: 402——向 payTo 支付 5 USDC<br/>方式是对该 nonce 签署 transferWithAuthorization
    A->>W: 签署 EIP-712 类型化数据
    W->>C: transferWithAuthorization(from, payTo, 5 000 000, …, nonce, v, r, s)
    Note over C: 签名通过检查<br/>先记录 AuthorizationUsed(payer, nonce)，再记录 Transfer
    A->>H: POST /ai-market/v2/topups/{nonce} {"tx_hash"}
    H->>C: 读取交易回执（并等待确认）
    Note over H: 针对「这个」nonce 的授权向 payTo 转移了<br/>至少 5 000 000 个单位——随后认领、记录、入账
    H-->>A: 已入账 5.00，余额 5.00
    A->>H: 携带 X-API-Key 进行调用 / 分包 / A2A
```

## 资金去向

```mermaid
flowchart LR
    BW["买家钱包<br/>5 USDC"] -- "链上的一笔转账<br/>由买家签名" --> OW["运营者钱包<br/>payTo"]
    OW -. "枢纽从不持有<br/>也从不转移它" .- H["枢纽"]
    H -- "入账 5.00<br/>（账本：topup）" --> ACC["买家的额度账户<br/>balance、topped_up"]
    ACC -- "预留 → 扣费<br/>按每次调用" --> SPENT["已花费<br/>枢纽收入、提供方分成"]
    ACC -- "分包额度预留" --> JOB["分包作业<br/>分包额度"]
```

- USDC **直接进入运营者钱包**，通过买家签名的一笔链上转账完成。枢纽的职责是读取这笔转账并写入一笔额度。
- 额度是运营者所欠的预付服务。枢纽会公布它：`stats.credits.topped_up_usd`（购买的额度），旁边是 `outstanding_credit_usd`（仍以余额、预留和保证金形式欠下的全部金额）和 `credits_earned_usd`（已花费）。
- 购买的额度与赠送的额度分开记录（`topped_up_usd` 对 `granted_usd`）：注册赠送预算和偿付能力报告都不能把流入的资金误当作送出去的额度。
- 额度一旦到账，其花费方式与运营者发放的额度完全相同：先预留，交付时再扣费（[subcontracting.zh.md](subcontracting.zh.md#资金如何流动) 展示了一个作业的完整账本）。

<a id="credit-lifecycle"></a>

## 使用额度：预留、过期与退款

- **固定价格调用先预留。** 在调用提供方之前，hold 将价格从可用余额转入 `held`；成功后 capture 扣除同一金额。已处理的提供方错误路径会释放预留。余额不足时不会调用提供方。此路径不按输出量计费，也不在交付后追加超额费用；提供方响应中的 `charged_usd` 不能增加实际扣款。
- **释放预留无法撤销外部工作。** 超时后预留可能已返还，但提供方已经执行了操作。新请求或普通重试可能重复该操作。REST 的 [`Idempotency-Key` 机制](../README.md#retrying-a-paid-call)可以返回受支持请求已保存的结果；额度账本本身不保证提供方恰好执行一次，MCP 重试也不会自动获得此保证。
- **遗留预留在超过阈值后恢复，而非精确到期。** 普通遗留 credit hold 只有在年龄**大于 3600 秒**时才可释放。调度器在启动时运行，之后默认每 **120 秒**运行一次（`AIMARKET_SUBCONTRACT_SWEEP_S`）；值 ≤0 会禁用它。扫描数量限制及所有者状态可能推迟恢复。验证预留、申诉保证金和分包额度具有各自的生命周期。
- **密钥和余额不会自动过期。** 停用账户会阻止其密钥；轮换使旧密钥失效但保留余额。单独的 API 密钥没有每小时金额上限。请求限流按 IP/会话身份计数，而非按密钥花费计数。若需 `perCall`、按 UTC 自然日计算的 `perDay`、`total` 以及不包含边界时刻的 `validUntil`，请使用[授权书](mandates.zh.md)，并开启 `require_mandate=True`，防止原始 API 密钥绕过限制。
- **返还额度不等于支付 USDC。** Release 恢复服务额度。`CreditsLedger.refund` 是受信任运营者的账务调整，并非绑定 receipt 的客户退款；重复调用可能重复增加额度。两者都不会发送 USDC，也没有自助提现。未使用余额仍是运营者的负债（`outstanding_credit_usd`）；实际退款需要运营者另行付款并核对账目。
- **通道是另一种支付路径。** 转账注资通道的默认 TTL 为 24 小时，但由扫描执行：在扫描之前，`open` 行即使超过 `expires_at` 仍可接受 debit/hold；待处理 hold 会推迟关闭/过期。关闭/过期只记录 `refund_owed_usd`，`refund_executed_usd=0`，不会发送资金。不能把 escrow 合约的保证套用于该账本或预付额度。参见[支付路径](money-rails.md)。

这些场景通过真实应用/SQLite 代码和虚拟资金进行验证：[账本](../tests/test_micky_credit_lifecycle.py)、[MCP/invoke](../tests/test_micky_mcp_payment_flow.py)、[过期恢复](../tests/test_micky_expiry_recovery.py)。它们不验证真实链上的付款，也不验证正在运行的生产枢纽。

## 充值报价

带着账户的 `X-API-Key` 和 `{"amount_usd": 5}` 请求 `POST /ai-market/v2/account/topup`，会得到 **402** 应答，以两种形式给出同一组条款：`PAYMENT-REQUIRED` 头中的 x402 V2 `PaymentRequired`（base64 编码的 JSON），以及任何 x402 V1 客户端都能读取的 JSON 应答体。

```json
{
  "error": "payment_required",
  "nonce": "0x5c1f…",
  "binding": "eip3009",
  "pay_to": "0x7099…",
  "expires_at": 1790001234.5,
  "accepts": [{
    "scheme": "exact", "network": "base", "maxAmountRequired": "5000000",
    "asset": "0x8335…", "payTo": "0x7099…", "maxTimeoutSeconds": 900,
    "extra": { "name": "USD Coin", "version": "2", "chainId": 8453,
               "verifyingContract": "0x8335…", "nonce": "0x5c1f…", "decimals": 6, "symbol": "USDC" }
  }],
  "topup": {
    "nonce": "0x5c1f…", "amount_usd": 5.0, "amount_units": "5000000",
    "network": "eip155:8453", "chain_id": 8453, "pay_to": "0x7099…",
    "min_confirmations": 2, "redeem_url": "https://example-hub.net/ai-market/v2/topups/0x5c1f…"
  }
}
```

- **nonce** 是枢纽生成的 32 个随机字节。它在 `credit_topup_quotes` 中与发出请求的账户以及确切金额绑定。正是这一绑定（binding）决定了一笔付款记入谁的账户——付款方或出示方之后发送的任何内容都无法改变它。
- **金额**以整分为单位。`12.5` 可以；`1.005` 会被拒绝而不是被四舍五入，这样买家被告知的就是它将要支付的确切金额。
- `extra` 携带代币完整的 EIP-712 domain：钱包对它签名；若根据代币符号去猜测 name 或 version，得到的签名会被代币合约拒绝。

| 限制 | 默认值 | 设置 |
|---|---|---|
| 最小充值额 | $1.00 | `AIMARKET_TOPUP_MIN_USD` |
| 最大充值额 | $100.00 | `AIMARKET_TOPUP_MAX_USD` |
| 每个账户每 24 小时的购买额 | $500.00 | `AIMARKET_TOPUP_DAILY_USD` |
| 每个账户同时开放的未付报价数 | 5 | `AIMARKET_TOPUP_MAX_OPEN_QUOTES` |
| 未付报价的提供时长 | 900 s（至少 60） | `AIMARKET_TOPUP_QUOTE_TTL_S` |
| 此后未兑付的报价还会保留多久 | 30 天（至少 1） | `AIMARKET_TOPUP_RETAIN_DAYS` |

每日限额统计的是已经购买的额度**以及**仍然开放的报价，并且在兑付付款时会再检查一次：报价是在生成之后才被支付的，过期之后也仍可兑付，因此只在报价时检查什么也限制不住。超过限额时，已付款的兑付会以带 `retryable` 的 `429 daily_topup_limit` 应答，报价保持开放——额度会等着，而钱无论如何都属于该账户。该限额限制了被盗密钥能买多少（钱确实进来了，但运营者随之欠下等额的服务）。在报价之前，枢纽还会读取一次代币自己的 `decimals()`，如果它与枢纽计价所用的精度不符就拒绝报价：否则，指向一个 18 位小数代币的资产覆盖配置会只要求价格的万亿分之一，却按全额入账。

## 支付报价

买家签署一个 EIP-3009 `transferWithAuthorization`——`from` 为它的钱包，`to` = `payTo`，`value` = `maxAmountRequired`，`nonce` = 报价的 nonce——并**自己发送这笔交易**。枢纽什么也不提交，也不支付 gas：替人转发授权的枢纽需要一把存有资金的热密钥，而这恰恰是它所没有的。链上的任何钱包都可以提交已签名的授权，因此由买家自选的第三方也可以代为发送。

使用 Python SDK（它从不接触密钥）——用持有你密钥的任何工具签名：

```python
import time
from eth_account import Account
from aimarket_agent import AIMarketAgent
from aimarket_agent.topup import calldata, typed_data

agent = AIMarketAgent("https://example-hub.net")
agent.create_account("my agent")                       # sets agent.api_key
offer = agent.topup_quote(5)                           # the 402 body
typed = typed_data(offer, sender=WALLET, valid_before=int(time.time()) + 600)
signature = Account.sign_typed_data(PRIVATE_KEY, full_message=typed).signature.hex()
data = calldata(typed, signature)                      # send to offer["accepts"][0]["asset"]
# ... sign and broadcast a transaction {to: asset, data: data} from WALLET ...
agent.topup_redeem(offer["nonce"], tx_hash)            # → {"credited_usd": 5.0, "balance_usd": 5.0, …}
```

`typed_data` 会在签名之前拒绝它无法履行的报价（缺少 domain 字段、`payTo` 格式错误、没有 nonce）。把 `valid_before` 设得近一些：在此之前，任何持有已签名授权的人都可以提交它——付的仍是*你的*报价，但时机不由你选择。

**只有针对报价 nonce 的授权才会入账。** 向同一钱包转入同样金额的普通 `transfer` 不携带任何说明它属于哪个账户的信息，因此枢纽无法自动为它入账——见[找回付款](#找回枢纽无法入账的付款)。

### 用你自己的钱包，两条命令完成

[`scripts/credits_topup_pay.py`](https://github.com/alexar76/aicom/blob/main/scripts/credits_topup_pay.py) 替人走完整个流程：请求报价，打印条款，只有加上 `--yes` 才会对报价的 nonce 签署授权、发送交易（gas 由你支付）、等待确认并兑付。账户密钥和钱包密钥分属两个步骤，因此永远不必放在同一台机器上；钱包密钥从文件或环境变量读取，绝不打印。

```bash
# 1. whoever holds the ACCOUNT key asks for terms (valid 15 minutes)
python3 scripts/credits_topup_pay.py quote --hub https://hub.example --api-key-file account.key --amount 1 --out quote.json
# 2. whoever holds the WALLET key: without --yes it only prints what it would pay
python3 scripts/credits_topup_pay.py pay --quote quote.json --wallet-key-file wallet.key
python3 scripts/credits_topup_pay.py pay --quote quote.json --wallet-key-file wallet.key --yes
```

```text
pay          1.00 USDC  →  0x7099…79C8  (chain 31337)
from         0x3C44…93BC   balance 213.250000 USDC, 999.999585 ETH
credited to  the account that asked for the quote, after 1 confirmations
sent         0x61cb8aae…fcd5
mined        block 1716, 1+ confirmations
credited     $1.0 of $1.0 paid
```

2026-10-04 在 UNI 测试链上验证（上面的输出）：已入账；同一报价的第二次兑付返回 `idempotent_replay`；同一笔交易用于新报价时被拒绝。

## 兑付一笔付款

带 `{"tx_hash": "0x…"}` 请求 `POST /ai-market/v2/topups/{nonce}`。或者按 x402 的方式：重复报价请求，并附上 `X-Payment: <tx hash or x402 payload carrying it>`（交易哈希，或携带它的 x402 载荷）和 `X-Payment-Nonce: <nonce>`。两者执行的是同一段代码。

```mermaid
flowchart TD
    R["POST /topups/{nonce}<br/>tx_hash"] --> K{"报价存在吗？"}
    K -- 否 --> E404["404 topup_unknown"]
    K -- 是 --> S{"报价状态"}
    S -- "已入账，由这笔交易" --> OK0["200，idempotent_replay"]
    S -- "已入账，由另一笔交易" --> E409c["409 topup_already_credited"]
    S -- "正在兑付另一笔交易" --> E409p["409 topup_in_progress"]
    S -- "已报价，或正在兑付这笔交易" --> L{"这一分钟内<br/>检查不足 12 次？"}
    L -- 否 --> E429["429 too_many_attempts<br/>按调用方计"]
    L -- 是 --> V{"链上：AuthorizationUsed(payer, nonce)<br/>且紧随其后的那条 Transfer<br/>向 payTo 转移了 USDC？"}
    V -- "未上链 / 确认数不足" --> E409["409 payment_not_final<br/>重试"]
    V -- 否 --> E402["402 payment_invalid<br/>报价保持开放"]
    V -- 是 --> DL{"是否在<br/>每日限额之内？"}
    DL -- 否 --> E429d["429 daily_topup_limit<br/>稍后重试"]
    DL -- 是 --> B{"认领报价<br/>一条带条件的 UPDATE"}
    B -- "另一次兑付已占用它" --> E409b["409 topup_in_progress"]
    B -- 抢到 --> D{"在存款登记表中<br/>认领该交易"}
    D -- "已被另一个入口占用<br/>通道、Factory、运营者" --> REF["409 payment_already_used<br/>报价保持开放"]
    D -- 成功 --> X["在 x402_payments 中<br/>记录该授权"]
    X --> C["为「报价所绑定的」账户入账，最多到报价金额<br/>单个数据库事务，reference 为 topup:chain:nonce"]
    C --> OK["200 已入账"]
```

链上检查的要求——与市场轨道对“已付款”的定义相同（`settle.verify_transfer`）：

- 交易执行成功，且至少有 `AIMARKET_TOPUP_MIN_CONFIRMATIONS` 个确认（默认 2）；
- 代币合约为**这个** nonce 记录了 `AuthorizationUsed(payer, nonce)` 日志；
- 代币合约**紧接着的下一条日志**是一条从该付款方到 `payTo` 的 `Transfer`。如果把交易中的每一笔转账都计算在内，别人就可以把买家的授权和自己的授权打包进同一笔交易，从而兑付买家的钱；只有这一授权所转移的金额才算数。

入账的是这笔转账实际转移的金额，**最多到报价金额为止**，按账本的毫分向下取整：

- **少付**——按实际到账的金额入账。无论金额多少，nonce 都把这笔钱绑定到该账户；拒绝少付的付款反而会让钱被困住。
- **超额支付**——按报价金额入账；应答中的 `overpaid_usd` 和日志中的一条 ERROR 会说明运营者需要退还多少。`max_usd` 和每日限额限制的是*入账*金额，因此无论付了多少，它们都依然有效。

应答**只对该账户自己的密钥**显示新余额和账户 id；其他任何人只能得知该报价已入账以及入账金额。

每次检查都要往返一次链的 RPC，因此检查受速率限制——按**调用方**计，而不是按报价计：每个 IP 地址每分钟 12 次，除报价所有者以外的任何人（包括持有其他账户密钥的人）都消耗这份配额；所有者的账户另有每分钟 12 次，由它的全部报价共用。如果按 nonce 计数，任何从链上读到该 nonce 的人都可以用伪造的哈希耗尽这份配额，把所有者挡在门外；如果每份报价各有配额，免费开设的账户和始终可兑付的报价就能无限放大对链的读取。链上读取在请求循环之外进行，因此一个缓慢的节点只会拖慢它自己那次兑付。

## 报价的生命周期

```mermaid
stateDiagram-v2
    state "已报价" as Quoted
    state "兑付中" as Redeeming
    state "已入账" as Credited
    state "已清除" as Pruned
    [*] --> Quoted: POST /account/topup
    Quoted --> Quoted: 一笔未通过验证的付款<br/>（未付、未绑定、尚未最终确认）
    Quoted --> Redeeming: 一笔已通过验证的付款认领了它
    Redeeming --> Credited: 登记表、授权、入账
    Redeeming --> Quoted: 任何入账之前发生的暂时性失败
    Redeeming --> Redeeming: 卡住 60 秒——同一交易的<br/>下一次兑付会把它完成
    Redeeming --> Quoted: 另一个入口已持有该交易，<br/>或已达到每日限额
    Quoted --> Pruned: 从未入账，超过保留期（30 天）
    Credited --> [*]
    Pruned --> [*]
```

- **已付款的报价不会过期。** `AIMARKET_TOPUP_QUOTE_TTL_S` 限定的是未付报价的提供时长；为它所做的付款在报价被清除之前都可以兑付，而清除发生在报价过期之后 `AIMARKET_TOPUP_RETAIN_DAYS`（默认 30）天。已入账的报价永远不会被清除——它们是资金流入的记录。
- **只有入账才是终态。** 一次拒绝——交易已被另一个入口持有、达到每日限额、登记表或数据库无法写入——都会让报价保持 `quoted`，因此一旦导致拒绝的情况发生变化，同一笔付款可以再次出示。
- **被中断的兑付会被完成。** 认领之后的每一步都以 nonce 为幂等键（登记表认领、授权记录、账本 reference），因此中途失败的兑付会由针对同一交易的下一次兑付完成，并且只入账一次。

## 为什么兑付不需要秘密值

直付卖家轨道把它的 nonce 绑定到一个秘密值（payment secret）上，枢纽只把这个秘密值交给拿到那次 402 的调用方，因为一次调用是为**出示付款的人**提供的服务：付款一旦上链，其哈希和 nonce 就是公开的，抢先出示它们的旁观者就会拿走这次调用。

充值则不是为出示者提供的服务。账户在报价生成时就已确定，因此：

| 不是买家的某人…… | ……得到 |
|---|---|
| 抢先出示买家已上链的交易 | 什么也得不到：入账的是**买家的**账户，且只入账一次 |
| 自己请求报价并支付 | 在**他自己的**账户上获得额度，用的是他自己的钱 |
| 对买家的 nonce 签署授权，金额不限 | 送给买家的一份礼物：买家的账户按实际到账金额入账 |
| 重新发送已入账的付款，或把它当作通道存款使用 | 什么也得不到：它只能被认领一次，对所有入口都一样 |

在这里要求秘密值什么也保护不了，反而会让丢失秘密值的买家的钱被困住。因此任何持有交易哈希的人都可以兑付——买家的钱包、代为发送交易的第三方，或代表买家的枢纽运营者。

## 一笔付款，一次入账

```mermaid
flowchart LR
    TX["一笔已上链的交易<br/>转入运营者钱包"] --> REG{"存款认领登记表<br/>以 chain + tx 为键"}
    REG -- "先认领者得" --> T["充值入口<br/>为报价所绑定的账户入账"]
    REG -- "先认领者得" --> CH["通道存款入口<br/>为一个通道注资"]
    T --> XP["x402_payments<br/>授权已花费"]
    XP -. "调用无法兑付<br/>充值 nonce" .-> INV["直付卖家调用"]
```

通道存款入口接受的同样是转入运营者钱包的转账。入账之前，兑付会以 `aimarket-hub-topup` 的名义，在通道入口和 Factory 共同写入的那个一次性登记表（`AIMARKET_DEPOSIT_CLAIMS_DIR`，或通道账本自己的目录）中认领这笔交易。哪个入口先认领，交易就归哪个入口：已入账的充值此后永远不能再为通道注资，而已被用作存款的交易在这里会被拒绝。

**认领记录的是验证器实际读取的那条链。** 登记表过去以调用方给出的链标签作为认领的键。但设置了 `AIMARKET_DEPOSIT_RPC_URL` 时，所有标签都在同一个节点上验证，因此同一笔交易可以先以 “base” 认领一次，再以 “ethereum” 认领一次——一笔付款换来一次充值加一个通道，或者两个通道。现在每个入口都会同时以 `eip155:<chainId>`（标签被覆盖时，用节点自己的 `eth_chainId`）、以它自己的标签（在此之前写入的认领只带有这个标签，仍然会与新认领冲突），以及以每个指向同一条链的已配置标签来认领交易。写入者在写完之前就已终止的认领文件会在一分钟后被修复；可读的他方认领永远不会被覆盖。

一笔交易中的两个充值授权——一个智能钱包一次支付两份报价——各自为自己的报价入账：登记表条目属于充值入口，而每个授权在 `x402_payments` 中分别被花费。

## 无需任何人出示即可入账

如果枢纽的充值钱包是**专用**的（`AIMARKET_TOPUP_PAY_TO` 只接收充值），枢纽会每隔
`AIMARKET_DEPOSIT_WATCH_INTERVAL_S`（60 秒）自己读取这个钱包，任何人都不必出示付款：

| 钱包收到的款项 | 枢纽的处理 |
|---|---|
| 对某份报价的付款（带报价 nonce 的 `transferWithAuthorization`） | 达到确认数后，按与 `POST /topups/{nonce}` 完全相同的方式兑付。自己出示依然可行，只是更快。 |
| 来自已与账户**关联**的钱包的普通转账 | 作为已付额度（`topped_up_usd`）记入该账户，引用为 `chain:<chain>:<tx>`。 |
| 来自无人关联的钱包的普通转账 | 记为**未归属**：计入 well-known、列给运营者、由告警器报警，并在其发送方被关联的那一刻入账。 |

枢纽是否这样做、付款到哪里，都写在它的 well-known 中：

```json
"topup": { "enabled": true, "pay_to": "0x63177eb5…", "...": "...",
  "deposit_watch": {
    "enabled": true, "wallet": "0x63177eb5…", "interval_s": 60,
    "link": "/ai-market/v2/account/payer-wallets",
    "link_message": "aimarket-payer-wallet/1\nhub: https://example-hub.net\naccount: <account_id>\naddress: <address>\nissued_at: <unix seconds>",
    "link_signature": "EIP-191 personal_sign by the wallet",
    "unattributed_deposits": 0 } }
```

### 关联钱包

普通转账（人们用普通钱包应用发送的那种）不携带账户。因此在付款前或付款后，账户只需做一次：说明
它从哪个钱包付款，并证明它控制该钱包——由该钱包对 `link_message` 做 EIP-191 `personal_sign`
签名，消息中填入账户 id、小写地址和当前 unix 时间。这是签名而不是交易：不花任何钱，也不付 gas。

```bash
python3 scripts/credits_topup_pay.py link --hub $HUB --api-key-file account.key --ask
```

或者手动操作，用任何能签名消息的钱包：

```bash
curl -s -X POST $HUB/ai-market/v2/account/payer-wallets -H "X-API-Key: $KEY" -H 'Content-Type: application/json' \
     -d '{"address": "0x…", "issued_at": 1790000000, "signature": "0x…"}'
```

| 应答 | 情形 |
|---|---|
| 200，`linked` 或 `already`，`credited_now` | 已关联。该钱包之前等待中的转账现在入账。 |
| 400 | 不是地址，或 `issued_at` 与枢纽时钟相差超过 10 分钟。 |
| 403 | 签名不是该钱包对这条消息的签名（其他枢纽、账户、地址或时间）。 |
| 409 | 该钱包已关联到另一个账户：一个钱包只为一个账户付款。 |
| 401 | 没有 `X-API-Key`，或该枢纽不认识这个密钥。 |
| 503 | 该枢纽无法校验钱包签名（未安装 eth-account）：请运营者关联该钱包。 |

`GET /ai-market/v2/account/payer-wallets` 列出账户的钱包；`POST
/ai-market/v2/account/payer-wallets/unlink` 带 `{"address"}` 可解除关联（已入账的额度保留）。
对于它认识的公司，运营者可以不经签名关联钱包：
`POST /ai-market/v2/accounts/{id}/payer-wallets`，带 `{"address"}` 和管理员令牌。

### 为什么只能用专用钱包

枢纽的 x402 钱包（`AIMARKET_X402_PAY_TO`）也接收销售款，与之共用的商店也在那里收自己的款项，而收款钱包
（`AIMARKET_PAYMENT_RECIPIENT`）接收通道存款。把每笔转入都当作充值，会把这些款项重复入账。因此监视器只在
明确设置了 `AIMARKET_TOPUP_PAY_TO` 时运行，且绝不在这两个钱包上运行；关闭时，well-known 会说明原因。

### 只入账一次，无论哪个入口先看到

监视器在所有入口共用的同一个存款登记表中占用普通转账（名称为 `aimarket-hub-deposit-watch`），
并使用与运营者手动入账相同的账本引用入账。运营者已手动入账的转账记为 `credited_elsewhere`；在
监视器之后再手动入账会得到 `409`。报价付款走兑付代码本身。数据库中的游标记住最后读到的区块；节点
出错时，下次重新读取相同的区块。枢纽启动后，监视器先等待一个间隔。

### 每笔转账会怎样

转入钱包的每笔转账都有自己的一行记录，任何一笔都不会拖住其他转账：枢纽记下它的状态后继续读取。只有完全
无法读取的节点才会让一次扫描停下——随后会重新读取相同的区块。每次扫描还会重读最近 12 个区块（负载均衡后
的节点可能由落后一个区块的后端应答），并自行检查每条日志：代币、Transfer 事件、收款方以及节点的 chain id。

| 状态 | 含义 | 由什么了结 |
|---|---|---|
| `credited` | 已记入报价或关联所指的账户。 | — |
| `credited_elsewhere` | 另一个入口先为这笔交易入账：运营者的手动入账、手动出示的报价、通道。 | — |
| `pending` | 暂时无法判定：报价所属账户超出 24 小时限额、节点还没有收据、登记表没有应答。 | 枢纽在每次扫描时重试。 |
| `unattributed` | 无法认定账户：未关联的钱包、一笔交易中有多个发送方、枢纽拒绝的报价付款。 | 关联（仅限单一发送方）、运营者手动入账，或 `POST /admin/deposits/{tx}/resolve`。 |
| `ignored` | 少于一毫分（$0.00001）：没有可入账的金额。 | — |
| `resolved` | 运营者已在枢纽之外处理（退款）并注明方式。 | — |

**一笔交易中有多个发送方**时不会自动记给任何人——放在别人付款前面的、来自已关联钱包的一笔小额转账，不能
因此拿走那笔付款。运营者按 `tx_hash` 手动记入正确的账户。

### 限额与钱包

- 最低额、最高额和 24 小时限额适用于**报价**。来自已关联钱包的普通转账无论金额大小都会入账：钱已经到账，
  拒绝入账也不会把钱退回去。
- **合约钱包**（EIP-1271：Safe、Coinbase Smart Wallet）无法用签名关联（`403`）：请运营者关联。
- 切勿关联**共用的发送方**——交易所的热钱包、从 `0x0…` 铸造的跨链桥：任何人经由它的每笔到账都会记入同
  一个账户。
- 切勿让**两个枢纽共用一个充值钱包**：各自有自己的登记表，两边都会为同一笔转账入账。

## 错误

| 状态码 | `error` | 何时 | 怎么做 |
|---|---|---|---|
| 401 | `api_key_required` | 请求报价时没有有效的 `X-API-Key`。 | 开设账户（`POST /ai-market/v2/accounts`）并发送其密钥。 |
| 400 | `amount_invalid` | 不是数字，或精度细于一分。 | 以整分发送。 |
| 400 | `amount_out_of_range` | 低于最小值或高于最大值。 | 保持在 well-known 给出的 `min_usd`–`max_usd` 范围内。 |
| 429 | `too_many_open_quotes` | 账户上的未付报价过多。 | 支付其中一份，或等它们过期。 |
| 429 | `daily_topup_limit` | 该账户已买满 24 小时内的上限。 | 等待，或联系运营者。 |
| 503 | `topup_unavailable` | 本枢纽上的该入口已关闭（并说明原因）。 | 读取 `payment_rails.credits.topup.reason`。 |
| 400 | `nonce_invalid` / `tx_hash_invalid` | 格式错误——或者 x402 载荷只携带了一个已签名的授权：本枢纽只做验证，从不代为结算。 | 自己提交该授权，然后发送以 0x 开头的交易哈希。 |
| 404 | `topup_unknown` | 这里没有该 nonce 的报价（从未生成，或未付款而已被清除）。 | 检查枢纽和 nonce。 |
| 409 | `payment_not_final` | 尚未上链，或确认数不足。`retryable`。 | 等一两个区块后重试。 |
| 402 | `payment_invalid` | 该交易没有支付这份报价：没有针对该 nonce 的授权、收款方错误、交易已回滚。报价保持开放。 | 按报价所给的条款支付。 |
| 429 | `daily_topup_limit`（兑付时） | 为这笔付款入账将超出该账户的 24 小时限额。`retryable`；报价保持开放。 | 稍后再兑付。 |
| 409 | `topup_in_progress` | 另一次兑付正占用该报价。 | 读取 `GET /ai-market/v2/topups/{nonce}` 后重试。 |
| 409 | `topup_already_credited` | 该报价已由另一笔交易入账。 | 无需操作：你的账户已经收到。 |
| 409 | `payment_already_used` | 该交易已在另一个入口被使用。报价保持开放。 | 带着 nonce 联系运营者。 |
| 500 | `credit_failed` | 付款已通过验证，但额度无法写入。`retryable`。 | 重试；如果一直失败，把 nonce 交给运营者。 |
| 429 | `too_many_attempts` | 一分钟内来自同一地址（报价所有者以外的任何人）的检查超过 12 次，或所有者账户在其全部报价上的检查超过 12 次。 | 一分钟后重试，或用该账户的密钥兑付。 |
| 503 | `verifier_unavailable` / `deposit_registry_unavailable` / `payment_record_unavailable` | 无法读取或写入链、登记表或付款记录。没有入账任何金额。`retryable`。 | 重试。 |
| 503 | `topup_unavailable`（报价时） | 当无法读取代币的 `decimals()`，或它与枢纽计价所用的精度不符时，也会返回此错误。 | 重试，或告知运营者。 |

## 运营者

### 开启入口

| 变量 | 默认值 | 作用 |
|---|---|---|
| `AIMARKET_TOPUP_ENABLED` | `0` | 开启充值入口。还需要额度轨道（`AIMARKET_CREDITS_ENABLED=1`）和一种 USDC 资产。 |
| `AIMARKET_TOPUP_PAY_TO` | 枢纽的 `AIMARKET_X402_PAY_TO` | 充值款项支付到的钱包。请使用一个**只**接收充值的钱包：只有这样，枢纽才会自己监视它并为到账自动入账（见下文）。 |
| `AIMARKET_CREDITS_OPEN_SIGNUP` | `1` | 允许智能体自行开设账户。关闭时，密钥由人工签发，陌生人根本无法购买。 |
| `AIMARKET_SIGNUP_GRANT_USD` | `0` | 自行开设的账户初始获得的免费额度。出售额度时，零才是正确的取值。 |
| `AIMARKET_TOPUP_MIN_CONFIRMATIONS` | `2` | 付款入账之前所需的确认数。 |
| `AIMARKET_TOPUP_VERIFY_DECIMALS` | `1` | 报价之前读取代币的 `decimals()`（每个地址一次）。 |
| `AIMARKET_TOPUP_MIN_USD`, `_MAX_USD`, `_DAILY_USD`, `_MAX_OPEN_QUOTES`, `_QUOTE_TTL_S`, `_RETAIN_DAYS` | 见[充值报价](#充值报价) | 限额。 |
| `AIMARKET_SETTLE_RPC_URL` | 各链的默认值 | 读取付款的位置（与直付卖家共用）：逗号分隔的列表，轮流询问；拒绝服务的节点（HTTP 429、区块范围上限）会暂停使用。免费节点按 IP 限流，请在 hub 所在机器上用 `aimarket rpc-check` 检查列表。 |
| `AIMARKET_DEPOSIT_WATCH` | `1` | 监视充值钱包（需要专用的 `AIMARKET_TOPUP_PAY_TO`）。`0` = 只能出示兑付或手动入账。 |
| `AIMARKET_DEPOSIT_WATCH_INTERVAL_S` | `60`（至少 15） | 读取钱包的频率。 |
| `AIMARKET_DEPOSIT_WATCH_CHUNK_BLOCKS` | `500`（10–2000） | 每次 `eth_getLogs` 的区块数（Base 公共节点拒绝超过约 2000）。 |
| `AIMARKET_DEPOSIT_WATCH_PAUSE_S` | `0.3`（0–5） | 扫描追赶进度时（落后超过 4 个窗口）在窗口之间暂停，避免免费节点的按 IP 限流每隔几个窗口就中断扫描。 |
| `AIMARKET_DEPOSIT_WATCH_LOOKBACK_BLOCKS` | `1800`（Base 上约 1 小时） | 首次扫描的起点；之后由数据库中的游标继续。 |

well-known 会说明该入口是否开放，以及开放的条件：

```json
"payment_rails": { "credits": {
  "enabled": true, "open_signup": true, "signup_url": "https://example-hub.net/ai-market/v2/accounts",
  "topup": { "enabled": true, "quote": "/ai-market/v2/account/topup", "redeem": "/ai-market/v2/topups/{nonce}",
             "binding": "eip3009", "asset": "USDC", "network": "eip155:8453", "pay_to": "0x7099…",
             "min_usd": 1.0, "max_usd": 100.0, "daily_usd": 500.0, "min_confirmations": 2, "quote_ttl_s": 900 }
} }
```

关闭时，`topup` 带有 `"enabled": false` 和一个 `reason`。调用返回的 402 也会指明这个入口，就在注册 URL 旁边。

### 退款

额度是预付的服务。没有任何机制会自动退款；未花费的额度是否退还，由运营者按自己的条款决定——退还的方式是在链上把钱付回，并从账户中扣除相应额度。

### 找回枢纽无法入账的付款

普通转账，或针对本枢纽从未生成的 nonce 的授权，会到达运营者钱包，但无法与任何账户对应。运营者需要手动为它入账，并指明该交易：

```bash
curl -s -X POST $HUB/ai-market/v2/accounts/$ACCOUNT_ID/credit -H "Authorization: Bearer $ADMIN_TOKEN" \
     -H 'Content-Type: application/json' -d "{\"amount_usd\": 5, \"tx_hash\": \"$TX\", \"note\": \"plain transfer\"}"
```

带上 `tx_hash` 时，会先检查账户（输错的 id 会得到 `404`，且不认领任何东西），这笔额度属于**购买的**额度（计入 `topped_up_usd`，而不是赠送），以交易为幂等键，并且该交易会在所有入口共用的同一个登记表中被认领——因此它此后既不能为通道注资，也不能被记入第二个账户，也不能通过报价兑付（`409`）。针对报价 nonce 所做的付款，最好兑付而不是手动入账：任何人都可以兑付它，而且报价随后会记录下这笔付款。

在监视自己钱包的枢纽上，更好的做法是关联发送方
（`POST /ai-market/v2/accounts/{id}/payer-wallets`）：等待中的转账立即入账，此后该钱包的每笔
转账都会自动入账。

### 监控要点

- WARNING 级别的 `topup: credited $… to acct_… for 0x… (tx 0x…, payer 0x…)`——每一次入账。
- ERROR 级别的 `topup: … was already used at another door`——一笔交易被出示给了两个入口。
- 将 `stats.credits.topped_up_usd` 与运营者钱包的链上余额进行对照。
- `GET /ai-market/v2/account/topups`——某个账户自己的历史；`GET /ai-market/v2/topups/{nonce}`——单份报价。
- WARNING 级别的 `deposit watch: credited $… to acct_… (plain transfer 0x… from 0x…)`——每笔已入账的普通转账。
- `GET /ai-market/v2/admin/deposits`（管理员令牌）——未归属和等待中的到账（发送方、金额、交易、原因）以及监视器状态；带 `{"note"}` 调用 `POST /ai-market/v2/admin/deposits/{tx}/resolve` 可关闭一笔在枢纽之外处理完毕的到账。
- `payment_rails.credits.topup.deposit_watch.last_scan_at`——最后一次读取钱包的时间；停止读取的监视器即使显示 `enabled` 也会触发告警。
- `payment_rails.credits.topup.deposit_watch.unattributed_deposits` 大于零——生态告警器会报警
  （`deposits_unattributed:<hub>`）；应当监视却没有监视的枢纽则触发 `deposit_watch_on:<hub>`。

### 表

迁移 `041_credit_topup_quotes` 新增 `credit_topup_quotes`（nonce、账户、以代币单位计的确切金额、收款方、代币、链、过期时间、状态、交易、付款方、实际到账的单位数、已入账的毫分数、账本 reference，以及以 epoch 秒表示的 `credited_at`——每日限额比较的是一个数字，它在 SQLite 和 PostgreSQL 上读起来都一样）以及 `credit_accounts.topped_up_mc`。不存储任何秘密值：这里没有任何东西需要它。

## 如何测试

| 测试内容 | 位置 |
|---|---|
| 402（两种形式）、金额、限额、默认关闭的入口、well-known | `tests/test_topup.py::TestQuote` |
| 只入账一次、重放、x402 重试、由他人出示的付款记入报价所有者的账户、超额支付以报价金额为上限、少付按实际到账金额入账、未通过验证的付款仍可兑付、未绑定的转账被拒绝、速率限制、已停用的账户 | `tests/test_topup.py::TestRedeem` |
| 通道入口与充值入口共用同一次认领、仍在写入中的登记表条目被重试而不是被拒绝、一笔交易中的两个授权、相互竞争的兑付、在入账之前和之后被中断的兑付、清除、调用拒绝充值 nonce | `tests/test_topup.py::TestExclusivity` |
| 运营者手动为一笔链上付款入账：属于购买的额度、幂等，且该交易此后在记入第二个账户、用于通道入口和兑付报价时都会被拒绝 | `tests/test_topup.py::TestOperatorCredit` |
| 独立审查确认的每一项缺陷：枢纽本地的登记表、无论入口使用哪个链标签都只有一次认领、失败的付款记录会被重试而不是被拒绝、写到一半的存款不留下任何东西、兑付时的每日限额、匿名检查不会把所有者挡在门外、写入者已终止的认领、缓慢的链不会拖住其他请求、代币的 decimals、运营者向未知账户入账、只含授权的 x402 载荷 | `tests/test_topup.py::TestReviewFindings` |
| 陌生人开设账户，在本地 anvil 链上用真实的 EIP-3009 代币合约购买 5 USDC 的额度并把它花掉；普通转账被拒绝；少付的授权按实际到账金额入账 | `tests/test_topup_chain.py` |
| SDK 的类型化数据和 calldata，与 `cast calldata` 逐字节比对 | `aimarket-agent/tests/test_topup.py` |

上述每套测试都在 SQLite 和 PostgreSQL 上通过（`AIMARKET_TEST_DATABASE_URL`）。

`tests/test_topup_chain.py` 使用 Base 的 chain id 和 UniUSD（`contracts/evm/src/UniUSD.sol`，即 UNI bubble 的 USDC）运行 anvil。编写这项测试时发现，UniUSD 把它的授权记录为 `AuthorizationUsedEvent`——其 topic 与 USDC 的 `AuthorizationUsed` 不同，因此 bubble 内的任何 EIP-3009 付款都根本不可能通过验证。现在该事件已按 USDC 的方式命名，并由 `contracts/evm/test/UniUSD.t.sol` 固定其 topic。

## 容易忽略的规则

- **用针对报价 nonce 的 `transferWithAuthorization` 付款。** 普通转账不会自动入账。
- **由你发送交易并支付 gas。** 枢纽没有密钥。
- **已付款的报价不会过期**；未付款的报价在保留期过后会被清除。
- **可以从任何地方兑付。** 无论谁出示付款，额度都记入报价所绑定的账户。
- **等待确认。** `payment_not_final` 的意思是“稍后再来”，而不是“不行”。
- **到账多少就入账多少，最多到报价金额为止**，按毫分向下取整；超额支付会被报告出来，由运营者退还。
- **一笔交易，一次入账**——在充值入口和通道存款入口之间同样如此。
- **额度是预付的服务**，不是会生息的存款，也不是会自动退还的余额。

另见：[subcontracting.zh.md](subcontracting.zh.md) · [mandates.zh.md](mandates.zh.md) · [a2a.md](a2a.md) ·
[money-rails.md](money-rails.md) · [市场轨道](https://github.com/alexar76/aicom/blob/main/docs/hestia-hub-market-rail.md) ·
[术语表](https://github.com/alexar76/aicom/blob/main/docs/localization-glossary.md)
