# 用银行卡购买额度（Stripe Checkout）

> **English:** [card-topup.md](./card-topup.md) · **Русский:** [card-topup.ru.md](./card-topup.ru.md) · **Español:** [card-topup.es.md](./card-topup.es.md) · **Français:** [card-topup.fr.md](./card-topup.fr.md)
>
> 代码：[`card_topup.py`](../aimarket_hub/card_topup.py) · 路由见 [`hub_routes/accounts.py`](../aimarket_hub/hub_routes/accounts.py) · [`credits.py`](../aimarket_hub/credits.py)（`deposit`） · 测试 [`test_card_topup.py`](../tests/test_card_topup.py)

[USDC 充值](credits-topup.zh.md)让持有钱包的智能体为自己的额度账户充值。只有银行卡、没有钱包的人此前无法充值。这扇门像普通商店一样收卡，并把钱记入与 USDC 充值**相同**的账本行（`CreditsLedger.deposit`，类型 `topup`）。因此此后额度轨道上的一切——付费调用、[授权书](mandates.zh.md)、分包、A2A——都照常运作。

**状态。** 自 2026-10-20（3.16.0）起提供，**默认关闭**。2026 年 10 月 20–21 日已在 Stripe 官方沙箱验证：无税付款、包含非零增值税的 Managed Payments 付款、含税与无税的全额退款，以及争议。下文明确列出覆盖范围和未验证项目。没有转移真实资金。

<a id="sandbox-verification"></a>
## Stripe 官方沙箱验证范围

这些验证使用 Stripe 托管的 Checkout、测试卡、真实 Stripe API 响应，以及由官方 Stripe CLI 转发到隔离本地枢纽的签名事件。它们与在 HTTP 边界模拟 Stripe 的单元测试不同。[验证记录](evidence/stripe-sandbox-2026-10-21.json)包含金额、事件 ID、投递结果和账本检查；记录中的时间均为 UTC。

| 场景 | 已观察到的结果 |
|---|---|
| `off`：无税付款 | 支付 5 美元，`checkout.session.completed` 恰好入账一次，额度为 5 美元；重复投递未增加额度。 |
| `stripe_tax` | 已验证在沙箱创建并打开 Checkout。此模式下的付款、非零税额、退款和争议**尚未验证**。 |
| `managed_payments` + `exclusive` | 荷兰测试买家：5 美元 + 21% 增值税（1.05 美元）= 6.05 美元；付款为 `paid`，税额计算为 `complete`，纳税责任为 `stripe`。枢纽通过 `refresh` 恰好入账一次，额度为 5 美元。该次运行未验证最初付款的 webhook。 |
| 含税全额退款 | Stripe API 对 6.05 美元退款返回 `succeeded`，其中包含 1.05 美元税额。签名 `charge.refunded` 获得 HTTP 200，枢纽状态变为 `refunded`。退款由运营者请求；未测试 Stripe 主动发起的自动退款。 |
| 无税全额退款（`off`） | 退回 5 美元，状态为 `succeeded`；签名 `charge.refunded` 获得 HTTP 200，状态变为 `refunded`。 |
| 无税争议（`off`） | 测试卡 `4000 0000 0000 0259` 产生了一笔真实沙箱争议：金额 5 美元、原因为 `fraudulent`、Stripe 状态为 `needs_response`；`charge.dispute.created` 将充值状态设为 `disputed`。 |
| 重复及延迟事件 | Stripe 重新投递付款、退款和争议事件。延迟付款事件未改变 `refunded`/`disputed` 状态；每个账户只有一条 5 美元的 `topup` 账目，没有重复入账。 |
| 价内税（`inclusive`） | 金额校验由本地测试覆盖；官方沙箱中的实际付款及退款**尚未验证**。 |

**发现并修复了事件顺序缺陷。** 第一次争议测试中，Stripe 在付款完成事件之前投递了争议，旧处理器返回了 `ignored`。现在枢纽会根据 PaymentIntent 查找 Checkout Session，验证它与本地充值记录的关联，并按该记录保存的税务模式核对付款，再记录退款或争议。查询失败会返回可重试错误。随后刻意先投递真实退款、再投递付款事件：退款正确记录，Stripe 延迟重投付款后仍保持 `refunded`。争议先到的顺序也有回归测试；重投恢复了第一次争议，新的一次付款及争议测试通过。会话 ID 和金额校验仍然生效。

**已确认的余额策略：** 退款和争议会记录状态并将账户写入错误日志，但不会自动扣减额度或冻结账户。每个测试账户在退款或争议后仍有 5 美元额度。运营者需要决定并执行余额调整。

