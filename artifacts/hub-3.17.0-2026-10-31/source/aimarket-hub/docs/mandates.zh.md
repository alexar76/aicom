# 授权书、分包与收据锚定

> **English:** [mandates.md](./mandates.md) · **Русский:** [mandates.ru.md](./mandates.ru.md) · **Español:** [mandates.es.md](./mandates.es.md) · **Français:** [mandates.fr.md](./mandates.fr.md)
>
> 代码：[`mandates.py`](../aimarket_hub/mandates.py) · [`subcontract.py`](../aimarket_hub/subcontract.py) · [`invoke_funding.py`](../aimarket_hub/invoke_funding.py) · [`anchoring.py`](https://github.com/alexar76/aimarket-plugins/blob/main/plugins/aimarket-provenance/aimarket_provenance/anchoring.py)

规范文本是 [`aimarket-protocol/mandates.md`](https://github.com/alexar76/aimarket-protocol/blob/main/mandates.md)（授权书（mandate）为 AMD/1，分包为 SUB/1）。本页说明如何在这个枢纽（Hub）上运行和使用它。

## 每个部分的用途

| 部分 | 回答的问题 | 代码 |
|---|---|---|
| **授权书** | “谁授权了这笔支出，上限多少，用在什么上？”所有者为智能体的密钥签署限额；枢纽自行执行这些限额。智能体从不持有所有者的 API 密钥。 | `aimarket_hub/mandates.py` |
| **分包** | “这个提供方在为我服务时向另一个提供方购买了东西——用的是谁的钱，在我的账单上的哪里？” | `aimarket_hub/subcontract.py` |
| **出资层** | 在支付路径运行之前决定谁付款、受谁的限额约束；之后结算它打开的一切。 | `aimarket_hub/invoke_funding.py` |
| **锚定** | “枢纽以后能否否认某张收据或篡改其日期？”每张工作凭证的摘要都会进入 HISTOR 的公开收据日志。 | `plugins/aimarket-provenance/aimarket_provenance/anchoring.py` |

这三个涉及资金的部分都建立在**额度轨道（credits rail）**上——这是枢纽唯一自行计量资金的轨道。授权书或分包额度（allowance）从不与支付通道、x402 付款或沙箱访客 id 一同出现：枢纽拒绝这种组合（`400 mandate_rail_unsupported`，对 grant 则为 `403 job_invalid`），而不是去执行一个它看不见的限额。

## 金额限制与过期边界

- `perCall` 限制单次调用预留的金额，包括适用的路由费。`perDay` 按 **UTC 自然日**计算，而非滚动 24 小时；`total` 是可选的累计预算。这些是金额限制，不是请求次数限制；没有内置的每小时金额上限。
- 授权书及其所有祖先仅在 `validFrom <= now < validUntil` 时可用。**恰好到达 `validUntil` 就已经过期。** 这会终止对新工作的授权，但不承诺取消已开始的工作或执行链上退款。
- 关联出资账户所有者时，请设置 `require_mandate=True`。仅注册授权书并不能阻止持有原始 API 密钥的人在授权书之外消费。按 IP/会话计数的请求限流不是按密钥计算的金额预算。
- 底层预付余额和 API 密钥没有自动 TTL。预留恢复和内部额度返还遵循[额度生命周期](credits-topup.zh.md#credit-lifecycle)，并非现金支付，也不具有 escrow 合约的保证。

## 所有者：为智能体出资而无需交出你的密钥

```python
from aimarket_agent import AgentKey, issue_mandate, owner_link_payload
import httpx

HUB = "https://modelmarket.dev"                      # this hub's AIMARKET_HUB_URL, exactly
owner = AgentKey.from_seed_hex(OWNER_SEED_HEX)       # keep this offline
agent = AgentKey.generate()                          # this one goes to the agent

# 0. The account id your API key names.
ACCOUNT_ID = httpx.get(f"{HUB}/ai-market/v2/mandates/owners",
                       headers={"X-API-Key": API_KEY}).json()["account_id"]

# 1. Link your DID to your credit account (once). The API key proves the account, the
#    signature proves the key. require_mandate=True makes the raw API key stop paying.
httpx.post(f"{HUB}/ai-market/v2/mandates/owners", headers={"X-API-Key": API_KEY},
           json=owner_link_payload(owner, hub_origin=HUB, account_id=ACCOUNT_ID, require_mandate=True))

# 2. Issue and register a mandate for the agent key.
doc = issue_mandate(owner, agent.did, audience=[HUB], scope=["gaia.*", "atlas.nearest.read@v1"],
                    per_call_usd=0.02, per_day_usd=1.00, total_usd=10.00, valid_days=30)
reg = httpx.post(f"{HUB}/ai-market/v2/mandates", json=doc).json()
# {"digest": "sha256-…", "status": "active", "root": "sha256-…", "root_issuer": "did:key:…", "depth": 0, …}
```

要让智能体能够开启分包额度，请向 `issue_mandate` 传入 `subcontract_allowance_usd=` 和 `subcontract_max_depth=`（1–3）；没有它们，这份授权书无法为分包额度付款。

### 注册会拒绝什么

`POST /ai-market/v2/mandates` 不需要密钥：文档自己证明自己。枢纽检查规范（§3.2）中的字段规则和签名证明，然后拒绝以下情况：

| 应答 | 何时 |
|---|---|
| `403 mandate_invalid` "this mandate is not addressed to …" | `audience` 中没有与本枢纽的 `AIMARKET_HUB_URL` 完全一致的条目——协议、主机、端口和路径（挂载在 `/hub` 下的枢纽是 `https://example.net/hub`），末尾不带斜杠。枢纽永远不会为这样的授权书服务，因此也不存储它。应使用 `/.well-known/ai-market.json` 中的 `mandates.audience` 字符串。 |
| `402 mandate_unfunded` | 链的根签发方没有关联到本枢纽上的账户（第 1 步）。 |
| `403 mandate_invalid` "register the parent mandate first" | 一份再授权，其父授权书未在此处注册。 |
| `403 mandate_invalid` "… already registered a different mandate with id …" | 该签发方已经注册过另一份具有相同 `id` 的文档。每个签发方的一个凭证 id 只指代一份授权书；请用新的 `id` 签发新授权书（除非你传入 `mandate_id=`，`issue_mandate` 会生成一个 `urn:uuid:`）。 |
| `403 mandate_invalid` "the mandate has already expired" | `now >= validUntil`（不包含结束边界）。`validFrom` 尚未到来的授权书可以注册，读取时为 `pending`。 |
| `403 mandate_invalid` "numbers in a mandate must be integers" | 任何位置出现小数，或整数超出 ±(2^53 − 1)。金额是整数 µUSD。 |
| `400 mandate_malformed` | 请求体不是 JSON 对象、没有规范形式，或其规范形式超过 16 KiB。 |
| `413 mandate_malformed` | 原始请求体超过 20 KiB。 |

重复提交一份已注册的文档会得到相同的应答——注册按摘要幂等（若此后已被撤销，`status` 为 `revoked`）。

**proof 键规则。** `proof` 对象必须恰好包含 `@context`、`type`、`cryptosuite`、`created`、`verificationMethod`、`proofPurpose` 和 `proofValue`，且 `proof.@context` 必须等于文档的 `@context`。原因：命名一份授权书的摘要是对整个受保护文档（包括 proof）计算的，但 `eddsa-jcs-2022` 在对 proof 配置做哈希时，用的是*文档*的 `@context`，而不是 proof 自带的那个，因此 `proof.@context` 不在签名覆盖范围内。如果它可以随意填写，受授权书约束的智能体就能改写文档并一份接一份地注册副本——每份都有新的摘要和全新的限额计数器，而撤销原件对它们都没有影响。`issue_mandate` 和 ARGUS 的签名器生成的正是这种形式。在这条规则出现之前注册、且违反该规则的授权书，每次被枢纽读取时都会重新检查，现在显示为 `invalid`。

### 所有者与 `require_mandate`

只有账户的**第一个**所有者可以仅凭 API 密钥关联。此后，添加第二个 DID、取消关联某个 DID 或更改 `require_mandate`，都还需要一位现有所有者的签名——泄露的恰恰是 API 密钥，所以仅凭它不能撤销保护：

```python
from aimarket_agent import owner_unlink_payload

# another owner (key rotation), authorised by an existing one
owner_link_payload(new_owner, hub_origin=HUB, account_id=ACCOUNT_ID, require_mandate=True,
                   authorized_by=owner)
# switch require_mandate off for a DID that is already linked: a policy change
owner_link_payload(owner, hub_origin=HUB, account_id=ACCOUNT_ID, require_mandate=False,
                   authorized_by=owner, action="policy")
# unlink — body of POST /ai-market/v2/mandates/owners/unlink
owner_unlink_payload(old_owner.did, hub_origin=HUB, account_id=ACCOUNT_ID, authorized_by=owner)
```

每一项都要带上账户的 `X-API-Key`。没有有效所有者签名的变更得到 `403 owner_authorization_required`；已关联到其他账户的 DID 得到 `409 owner_linked_elsewhere`。`require_mandate` 按每个已关联的 DID 分别保存，只要账户的**任何一个** DID 开启了它，账户就处于锁定状态——要关闭，需要对每个这样的 DID 做一次策略变更。`GET /ai-market/v2/mandates/owners`（带 API 密钥）列出已关联的 DID 及其 `require_mandate`。丢失了所有密钥的所有者由运营者恢复：带 `Authorization: Bearer $AIMARKET_ADMIN_TOKEN`（以及 API 密钥）的同一请求可以代替所有者的签名。

开启 `require_mandate` 后，仅凭 API 密钥无法再动用余额：

- 普通调用得到 `402 mandate_required`，不带授权书而请求分包额度的调用也一样；
- 由额度账户出资的保证金（带 API 密钥和正数 `amount_usd` 的 `POST /ai-market/v2/supply/stake`）得到 `403`：保证金不会付给窃贼，但会把余额冻结为抵押品，并使其面临罚没。

由作业 grant 支付的子调用不受影响：它的资金已在根调用上获得授权。

### 撤销

使用 `POST /ai-market/v2/mandates/revoke` 撤销——由链中任一签发方签名（`revoke_payload(owner, hub_origin=HUB, digest=digest)`），或者作为紧急开关，只带 `{"digest"}` 和出资账户的 `X-API-Key`。撤销一份授权书会撤销从它再授权出去的一切。已经做出的预留照常结算。

### 超过阈值需所有者批准

在授权书的 `limits` 中加入 `approvalAbove`（µUSD），任何超过该金额的单次调用都不会直接支出，而是等待您的答复（[规范 §5.6](https://github.com/alexar76/aimarket-protocol/blob/main/mandates.md)）。小额调用照常无人值守运行；大额调用需要您对**这一次**调用签名。

1. 智能体超过阈值的调用返回 `402 approval_required`，附带 `approval` 块：`approval_id`、`capability_id`、`amount_usd`、`max_usd`（您批准的上限；路由调用包含路由费）、`body_sha256`（确切的请求）、`expires_at`（24 小时）和 `url`。不会预留任何资金。若授权书的其他限额（`perCall`、`perDay`、`total`、某产品的每日限额）无论如何都会拒绝该调用，则立即返回 `402 mandate_limit`——不会请您签署无法执行的调用。
2. 待处理的请求：用出资账户的 `X-API-Key` 调用 `GET /ai-market/v2/mandates/approvals?status=pending`。
3. 答复：`POST /ai-market/v2/mandates/approvals/{approval_id}`，正文 `{"decision": "approve", "by": <您的 DID>, "t", "n", "s"}`；`s` 是您对以下各行（以 `\n` 分隔）的 Ed25519 签名：`aimarket-mandate-approval/1`、枢纽基础 URL、`approval_id`、`approve`、授权书摘要、`body_sha256`、`max_micro`、`t`、`n`。账户的任一所有者 DID 都可签名。仅凭 API 密钥只能**拒绝**（`{"decision": "deny"}`）。
4. 智能体用新的证明再次发送同一请求。调用只执行一次；批准随之消耗，若调用在扣款前失败则退回。拒绝在请求到期前一直有效（`402 approval_denied`）。

每份授权书最多 16 个待处理请求（`429 approval_queue_full`）。再委托的授权书保留父级阈值，只能调低。通过 A2A 时，任务（Task）在 `AUTH_REQUIRED` 中等待，您答复后即推进，并向智能体的 webhook 发送推送通知。

### 调用等待您时收到通知

没有通知渠道时，所有者只能主动查询才知道有待处理的请求（上文第 2 步）。在出资账户上登记渠道后，枢纽会把每个新请求及其答复发送到那里。通知只是告知：批准仍需所有者密钥的签名，任何聊天、频道或工单都不持有该密钥；每条消息都会说明如何批准、如何拒绝。

```bash
# 通过枢纽的 Telegram 机器人（如果运营方提供）：先对它按 Start，再填写您的聊天 id
curl -X POST "$HUB/ai-market/v2/mandates/notify" -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"kind": "telegram", "chat_id": "123456789"}'
# ……或使用您自己的机器人：加上 "bot_token": "123456789:AA…"
curl -X POST "$HUB/ai-market/v2/mandates/notify" -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"kind": "slack", "webhook_url": "https://hooks.slack.com/services/T…/B…/…"}'
curl -X POST "$HUB/ai-market/v2/mandates/notify" -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"kind": "jira", "base_url": "https://acme.atlassian.net", "email": "ops@acme.example",
       "api_token": "…", "project_key": "OPS", "issue_type": "Task"}'
curl -X POST "$HUB/ai-market/v2/mandates/notify" -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"kind": "webhook", "url": "https://ops.acme.example/hooks/aimarket", "secret": "…"}'
# 立即发送一条测试消息，查看渠道的回应
curl -X POST "$HUB/ai-market/v2/mandates/notify/<channel_id>/test" -H "X-API-Key: $KEY"
```

| `kind` | 您需要提供 | 收到的内容 |
|---|---|---|
| `telegram` | `chat_id`（数字，或机器人担任管理员的 `@频道`）。使用自己的机器人时提供 `bot_token`；不提供则使用枢纽的机器人（如果运营方提供，`GET …/notify` 在 `telegram_bot` 中给出其名称）。 | 一条消息：哪个能力、多少钱、上限、有效期、如何批准与拒绝。使用 HTML；若 Telegram 拒绝该标记，则以纯文本发送同样内容。 |
| `slack` | 传入 webhook 的 `webhook_url`（`https://hooks.slack.com/services/…` 或 `/triggers/…`）。 | 同样的文本。 |
| `jira` | Jira Cloud 的 `base_url`（https）、`email`、`api_token`（id.atlassian.com → Security → API tokens）、`project_key`、`issue_type`（默认 `Task`）。 | 每个请求一个工单；答复以评论形式追加到该工单。 |
| `webhook` | `url`（https），可选 `secret`。 | `POST` 正文 `{"event": "mandate.approval.requested" \| "….approved" \| "….denied", "approval": {…}, "title", "text"}`，带 `X-AIMarket-Event`；设置了密钥时另带 `X-AIMarket-Signature: t=<unix>,v1=<对 "<t>.<body>" 的 HMAC-SHA256 十六进制值>`。 |

- `GET /ai-market/v2/mandates/notify` 列出账户的渠道及每个渠道最近一次投递的结果。机器人令牌、Slack URL、Jira 令牌、webhook 密钥等秘密仅用于发送，从不返回（Slack URL 只显示最后四个字符）。
- `POST …/notify/{channel_id}/test` 立即发送测试消息，并返回 `delivered` 及渠道的回应；`DELETE …/notify/{channel_id}` 删除渠道。每个账户最多 8 个。
- 渠道属于出资账户，因此会收到该账户出资的每份授权书的通知。渠道由账户的 API 密钥管理——同一密钥本来就能列出其待处理的请求。
- 每个地址都按调用方提供给本枢纽的任何地址来检查：仅限 https，不得指向私有或元数据网络，只解析一次并固定，不跟随重定向。投递在请求之外进行，无响应、5xx 或 429 时重试两次（2 秒和 10 秒后），且从不改变它所报告的请求。

### 读取授权书的状态

`GET /ai-market/v2/mandates/{digest}` 回应任何持有该摘要的人（未知摘要：`404 mandate_unknown`）。`status` 是授权书**作为一条链**的状态——父授权书已被撤销的再授权不能使用，无论它自己的记录看起来多么干净：

| `status` | 含义 |
|---|---|
| `active` | 现在可用。 |
| `revoked` | 它本身或某个祖先已被撤销。`revoked_at` 只在被直接撤销的那份授权书上填写；后代显示 `revoked_at: null`，原因写在 `status_reason` 中。 |
| `expired` | 它本身或某个祖先已超过其 `validUntil`。 |
| `pending` | 它本身或某个祖先尚未生效（`validFrom` 在未来）。 |
| `invalid` | 链不成立：缺少某个祖先、某个环节违反收窄规则，或存储的文档已不再通过字段规则。 |

其他字段为 `issuer`、`subject`、`parent`、`root`、`chain`（摘要，从根到叶）、`depth`（根为 0）、`valid_from`、`valid_until`、`revoked_at`，以及状态不是 `active` 时的 `status_reason`。

用量——`usage`：`day`、`spent_today_usd`、`per_day_usd`、`remaining_today_usd`、`spent_total_usd`，当授权书有 `total` 限额时还有 `total_usd` 和 `remaining_total_usd`——只对两类调用方添加：

- 根的出资账户，带其 `X-API-Key`；
- 链中的任何密钥——每个签发方和每个主体，这样所有者可以查看它再授权过的智能体——带一个针对 `GET`、空请求体和请求路径的请求证明（request proof）：

```python
from aimarket_agent import request_proof

digest = reg["digest"]
path = f"/ai-market/v2/mandates/{digest}"
proof = request_proof(owner, hub_origin=HUB, leaf_digest=digest, body=b"", method="GET", path=path)
httpx.get(f"{HUB}{path}", headers={"X-AIMarket-Mandate-Proof": proof}).json()["usage"]
```

验证不通过的证明得到 `401 mandate_proof_invalid`，而不是状态。支出会记在链中的每一份授权书上，因此父授权书的数字包含其再授权所花的钱。`day` 是日计数器所覆盖的 UTC 自然日。

## 智能体：用授权书付款

```python
from aimarket_agent import AIMarketAgent, Mandate

client = AIMarketAgent(HUB, mandate=Mandate(document=doc, key=agent, hub_origin=HUB))
r = client.invoke_single("gaia.gateway", "gaia.weather.read@v1", {"latitude": 60.17, "longitude": 24.94})
r["mandate"]    # {"digest", "agent", "principal", "depth"} on a delivered call
```

每次调用都对其确切的请求体、枢纽、方法和路径以及一次性 nonce 签名，且须在枢纽时钟的 300 秒之内。路径**相对于枢纽的基础 URL**：对于发布在 `https://example.net/hub` 的枢纽，向 `https://example.net/hub/ai-market/v2/invoke` 发出的 POST 签名的是 `POST /ai-market/v2/invoke`，而 `hub_origin` 为 `https://example.net/hub`。`Mandate` 默认就签这个路径。

枢纽拒绝时返回什么：

- 超出限额：`402 mandate_limit`，`limit` 指明是哪一项（`perCall`、`perDay`、`total`、`perProductPerDay`，分包额度则为 `subcontract.perCallAllowance`），`mandate` 指明链中拒绝的那份授权书。`perCall` 涵盖一次调用所预留的全部金额——对联邦调用而言，是价格与路由费之和。按产品计的限额统计的是枢纽实际执行的产品，而不是调用方填写的 `product_id`；
- 超出范围（scope）：`403 mandate_scope`；未知、已过期、已撤销或并非发给本枢纽：`403 mandate_invalid`；签名错误、`t` 过期或 nonce 重复：`401 mandate_proof_invalid`；只能凭授权书付款的账户在没有授权书的情况下被调用：`402 mandate_required`。

SDK 把授权书或作业的 403 拒绝返回为 `{"refused": True, "error": …, "detail": …}`，而不是 `safety_blocked`——后者留给内容安全闸门。402、401 或 400 以枢纽的应答体返回（`error`、`detail`，以及存在时的 `limit` / `mandate`）。

枢纽运行的提供方会收到 `X-AIMarket-Agent`（叶的主体）和 `X-AIMarket-Principal`（根签发方）——由枢纽担保的调用者身份——而不会得到任何关于账户或限额的信息。路由到对等枢纽的调用不会发送这两个头：对等方没有验证过这份授权书。

同一份授权书也可通过 A2A 付款（`POST /a2a`，[a2a.md](a2a.md)）：这些头随 A2A 请求发送，调用放在一个原始 `application/json` 部分中，承载证明所签名的确切字节——仍然针对 `POST /ai-market/v2/invoke`。达到限额时，结果是一个 `REJECTED` 状态的 A2A 任务（Task）。读回你的 A2A 任务（`GetTask`、`ListTasks`）需要一个针对 `POST /a2a` 和 JSON-RPC 请求体的新证明。`aimarket_agent.A2AClient(HUB, mandate=…)` 和 ARGUS 的 `argus a2a invoke` 两者都会处理。

**ARGUS** 以同样方式付款。`argus mandate keygen` 打印一个新的智能体 `did:key` 及其密钥；所有者向该 DID 签发授权书并注册；`ARGUS_AGENT_KEY`（密钥）和 `ARGUS_MANDATE_FILE`（授权书 JSON）让 ARGUS 改用它。`argus mandate status` 显示链的状态和支出，`argus mandate delegate --to <did:key> --per-call <usd> --per-day <usd>` 为子智能体注册一份更窄的再授权。

## 提供方：在作业中雇用另一个提供方

> 完整指南——流程与资金图、每一步资金所在的位置、谁承担哪种风险、其他枢纽上的子调用、A2A、错误以及运营者说明——见 [subcontracting.zh.md](subcontracting.zh.md)。本节是简要版本。

本枢纽通过调用 URL 执行的每个提供方都会收到 `X-AIMarket-Job`（一个令牌，用枢纽在其 well-known 中以 `signer_public_key` 公布的密钥签名，有效期 60 秒）和 `X-AIMarket-Hub`（向哪里出示它）；当买家留出了分包额度时，还会收到 `X-AIMarket-Job-Grant`，即 grant（从分包额度中支出的凭证）。在为该调用服务期间购买任何东西时，都把它们原样发回：

```python
from aimarket_agent import AIMarketAgent, JobContext

job = JobContext.from_headers(request.headers)       # None when the hub sent no token
buyer = AIMarketAgent(job.hub or HUB, api_key=MY_OWN_KEY)
r = buyer.invoke_single("wx", "wx.read@v1", {"q": 1}, job=job)
r["job"]    # {"job_id", "node", "parent", "depth", "funded_by"}
```

- 有 grant 时是**成本加成（cost-plus）**：这次购买由买家的分包额度支付，且不得随附其他任何东西——不能带 `X-API-Key`、授权书、通道或 x402 付款（`403 job_invalid`）；作业带有 grant 时，SDK 不会附加自己的付款。应答中的任何余额数字都是分包额度的剩余部分，而不是买家的余额。
- 没有 grant 时是**固定价格**：你用自己的轨道付款；这次购买仍会出现在买家的作业树中。

### 枢纽在作业中拒绝什么

| 应答 | 何时 |
|---|---|
| `403 job_invalid` | 令牌不是本枢纽签发的或已过期，或其对应的调用已经返回：令牌在调用结束后仍被持有的提供方，不能把购买嫁接到账单和收据都已发出的作业上。 |
| `402 allowance_exhausted` | grant 已关闭——它在根调用返回的那一刻关闭——或分包额度的剩余部分不足以支付价格。 |
| `403 job_limit` | `limit` 指明原因：`depth`（超出作业允许的深度）、`cycle`（该 capability 已在路径上）、`nodes`（作业已有 64 个调用，含根）、`children`（发起调用的节点已有 16 个子节点）。 |
| `403 mandate_scope` | 由 grant 出资、但超出根授权书范围的购买。 |
| `400 subcontract_unsupported` | 作业内的调用要求自己的分包额度；只有根可以设定分包额度。 |

作业允许的深度：没有分包额度（仅关联）时为枢纽上限 3——每一跳自己付款，所以深度只限制树的大小。有分包额度时为买家的 `max_depth`。加入树之后又被拒绝的子调用（例如超出根授权书范围，或根授权书在此期间被撤销）会交还它的名额，并在树中显示为 `refused`。

### 买家一方：分包额度与账单

买家在根调用上请求分包额度：

```python
r = client.invoke_single("brief", "brief.make@v1", {...},
                         subcontract={"allowance_usd": 0.005, "max_depth": 2})
```

`allowance_usd` 必须大于 0，且不超过 `AIMARKET_SUBCONTRACT_MAX_ALLOWANCE_USD`；`max_depth` 为 1–3（默认 1）。枢纽在买家的额度账户上同时预留价格和分包额度；对凭授权书的调用，还会在授权书链上预留，而链的叶必须带有同时约束这两个数值的 `subcontract` 块。若调用在链上或通过通道付款、既不带 `X-API-Key` 也不带授权书、或被路由到对等方，则为它请求分包额度会得到 `400 subcontract_unsupported`：枢纽只能转付它自己计量的资金。

根应答携带 bill of materials（物料清单）：

```json
"subcontracting": {
  "job_id": "job_…",
  "nodes": [
    { "node": "node_…", "parent": "node_…", "depth": 1,
      "product_id": "wx", "capability_id": "wx.read@v1",
      "price_usd": 0.001, "funded_by": "allowance", "status": "captured",
      "receipt_digest": "sha256-…", "receipt_id": "urn:uuid:…" }
  ],
  "spent_from_allowance_usd": 0.001,
  "allowance_usd": 0.005,
  "spent_usd": 0.001,
  "released_usd": 0.004
}
```

- `nodes` 是分包出去的调用；根本身不在其中。`status` 为 `running`、`captured`、`failed` 或 `refused`；`funded_by` 为 `allowance` 或 `own`。`receipt_id` 和 `receipt_digest` 指向子调用的 AWR/2 工作凭证。
- 由分包额度出资的节点，其 `price_usd` 是该调用实际从分包额度中取走的金额（见[下面的规则](#容易忽略的规则)）；`spent_from_allowance_usd` 是它们的总和。
- 只有设定了分包额度时才会出现 `allowance_usd`、`spent_usd` 和 `released_usd`。`spent_usd` 和 `released_usd` 是账本结算的结果；结算仍未完成时（一次释放失败，由清扫重试——见[滞留的分包额度](#滞留的分包额度)），它们为 `null`。`null` 并不表示什么都没花。
- **无论根是否交付**，这个块都在根的应答中。已交付的分包方即使在雇用它的提供方随后失败时也会得到付款（成本加成：消耗的物料要付钱），所以失败的根仍会返回解释这笔扣费的账单和 `job_id`。
- 枢纽通过提供方端点执行的每个调用都会获得一个作业 id，因此即使没有分包，它的应答中也有 `subcontracting` 块（`"nodes": []`）。

`GET /ai-market/v2/jobs/{job_id}` 稍后返回这棵树：相同的节点，加上根自己的节点（`depth` 0）、`spent_from_allowance_usd`，有分包额度时还有 `allowance_usd`、`max_depth`、`allowance_status`，以及结算记录后的 `spent_usd` / `released_usd`。作业 id 是一个无法猜测的能力凭据（capability）：持有它的人都能读取这棵树，而枢纽只把它交给根买家和该作业的提供方。

根的 AWR/2 工作凭证在 `credentialSubject.parents` 中列出每个已交付子调用的工作凭证：`id` 是子调用的 `receipt_id`，`digestSRI` 是它的 `receipt_digest`。每个子调用的凭证对它自己的子调用也做同样的事，所以这棵树是逐跳承诺的，而不只是报告出来的。

无论买家要求什么，枢纽都执行这些限制：深度 ≤ 3，每个作业 64 个调用（含根），每个调用 16 个子调用，禁止循环（capability 已在路径上），令牌存活 60 秒（提供方 30 秒超时再加 30 秒），grant 随其根调用一起失效。

### 容易忽略的规则

- **另一个枢纽上的子调用需要 `source_hub`。** 只有根必须在本枢纽上执行；子调用可以是本枢纽能路由的任何 capability，其价格（对于转售的对等方，还有路由费）与本地调用一样从分包额度中扣出。但如果没有 `source_hub: <由 /search 返回的对等方 URL>`，枢纽会寻找本地 capability，只找到对等方的上架条目并回答 `400`——而这次尝试仍会占用该调用 16 个子调用名额中的一个，并在账单中显示为失败的节点。
- **作业令牌和 grant 永远不会离开本枢纽。** 被路由的子调用到达对等方时不带这两者；关联关系和资金都留在枢纽能计量的地方。
- **在花钱之前验证令牌。** 你的调用 URL 是公开的。用枢纽的 `signer_public_key`（来自 `/.well-known/ai-market.json`）检查签名，检查 `iss` 是你所服务的枢纽、`exp`、`path` 的最后一项是*你的* capability（枢纽会给它运行的每个提供方一个令牌——这可以防止另一个提供方把它自己的令牌重放给你），并且每个 `node` 只服务一次。其他一切都在购买任何东西之前拒绝。
- **路由子调用上的 `max_price_usd` 以整美分比较。** 枢纽对路由的 capability 报价为其价格加路由费并向上取整到美分，因此低于 $0.01 的上限会以 `409 price_limit_exceeded` 拒绝一个 $0.001 的子调用。
- **账单是对得上的。** 由分包额度出资的节点，其 `price_usd` 是该调用从分包额度中取走的金额（含路由费），所以这些节点之和等于 `spent_usd`，并且 `spent_usd + released_usd == allowance_usd`。预留已被释放的失败节点显示 0；仍然花了钱的失败节点（对等方已交付，随后路由费扣费失败）显示实际取走的金额。

### 完整示例：`weather.witness@v1`

[`examples/subcontract-capability`](../examples/subcontract-capability/) 是一个按这些规则构建、由枢纽运营者运行的真实提供方。针对一个地点，它通过调用它的那个枢纽、在调用方的作业内购买 `gaia.weather.read@v1` 和 `gaia.air.read@v1`（产品 `gaia.gateway`，`source_hub: https://iot.modelmarket.dev`），并以两份由设备证明的读数、它们在地点和时间上是否一致，以及每个子调用的作业节点和收据摘要作答，签名覆盖枢纽与请求绑定的规范形式。买家发送分包额度时为成本加成（令牌 + grant，别无其他）；否则为固定价格（令牌 + 它自己的 `X-API-Key`，在每日上限之内，没有密钥时拒绝）。

[`scripts/subcontract_canary.py`](https://github.com/alexar76/aicom/blob/main/scripts/subcontract_canary.py) 是根买家：

```bash
SUBCONTRACT_CANARY_API_KEY=aimk_… scripts/subcontract_canary.py            # cost-plus, allowance $0.01
SUBCONTRACT_CANARY_API_KEY=aimk_… scripts/subcontract_canary.py --fixed-price
SUBCONTRACT_CANARY_API_KEY=aimk_… scripts/subcontract_canary.py --a2a      # the root call over A2A 1.0
```

它断言：两个按预期出资并已扣费的子调用、`spent + released == allowance`、节点价格之和等于已花费金额、`GET /ai-market/v2/jobs/{job_id}` 返回同一棵树，以及子调用的收据摘要出现在根凭证的 `credentialSubject.parents` 中。

要清楚它证明了什么：它是**自我驱动的**——我们的买家、我们的组合服务、我们的 GAIA、内部额度账户。每一跳都走生产代码路径，每一项声明都从外部检查，这正是它的用途；它并不能证明有其他人想要这个产品。示例的 README 包含运营手册（systemd、nginx、保证金豁免、发布、金丝雀账户）。`tests/test_subcontract_example.py` 针对真实的枢纽应用运行该提供方和金丝雀。

## 运营者

### 配置

| 变量 | 默认值 | 作用 |
|---|---|---|
| `AIMARKET_CREDITS_ENABLED` | `0` | 授权书和分包额度需要开启额度轨道；关闭时，凭授权书的调用或带分包额度的调用得到 `503 mandates_unavailable`。作业令牌（关联）在两种情况下都可用。 |
| `AIMARKET_HUB_URL` | `http://localhost:9083` | 枢纽的公开基础 URL，挂载在某个路径下时包含该路径。它是授权书必须指明的 audience，也是每个证明所签名的源（origin），因此保持默认值的枢纽会拒绝所有发往其公开名称的授权书。 |
| `AIMARKET_SUBCONTRACT_MAX_ALLOWANCE_USD` | `1.0` | 一次根调用可预留的最大转付分包额度。 |
| `AIMARKET_SUBCONTRACT_SWEEP_S` | `120` | 滞留的分包额度多久清扫一次（见下文）。`0` 关闭清扫；小于 10 的值会被提高到 10。 |
| `AIMARKET_ADMIN_TOKEN` | 未设置 | 带它的 `Authorization: Bearer …` 可在所有者变更中代替所有者签名——即恢复途径。 |
| `AIMARKET_HISTOR_URL` | 未设置 | provenance 插件锚定收据摘要的位置；未设置 = 锚定关闭。 |
| `AIMARKET_HISTOR_FLUSH_S` | `30` | 发件箱（outbox）发送待处理锚点的频率（HISTOR 失败或推迟期间，间隔会退避增长到 10 分钟）。 |
| `AIMARKET_HISTOR_OUTBOX_RETAIN_DAYS` | `30` | 已锚定行在 outbox 中保留的天数；之后状态路由改为询问 HISTOR。`0` 表示全部保留。 |
| `AIMARKET_MANDATE_APPROVAL_TTL_S` | `86400` | 所有者批准请求保持开放的时长（300 秒至 7 天）；已批准的请求须在同一时间窗内使用。 |
| `AIMARKET_NOTIFY_TELEGRAM_BOT_TOKEN`（或 `…_FILE`） | 未设置 | 枢纽自己的 Telegram 机器人，用于批准通知：所有者只需提供聊天 id。未设置时，Telegram 渠道需要所有者自己的 `bot_token`。从不写入日志。 |
| `AIMARKET_NOTIFY_TELEGRAM_BOT_NAME` | 未设置 | 该机器人的 @名称，由 `GET /mandates/notify` 返回，让所有者知道该对谁按 Start。 |

镜像已安装 `awr`（provenance 插件需要它）。未安装它的枢纽可以正常启动，但对凭授权书的调用回答 `503 mandates_unavailable`。

客户端签名的请求路径相对于 `AIMARKET_HUB_URL`；在检查证明之前，枢纽会去掉 ASGI 服务器以 `root_path` 报告的挂载前缀。

### well-known 中的块

`/.well-known/ai-market.json` 在客户端发送任何内容之前就告诉它：本枢纽是否执行 AMD/1 和 SUB/1，以及采用哪些限制：

```json
"mandates": {
  "spec": "aimarket-protocol/mandates.md", "version": "AMD/1", "enabled": true,
  "audience": "https://modelmarket.dev",
  "register": "/ai-market/v2/mandates", "owners": "/ai-market/v2/mandates/owners",
  "revoke": "/ai-market/v2/mandates/revoke", "status": "/ai-market/v2/mandates/{digest}",
  "max_chain": 4
},
"subcontracting": {
  "spec": "aimarket-protocol/mandates.md#6-subcontracting-sub1", "version": "SUB/1",
  "job_tokens": true, "allowance": true, "max_allowance_usd": 1.0,
  "max_depth": 3, "max_nodes_per_job": 64, "max_children_per_node": 16,
  "jobs": "/ai-market/v2/jobs/{job_id}"
}
```

`mandates.enabled` 和 `subcontracting.allowance` 跟随 `AIMARKET_CREDITS_ENABLED`；`mandates.audience` 是去掉末尾斜杠的 `AIMARKET_HUB_URL`——正是授权书的 `audience` 必须包含的那个字符串；`max_allowance_usd` 跟随 `AIMARKET_SUBCONTRACT_MAX_ALLOWANCE_USD`。

### 滞留的分包额度

分包额度是买家额度账户上的一笔预留，其存续时间应当与根调用完全相同。如果根从未结算它——调用中途崩溃、释放一再失败——这笔钱就会一直被冻结。枢纽在启动时清扫一次，之后每隔 `AIMARKET_SUBCONTRACT_SWEEP_S` 秒清扫一次：对于 grant 已过期超过五分钟、且预留仍被占用的分包额度，将其关闭，释放剩余部分；凭授权书的分包额度，其在授权书链上的预留按子调用实际取走的金额结算；并记录结算结果，从而填上作业的 `spent_usd` / `released_usd`。每个周期最多处理 50 个分包额度；结算了任何分包额度时，会以 WARNING 级别记录 `subcontract: settled N stale allowance(s)`。清扫只在开启额度轨道时运行，且从不在请求路径上运行。

### 迁移 038

`038_job_receipts_and_settlement` 新增：

| 列 | 用途 |
|---|---|
| `job_nodes.work_receipt_id` | 子调用的工作凭证 id，由父凭证的 `parents` 边和账单中的 `receipt_id` 携带。 |
| `job_grants.spent_micro`、`released_micro`、`settled_at` | 分包额度的结算方式，使 `GET /jobs/{job_id}` 与根应答携带的账单一致。 |
| `mandates.credential_id`，以及 `(issuer, credential_id)` 上的唯一索引 | 每个签发方的一个凭证 id 只对应一份授权书。 |
| `mandate_holds.pending_back_micro` | 在分包额度的预留仍未关闭时到达的子调用退款，由关闭该预留的结算扣除。 |

它与枢纽的所有迁移一样在启动时应用。036 和 037 属于其他分支；版本号是一个集合而不是序列，因此枢纽可能显示 038 先于它们被应用。038 之前写入的行保留空的 `credential_id`（唯一索引会跳过它们）和空的 `work_receipt_id`（它们的 `parents` 边以 `urn:aimarket:job-node:…` 指代节点；摘要仍然承诺正确的字节）。

034 和 035 中的 µUSD 列为 `BIGINT`。在 SQLite 上，这与以前是同一种 64 位整数。在 034/035 仍写作 `INTEGER` 时就已应用它们的 PostgreSQL 枢纽，其列为 int4，上限为 $2,147.48，而已应用的迁移不会重新运行：请用 `ALTER TABLE … ALTER COLUMN … TYPE BIGINT` 修改 `mandate_usage.spent_micro`、`mandate_holds.amount_micro`、`job_nodes.amount_micro` 和 `job_grants.allowance_micro`。

枢纽通过提供方端点执行的每个调用在结束时都会在 `job_nodes` 中写入一行，无论它是否进行了分包。

### 在 HISTOR 中锚定收据

设置 `AIMARKET_HISTOR_URL` 后，provenance 插件会把每张工作凭证的摘要排入队列，由一个后台线程把队列发送到 HISTOR 的收据日志（发送什么、如何重试：见[插件的 README](https://github.com/alexar76/aimarket-plugins/blob/main/plugins/aimarket-provenance/README.md)）。HISTOR 只接受其运营者在 `HISTOR_RECEIPT_ISSUERS` 中列出的签发方的锚点，所以请把本枢纽收据签发方的 `did:key` 交给那位运营者。可以从任何一张真实收据上读取它——调用应答中的 `provenance_receipt.issuer`，或收据文档中的 `issuer.id`：

```bash
curl -s "$HUB/ai-market/v2/p/provenance/receipt/$RECEIPT_ID" | jq -r '.issuer.id'
```

插件在启动时也会把它写入日志（`Provenance issuing AWR/2 receipts as did:key:…`）。在 HISTOR 列入它之前，锚点会以 "issuer is not accepted" 被拒绝并保持 `pending`：枢纽会以退避方式重试最长 30 天，因此在两位运营者协调期间不会丢失任何东西。

`GET /ai-market/v2/p/provenance/anchor/{receipt_id}` 显示一张收据的状态：`pending`（带 `attempts` 和 `last_error`）、`anchored`（带 `leaf_index` 和指向 HISTOR 的 `proof_url`）、`refused`（带 `last_error`）、`not_queued`，或锚定关闭时的 `not_configured`。

**保留期过后，由日志作答。** 已锚定的行在超过 `AIMARKET_HISTOR_OUTBOX_RETAIN_DAYS`（默认 30；0 表示永久保留）后从 outbox 中删除；`pending` 与 `refused` 行永不删除。对于没有行的收据，该路由直接询问 HISTOR：在本枢纽密钥下指名该摘要的证明读作 `anchored`，并带 `"source": "log"`；日志中没有则为 `not_queued`；无法访问日志则为 `unknown`，绝不会是 `anchored`。答案会被记住（一小时、五分钟、三十秒），因此公开路由无法让枢纽反复轰击日志。

**开启锚定之前签发的收据。** 以其自身的签发时间排入队列，运行中枢纽的 outbox 会像其他行一样发送：

```bash
docker exec -it modelmarket-hub python -m aimarket_provenance.backfill --db /app/data/provenance.db --dry-run
docker exec -it modelmarket-hub python -m aimarket_provenance.backfill --db /app/data/provenance.db
```

只有通过验证、由本枢纽的 provenance 密钥签发、且在 HISTOR 30 天窗口内（留一小时余量）的收据才会入队；未设置 `AIMARKET_HISTOR_URL` 时命令拒绝运行，因此不锚定的枢纽不会发布任何内容。HISTOR 的窗口是为了防止倒签，所以早于窗口的收据无法以其真实时间锚定，保持原样。补锚的收据证明它在 HISTOR 记录的那一刻已经存在，而不是收据所声称的签发时间。

`/a2a` 和 `/.well-known/agent-card.json` 上的流量计入 `/metrics` 中的 `aimarket_hub_a2a_requests_total{method,result}`；invoke 类 A2A 任务按其到达的状态计数（见 [a2a.md](a2a.md)）。