**官方沙箱中尚未验证：** 部分退款、异步失败退款、争议胜诉或败诉、Managed Payments 下的争议，以及 `stripe_tax` 和 `inclusive` 的付款及退款。沙箱成功并不证明生产环境的 Managed Payments 使用资格；生产模式仍由运营者决定。

参考：[Stripe 测试卡与争议](https://docs.stripe.com/testing#disputes)、[退款 API](https://docs.stripe.com/api/refunds/create)、[按 PaymentIntent 查找 Checkout Session](https://docs.stripe.com/api/checkout/sessions/list)。

## 目录

- [Stripe 官方沙箱验证范围](#sandbox-verification)
- [简要流程](#简要流程)
- [买家看到什么](#买家看到什么)
- [枢纽检查什么](#枢纽检查什么)
- [销售税：三种模式](#销售税三种模式)
- [webhook 没有到达时](#webhook-没有到达时)
- [退款与争议](#退款与争议)
- [限额与设置](#限额与设置)
- [这扇门不做的事](#这扇门不做的事)
- [运营者](#运营者)
- [在 Stripe 沙箱中逐步测试](#在-stripe-沙箱中逐步测试)

## 简要流程

```bash
# 1. 为您的账户开立一笔 10 美元额度的支付。
curl -s -X POST $HUB/ai-market/v2/account/topup/card -H "X-API-Key: $KEY" \
     -H 'Content-Type: application/json' -d '{"amount_usd": 10}'
# → 201 {"topup_id": "ctp_…", "checkout_url": "https://checkout.stripe.com/…", "status": "open",
#        "amount_usd": 10, "charge_usd": 10, "fee_usd": 0, "expires_at": "…", "status_url": "…"}

# 2. 由人打开 checkout_url 并付款。Stripe 随后将其带回 status_url。

# 3. Stripe 确认后额度到账；随时可以查询状态：
curl -s $HUB/ai-market/v2/card-topups/ctp_…
```

智能体自己无法用银行卡付款：它把 `checkout_url` 交给自己的人，然后等待（或轮询状态）。这正是这扇门的意义：人来付款，智能体在其[授权书](mandates.zh.md)范围内支出。

## 买家看到什么

一个由 Stripe 托管的页面（`checkout.stripe.com`），只有一行：“Prepaid credit on <枢纽主机>: $10.00”（若运营者设置了附加费，还会显示 “incl. $x card fee”）。开启税务模式时，页面还会要求填写账单地址并显示税额；使用 Managed Payments 时，会显示 Stripe 的条款和卖家名称。页面**一小时**后过期；重新开立只需一个请求。付款后，Stripe 把买家带到 `status_url`，枢纽以 JSON 返回充值状态。

银行卡号从不到达枢纽——枢纽根本看不到它。PCI 合规范围留在 Stripe。

## 枢纽检查什么

Stripe 调用 `POST /ai-market/v2/stripe/webhook`。在读取事件的任何内容之前，必须先验证 `Stripe-Signature`：用端点密钥对 `t.payload` 计算 HMAC-SHA256，`t` 不超过五分钟，恒定时间比较（轮换密钥期间接受多个 `v1` 签名）。然后把事件中的会话与枢纽开立的记录核对——绝不反过来：

| 检查 | 原因 |
|---|---|
| 充值 id 是本枢纽开立的 | 事件可以指名一笔充值，但不能创建充值 |
| 会话 id 等于开立时 Stripe 给出的 id | 其他支付的已付会话不能冒充本次 |
| `payment_status == "paid"` | 已完成但未付款（异步）的会话暂不入账 |
| `currency == "usd"`，且金额按开立时的税务模式与枢纽请求的金额一致（[见下文](#销售税三种模式)） | 金额和账户由枢纽决定，而不是由事件决定 |
| 使用正式密钥（`sk_live_…`、`rk_live_…`）时，会话必须为 `livemode` | 测试资金永远不会给正式枢纽入账 |

额度记入开立时绑定的账户，金额为所请求的额度。银行卡附加费和税款都不计入额度。账本行以会话 id 为引用，因此重复投递的事件——或两次同时投递——只入账一次。Stripe 只知道充值 id，不知道账户。

关于其他事情的事件会被确认（`200`）并忽略，以免 Stripe 连续数天重试。`checkout.session.expired` 会关闭该记录。

## 销售税：三种模式

由谁计算并承担销售税（增值税/VAT、GST、美国销售税）由运营者决定。这是一项设置 `AIMARKET_CARD_TOPUP_TAX`，枢纽把模式**保存在每笔支付的记录里**：按某种模式开立的支付，即使运营者在付款前更改了设置，也仍按该模式核对。

| 模式 | 卖家 | 谁计算税款 | 谁申报并缴纳 | 银行卡费用之外的 Stripe 费用 |
|---|---|---|---|---|
| `off`（默认） | 运营者 | Stripe 中无人计算 | 运营者，在 Stripe 之外 | — |
| `stripe_tax` | 运营者 | Stripe Tax，依据买家账单地址 | 运营者（Stripe Tax 提供申报报表） | Stripe Tax 定价 |
| `managed_payments` | **Stripe**（记录商户，merchant of record） | Stripe | Stripe | 每笔交易 3.5% |

**枢纽开立的支付有何变化：**

| 模式 | Checkout Session 的额外参数 | API 版本 |
|---|---|---|
| `off` | 无 | `2024-06-20` |
| `stripe_tax` | `automatic_tax[enabled]=true`、`billing_address_collection=required`、`price_data[tax_behavior]`、`product_data[tax_code]` | `2024-06-20` |
| `managed_payments` | `managed_payments[enabled]=true`、`price_data[tax_behavior]`、`product_data[tax_code]`。不发送 `automatic_tax`、`billing_address_collection` 或支付方式参数：与 Managed Payments 同时出现时 Stripe 会拒绝，因为地址由它收集、支付方式由它选择。 | `2025-03-31.basil`（最早支持 Managed Payments 的版本）；枢纽也用它读取此类支付 |

**税额加在价外还是含在价内。** `AIMARKET_CARD_TOPUP_TAX_BEHAVIOR`：

- `exclusive`（默认）——税额加在价格之上。对来自增值税率 21% 国家的买家，10 美元的充值需支付 12.10 美元；枢纽检查会话的 `amount_subtotal` 恰好为 10 美元，且 `amount_total` 恰好等于 `amount_subtotal + total_details.amount_tax`——任何折扣或其他行都不能改变它。入账 10 美元额度；2.10 美元作为 `tax_usd` 记在记录中。
- `inclusive`——税额包含在价格中。买家支付 10 美元，其中含税，运营者实收更少；枢纽检查 `amount_total` 恰好为 10 美元且税额不为负。入账 10 美元额度。

**商品税码**——`AIMARKET_CARD_TOPUP_TAX_CODE`，默认 `txcd_10000000`（“General — Electronically Supplied Services”，一般电子服务）。对于 AI 能力市场，`txcd_10105002`（“人工智能即服务——云端——商业用途”）或 `txcd_10701410`（“以电子方式提供的信息服务——商业用途”）可能更合适；正确的税码应咨询运营者的会计师。使用 Managed Payments 时，税码必须在 Stripe 的 “Eligible for Managed Payments” 列表中。

**枢纽无法理解的设置会关闭这扇门**，而不是凭猜测开立支付：未知的模式、不符合 `txcd_` + 8 位数字的税码、或 `exclusive`/`inclusive` 以外的行为，都会让 well-known 显示 `"enabled": false` 并给出原因。

**买家和 well-known 看到什么。** `payment_rails.credits.topup_card.tax` 为 `{"mode": "off"}`，或 `{"mode", "behavior", "seller_of_record": "operator" | "stripe"}`。付款后，充值状态包含 `tax: {mode, behavior, tax_usd}`。

### Managed Payments：开启前必读

谁能使用由 Stripe 决定，其条件在这里很重要：

- **仅限直接销售。** Stripe 的资格页面写明，产品必须“直接销售给客户，而不是通过平台或市场”。本枢纽是一个市场：在此购买的额度用于独立提供方的能力。Stripe 是否接受市场的预付额度使用 Managed Payments 由 Stripe 决定；在依赖它之前请先询问 Stripe。
- **仅限数字化、自动化的产品**，并使用符合资格的税码；企业所在国需受支持（列表包括欧盟国家、英国、瑞士、挪威、美国、加拿大、澳大利亚、中国香港、日本和新加坡）。
- **Stripe 可能在 60 天内退款**以避免拒付，并适用消费者冷静期规则。每笔退款都会以 `charge.refunded` 到达枢纽（[见下文](#退款与争议)）。
- 请先在控制台（Settings → Managed Payments）中开启，再设置该模式，否则 Stripe 会拒绝开立支付（`502 stripe_refused`，不会扣款）。

### Stripe Tax：开启前

在控制台：Tax → 设置（发货地址、默认税码）以及**税务登记**——Stripe Tax 只在运营者已登记的地区收税。若买家所在国没有登记，税额为零，枢纽会接受（`amount_tax: 0`）。

## webhook 没有到达时

`POST /ai-market/v2/card-topups/{id}/refresh` 向 Stripe 查询会话并执行同样的检查。任何持有 id 的人都可以调用（按调用方限频）：它只能给支付绑定的账户入账。因此，已付款的充值不会因为投递丢失而落空。

## 退款与争议

- **`charge.refunded`**——在 Stripe 中发生的退款（由运营者，或在 Managed Payments 下由 Stripe 本身）会把充值标为 `refunded`，并记录一条包含账户和金额的错误日志。额度**不会**被自动扣回：它可能已经花掉，而让余额变为负数是一个决定，而不是条件反射。由运营者手动更正。
- **`charge.dispute.created`**——拒付会把充值标为 `disputed` 并记录错误日志。账户不会被自动冻结。

## 限额与设置

| 变量 | 默认值 | 作用 |
|---|---|---|
| `AIMARKET_CARD_TOPUP_MIN_USD` | `5` | 最小充值额（不低于 Stripe 的 0.50 美元）。 |
| `AIMARKET_CARD_TOPUP_MAX_USD` | `100` | 单笔最大充值额。 |
| `AIMARKET_CARD_TOPUP_DAILY_USD` | `200` | 单个账户 24 小时内可用银行卡购买的最高额度。未到期的支付（1 小时）也计入，因为其中任何一笔仍可能被付款；已退款或有争议的充值继续计入，因为其额度仍留在账户上。同一时刻发起的支付会相互核对：合计不能超过限额。 |
| `AIMARKET_CARD_TOPUP_FEE_PCT` | `0` | 按百分比的附加费，付款前显示，不计入额度。`0`：银行卡手续费由运营者承担。在限制对银行卡收取附加费的地区，请保持 `0`。 |
| `AIMARKET_CARD_TOPUP_FEE_FIXED_USD` | `0` | 每笔支付的固定附加费。 |
| `AIMARKET_CARD_TOPUP_TAX` | `off` | `off`、`stripe_tax` 或 `managed_payments`（[见上文](#销售税三种模式)）。 |
| `AIMARKET_CARD_TOPUP_TAX_BEHAVIOR` | `exclusive` | `exclusive`（价外）或 `inclusive`（价内）。 |
| `AIMARKET_CARD_TOPUP_TAX_CODE` | `txcd_10000000` | Stripe 商品税码。 |

每日限额用于限制被盗银行卡的损失：争议到达时额度可能已经花掉，而枢纽无法收回已花掉的额度。

## 这扇门不做的事

- 退款或争议后**扣回额度**——只记录日志，由人工更正。
- 发生争议时**冻结账户**。
- **开具发票。** 若 Stripe 账户已设置，Stripe 会把自己的收据发到付款人的邮箱（使用 Managed Payments 时始终如此）。以运营者名义开具的法定发票以及销售的记账方式，是运营者的事务，取决于其所在司法辖区。

## 运营者

### 开启这扇门

1. 运营者名下的 Stripe 账户。**账户国家之后无法更改**；对于真实资金，必须是收取打款的法人实体所在国。
2. 只有一项权限 *Checkout Sessions: Write* 的**受限密钥**（Developers → API keys → Create restricted key → Custom permissions）。枢纽只需要这些：开立支付并读取。放入 `STRIPE_SECRET_KEY_FILE`（docker secret）或 `STRIPE_SECRET_KEY`。
3. 控制台中的 webhook 端点：`https://<枢纽>/ai-market/v2/stripe/webhook`，事件为 `checkout.session.completed`、`checkout.session.async_payment_succeeded`、`checkout.session.expired`、`charge.dispute.created`、`charge.refunded`。其签名密钥放入 `STRIPE_WEBHOOK_SECRET_FILE`（或 `STRIPE_WEBHOOK_SECRET`）。
4. `AIMARKET_CARD_TOPUP_ENABLED=1`；额度轨道必须开启（`AIMARKET_CREDITS_ENABLED=1`）。
5. 可选：在完成该模式的控制台步骤后，设置税务模式（`AIMARKET_CARD_TOPUP_TAX`）。

well-known 会说明这扇门是否开启以及未开启的原因：`payment_rails.credits.topup_card` = `{"enabled", "provider": "stripe-checkout", "create", "status", "currency", "min_usd", "max_usd", "daily_usd", "fee_pct", "fee_fixed_usd", "tax"}` 或 `{"enabled": false, "reason": "…"}`。

### 路由

| 路由 | 调用方 | 作用 |
|---|---|---|
| `POST /ai-market/v2/account/topup/card` | 账户的 `X-API-Key` | 开立支付（`{"amount_usd"}`）→ `201`，含 `checkout_url`；每个账户每分钟 6 次 |
| `GET /ai-market/v2/card-topups/{id}` | 持有 id 的任何人 | 状态；账户只对其自身密钥显示 |
| `POST /ai-market/v2/card-topups/{id}/refresh` | 持有 id 的任何人 | 与 Stripe 对账，已付款则入账 |
| `POST /ai-market/v2/stripe/webhook` | Stripe（已签名） | 事件 |
| `GET /ai-market/v2/account/topups` | 账户密钥 | 在 USDC 充值 `topups` 旁列出 `card_topups` |

### 错误

| 状态码 | `error` | 含义 |
|---|---|---|
| 400 | `amount_invalid`、`amount_out_of_range` | 不是整数分，或超出最小/最大值 |
| 400 | `signature_invalid` | webhook 签名验证失败（不读取任何内容） |
| 401 | `api_key_required` | 缺少 `X-API-Key` 或密钥未知 |
| 429 | `daily_topup_limit`、`too_many_attempts` | 超出每日限额（未到期支付也计入），或每分钟开立支付过多 |
| 502 | `stripe_refused` | Stripe 未开立支付（例如未开启 Managed Payments 或密钥缺少权限）；未扣款 |
| 503 | `card_topup_unavailable`、`stripe_unavailable` | 这扇门已关闭（原因中有说明），或无法连接 Stripe |

webhook 返回 `{"received": true, "outcome": …}`：`credited`、`already_credited`、`pending`、`refused`（金额不一致——记录为错误，不入账）、`expired`、`disputed`、`refunded` 或 `ignored`。

### 数据表

`card_topups`（迁移 056 和 057）：每笔支付一行——`topup_id`、`account_id`、`amount_cents`（额度）、`charge_cents`（银行卡支付的税前金额）、`status`（`new` → `open` → `credited` / `expired` / `failed` / `disputed` / `refunded`）、`session_id`、`payment_intent`、`livemode`、`credited_mc`、`tax_mode`、`tax_behavior`、`tax_cents`、时间戳。

## 在 Stripe 沙箱中逐步测试

这扇门正是在 2026-10-20 这样验证的；在正式上线前以及更改税务模式后请重复一遍。这里不会动用真实资金。

1. **沙箱。** 在 stripe.com 注册，跳过所有激活步骤（证件、银行账户）。在控制台中打开沙箱（顶部会显示 “Sandbox” 横幅）。
2. **受限密钥**，只有 *Checkout Sessions: Write*。复制后直接从剪贴板保存，确保它从不被粘贴到聊天或终端中：`pbpaste > ~/.aimarket-stripe-test-key && chmod 600 ~/.aimarket-stripe-test-key`。
3. **Stripe CLI**，用于把沙箱事件送到您机器上的枢纽。若 Homebrew 拒绝安装（Command Line Tools 过旧），请从 GitHub 官方发布页下载 macOS 版本，并用 `stripe-mac-checksums.txt` 校验。然后运行 `stripe login` 并选择**沙箱**（不要选正式账户，也不要选旧的 “Test mode”）。
4. **CLI 使用的 webhook 密钥：** `stripe listen --print-secret > ~/.aimarket-stripe-whsec`。
5. **本地枢纽**，设置 `AIMARKET_CREDITS_ENABLED=1 AIMARKET_CARD_TOPUP_ENABLED=1 STRIPE_SECRET_KEY_FILE=~/.aimarket-stripe-test-key STRIPE_WEBHOOK_SECRET_FILE=~/.aimarket-stripe-whsec`（以及要测试的税务模式）。
6. **转发事件：** `stripe listen --forward-to http://127.0.0.1:<端口>/ai-market/v2/stripe/webhook --events checkout.session.completed,checkout.session.async_payment_succeeded,checkout.session.expired,charge.dispute.created,charge.refunded`。`stripe trigger checkout.session.completed` 必须显示 `[200]`：签名验证通过（密钥错误时为 `[400]`）。
7. **一笔支付：** 用账户密钥调用 `POST /ai-market/v2/account/topup/card {"amount_usd": 5}`；由人打开 `checkout_url`，用 `4242 4242 4242 4242` 付款，有效期填任意未来日期，CVC 任意。
8. **检查：** CLI 显示 `checkout.session.completed` → `[200]`；充值状态为 `credited`；账户账本中恰好有一行对应的 `topup`。然后运行 `stripe events resend <evt_…>`：再次 `[200]`，余额不变。
9. **可选：** 用卡号 `4000 0000 0000 0259` 测试争议 → 充值变为 `disputed`；在控制台中退款 → `refunded`。
