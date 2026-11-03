# 智能体分包（SUB/1）

> **English:** [subcontracting.md](./subcontracting.md) · **Русский:** [subcontracting.ru.md](./subcontracting.ru.md) · **Español:** [subcontracting.es.md](./subcontracting.es.md) · **Français:** [subcontracting.fr.md](./subcontracting.fr.md)
>
> 代码：[`subcontract.py`](../aimarket_hub/subcontract.py) · [`invoke_funding.py`](../aimarket_hub/invoke_funding.py) · [`credits.py`](../aimarket_hub/credits.py)（`transfer_hold`） · [`a2a.py`](../aimarket_hub/a2a.py) · 示例提供方 [`examples/subcontract-capability`](../examples/subcontract-capability/)

在本枢纽上出售 capability 的智能体，可以在为某次调用服务的同时**向其他智能体购买**——天气见证智能体购买两份传感器读数，报告撰写者购买一份翻译，规划者购买三份报价。SUB/1 是枢纽让这样一条链保持诚实的方式：每次购买都加入同一棵**作业树**；根买家可以预留一笔**分包额度**，按成本向分包方付款；枢纽自己执行这笔分包额度以及树的规模限制；根买家拿回一份精确到分的 **bill of materials（物料清单）**，每个子调用的工作凭证都被承诺进根调用的工作凭证之中。

规范文本是 [`aimarket-protocol/mandates.md` §6](https://github.com/alexar76/aimarket-protocol/blob/main/mandates.md#6-subcontracting-sub1)。[`mandates.zh.md`](mandates.zh.md) 介绍授权书（谁可以花多少钱）；本页是分包的完整指南：流程、每一步资金在哪里、枢纽拒绝什么以及为什么，以及如何在其上构建买家或提供方。

**状态。** 已在网络中的每个枢纽上线（hub 3.7.0）。已在 `modelmarket.dev` 上得到验证：2026-09-26 根调用走 REST，2026-09-28 根调用走 A2A 1.0——见[如何测试](#如何测试)。

## 目录

- [本文用语](#本文用语)
- [向分包方付款的两种方式](#向分包方付款的两种方式)
- [一个作业的完整流程](#一个作业的完整流程)
- [资金如何流动](#资金如何流动)
- [枢纽对作业内购买的检查](#枢纽对作业内购买的检查)
- [作业令牌](#作业令牌)
- [其他枢纽上的子调用](#其他枢纽上的子调用)
- [跨公司雇佣](#跨公司雇佣)
- [通过 A2A 分包](#通过-a2a-分包)
- [bill of materials 与收据](#bill-of-materials-与收据)
- [代码：买家与提供方](#代码买家与提供方)
- [错误](#错误)
- [运营者](#运营者)
- [如何测试](#如何测试)
- [容易忽略的规则](#容易忽略的规则)

## 本文用语

| 用语 | 含义 |
|---|---|
| **根买家** | 发起开启作业那次调用的一方。支付根调用的费用，在成本加成（cost-plus）模式下还要支付每个分包方的费用。 |
| **提供方** | 枢纽为一次调用而执行的智能体。它进行分包时，自己也成为买家。 |
| **分包方** | 在作业内部被购买的提供方。它在市场上没有任何特别之处：就是一个普通的上架条目。 |
| **作业** | 一次根调用所启动的调用树。以 `job_…` 命名。 |
| **节点** | 树中的一次调用，以 `node_…` 命名。根的深度为 0，它的购买深度为 1，依此类推。 |
| **作业令牌** | `X-AIMarket-Job`：由枢纽签名、交给它所执行的每个提供方的短期令牌。购买时把它出示回枢纽，就会把这次购买挂到树上。**它不携带任何资金。** |
| **分包额度** | 根买家为分包方预留的资金（`subcontract.allowance_usd`）。随根调用一起从买家的额度账户中预留。 |
| **grant**（从分包额度中支出的凭证） | `X-AIMarket-Job-Grant`：一个随机的 256 位秘密值，让提供方能够动用分包额度。它有意被设计成持有者凭证（bearer secret）——作用范围限于一个作业，根调用返回的那一刻即失效。 |
| **bill of materials** | 根应答中的 `subcontracting` 块：每个节点、它的花费、谁付的款、分包额度如何结算。 |
| **额度轨道** | 枢纽的预付额度账户——枢纽唯一自行计量资金的轨道，因此也是分包额度唯一能依托的轨道。 |

这些术语的译法遵循[本地化术语表](https://github.com/alexar76/aicom/blob/main/docs/localization-glossary.md#mandate-and-subcontracting-terms-amd1--sub1)。

## 向分包方付款的两种方式

| | **固定价格** | **成本加成** |
|---|---|---|
| 根买家发送 | 普通调用 | 调用，外加 `"subcontract": {"allowance_usd": …, "max_depth": …}` |
| 枢纽向提供方发送 | `X-AIMarket-Job` + `X-AIMarket-Hub` | 同上，再加 `X-AIMarket-Job-Grant` |
| 提供方向分包方付款所用 | 它**自己的**轨道（它自己的 `X-API-Key`、授权书、通道……） | **grant**——且不得随附其他任何东西 |
| 谁承担分包方的费用 | 提供方；它对买家的价格必须覆盖这笔费用 | 根买家，按成本，从分包额度中支付 |
| 根买家支付什么 | 根价格 | 根价格 + 分包方的实际费用（≤ 分包额度） |
| 在树中 | 每一跳都是 `funded_by: "own"` | 每一跳都是 `funded_by: "allowance"`（提供方选择自己付款的那一跳则为 `own`） |
| 最大深度 | 枢纽的上限 3——每一跳自己付款，深度只限制树的规模 | 买家的 `max_depth`（1–3，默认 1） |

grant 只通过 TLS 发送，或发往运营方自己的主机（loopback、`AIMARKET_INVOKE_HOST_GATEWAY`）：公网明文 `http` 地址上的提供方只收到作业令牌，自行支付其分包方。

两种模式可以共存于一棵树中：持有 grant 的提供方仍可用自己的密钥支付某一次特定的购买，该节点显示 `funded_by: "own"`。

## 一个作业的完整流程

示例是枢纽运营者自己的组合服务 `weather.witness@v1`：针对一个城市，它从 GAIA 购买当前天气和当前空气质量，并报告这两份读数描述的是否是同一地点、同一时刻。这正是 2026-09-28 实时运行的流程。

```mermaid
sequenceDiagram
    participant B as 根买家
    participant H as 枢纽（modelmarket.dev）
    participant W as 提供方 weather.witness
    participant G as GAIA（对等枢纽）

    B->>H: POST /ai-market/v2/invoke<br/>weather.witness@v1 + subcontract.allowance_usd 0.01<br/>X-API-Key
    Note over H: 预留分包额度 0.01 和价格 0.002<br/>开启 job_…、根节点、grant
    H->>W: 调用信封<br/>X-AIMarket-Job（根令牌）+ X-AIMarket-Hub + X-AIMarket-Job-Grant
    Note over W: 花任何钱之前先验证令牌
    par 并行的两次购买
        W->>H: POST /ai-market/v2/invoke gaia.weather.read@v1<br/>X-AIMarket-Job + X-AIMarket-Job-Grant，别无其他
        Note over H: 加入作业（深度 1）<br/>从分包额度中扣出 0.001
        H->>G: 路由调用（不带令牌，不带 grant）
        G-->>H: 已签名的读数
        Note over H: 扣费 0.001，完成节点
        H-->>W: 读数 + job 块
    and
        W->>H: POST /ai-market/v2/invoke gaia.air.read@v1<br/>X-AIMarket-Job + X-AIMarket-Job-Grant
        H->>G: 路由调用
        G-->>H: 已签名的读数
        H-->>W: 读数 + job 块
    end
    W-->>H: 见证结果，用提供方的密钥签名
    Note over H: 对根价格 0.002 扣费<br/>关闭 grant，释放剩余的 0.008<br/>写入账单，根收据列出两份子调用收据
    H-->>B: 结果 + subcontracting（bill of materials）+ 收据
```

逐步说明发生了什么，以及它在代码中的位置：

1. **根调用请求分包额度。** `invoke_funding.prepare()` 检查该请求能否携带分包额度：在额度轨道上付款（`X-API-Key` 或授权书）、在本枢纽上执行（`source_hub` 为 `local`）、不超过 `AIMARKET_SUBCONTRACT_MAX_ALLOWANCE_USD`。
2. **枢纽先预留分包额度，再预留根的价格**，两者都是买家账户上的额度预留，然后开启作业：一个作业 id、一个根节点和一个 grant，枢纽存储的是 grant 的哈希（`job_grants`）。若使用授权书，这两笔金额还会在授权书链上预留。
3. **枢纽执行提供方**，附上作业令牌、枢纽的基础 URL 和 grant。
4. **提供方验证令牌**——签名、签发方、过期时间、令牌是为*它的* capability 和产品签发的、它以前没有服务过这个节点——然后才读取输入。
5. **每次购买都回到同一个枢纽**的 `POST /ai-market/v2/invoke`，原样携带令牌和 grant，不带任何其他付款。
6. **枢纽把这次购买加入树中**（`JobStore.join`）：检查深度、循环、节点数和扇出限制，以及 grant 属于令牌所在的作业且仍然开放。然后从分包额度中扣出子调用的价格（`CreditsLedger.transfer_hold`）。
7. **子调用运行**——这里它被路由到对等枢纽 GAIA。令牌和 grant 留在本枢纽；对等方两者都看不到。
8. **子调用交付后，其预留被扣费**，其节点以 `captured` 完成，并带上其工作凭证的 id 和摘要。
9. **子调用的应答回到提供方**，附带一个 `job` 块（`job_id`、`node`、`parent`、`depth`、`funded_by`）。其中的每个余额数字都是分包额度的剩余部分，而不是买家的余额。
10. **提供方应答枢纽**，用它自己的密钥签名。
11. **根调用结束。** 调用处理程序对根的价格扣费；然后 `invoke_funding.finish()` 关闭 grant，把分包额度的剩余部分释放回买家的余额，记录结算结果并完成根节点，而根收据承诺了子调用的收据。
12. **根买家在结果旁边拿到 bill of materials。**

## 资金如何流动

### 资金放在哪里

所有资金都在买家的额度账户上。预留、扣出、扣费和释放只是让资金在“可用”和“已预留”之间移动，并在扣费时最终离开账户。每次移动都是一条带条件的 SQL 语句，因此无论并发多高，都无法取走超过预留的金额。

```mermaid
flowchart TB
    BAL["买家的可用余额"]
    ROOT["预留：根价格<br/>0.002"]
    ALW["预留：分包额度<br/>alw_… 0.010"]
    C1["子调用预留<br/>gaia.weather.read 0.001"]
    C2["子调用预留<br/>gaia.air.read 0.001"]
    SPENT["已扣费：已花费<br/>枢纽收入、提供方分成"]

    BAL -- "1. 预留" --> ALW
    BAL -- "2. 预留" --> ROOT
    ALW -- "3. transfer_hold（扣出）" --> C1
    ALW -- "3. transfer_hold（扣出）" --> C2
    C1 -- "4. 交付时扣费" --> SPENT
    C2 -- "4. 交付时扣费" --> SPENT
    C1 -. "子调用失败：释放，<br/>回到开放的分包额度" .-> ALW
    C2 -. "子调用失败：释放" .-> ALW
    ROOT -- "5. 交付时扣费" --> SPENT
    ROOT -. "根调用失败：释放" .-> BAL
    ALW -- "6. 根返回：释放剩余部分" --> BAL
```

### 账本实例：2026-09-28 的实时运行

调用前买家账户的余额记为 `B`。价格为线上实际价格：见证服务 $0.002，每份 GAIA 读数 $0.001；在 `modelmarket.dev` 上，本枢纽是 GAIA 的登记卖家，因此不加路由费。

| 步骤 | 可用 | 分包额度预留 | 子调用预留 | 根预留 | 累计已扣费 |
|---|---|---|---|---|---|
| 调用前 | `B` | — | — | — | 0 |
| 已预留分包额度 | `B − 0.010` | 0.010 | — | — | 0 |
| 已预留根价格 | `B − 0.012` | 0.010 | — | 0.002 | 0 |
| 已扣出天气读数 | `B − 0.012` | 0.009 | 0.001 | 0.002 | 0 |
| 已扣出空气读数 | `B − 0.012` | 0.008 | 0.001 + 0.001 | 0.002 | 0 |
| 两份读数均已交付 | `B − 0.012` | 0.008 | — | 0.002 | 0.002 |
| 见证结果已交付 | `B − 0.012` | 0.008 | — | — | 0.004 |
| 根返回：grant 关闭，剩余部分释放 | **`B − 0.004`** | — | — | — | **0.004** |

扣出不会改变账户的总额：预留分包额度时，这笔钱就已离开“可用”，而一次扣出只是把一笔预留的一部分变成一笔单独的预留。返回的账单：

```json
"subcontracting": {
  "job_id": "job_5346033bb2ce717936278f7c",
  "nodes": [
    { "capability_id": "gaia.weather.read@v1", "depth": 1, "price_usd": 0.001,
      "funded_by": "allowance", "status": "captured", "receipt_digest": "sha256-InbmOY0P…" },
    { "capability_id": "gaia.air.read@v1", "depth": 1, "price_usd": 0.001,
      "funded_by": "allowance", "status": "captured", "receipt_digest": "sha256-bpIDxEev…" }
  ],
  "spent_from_allowance_usd": 0.002,
  "allowance_usd": 0.01,
  "spent_usd": 0.002,
  "released_usd": 0.008
}
```

`spent_usd + released_usd == allowance_usd`（0.002 + 0.008 = 0.01），且节点价格之和等于 `spent_usd`。这两个等式在每份账单上都成立；金丝雀（canary）在每次运行时都会断言它们。

### 分包额度预留的生命周期

```mermaid
stateDiagram-v2
    state "开放" as Open
    state "已关闭" as Closed
    state "已结算" as Settled
    state "已清扫" as Swept
    [*] --> Open: 根调用预留分包额度<br/>签发 grant，开启 60 秒后过期
    Open --> Open: 子调用从中扣出其价格<br/>失败子调用的钱回到这里
    Open --> Closed: 根调用返回<br/>（无论是否交付）
    Closed --> Settled: 剩余部分释放到余额<br/>记录已花费和已释放的金额
    Open --> Swept: 根调用从未结算它<br/>grant 已过期超过 5 分钟
    Swept --> Settled: 清扫负责关闭、释放、记录
    Settled --> [*]
```

- 已关闭的 grant 不能再支取：在根返回之后到达的购买得到 `402 allowance_exhausted`，而且已结束的调用的令牌本来就会被拒绝（`403 job_invalid`）。
- 如果根调用结束时的释放失败（暂时性的数据库错误），账单中的 `spent_usd` 和 `released_usd` 保持为 `null`——**表示尚未结算，这与什么都没花不是一回事**——[清扫](#滞留的分包额度)会在几分钟内完成结算。

### 子调用预留的生命周期

```mermaid
stateDiagram-v2
    state "已预留" as Held
    state "已扣费" as Captured
    state "退回分包额度" as BackToAllowance
    state "退回余额" as BackToBalance
    [*] --> Held: transfer_hold 从分包额度中扣出价格
    Held --> Captured: 子调用已交付
    Held --> BackToAllowance: 子调用失败，分包额度仍开放
    Held --> BackToBalance: 子调用在根关闭之后失败
    Held --> Orphaned: 进程在调用中途终止
    Orphaned --> BackToAllowance: 一小时后由清理任务释放
    Orphaned --> BackToBalance: 同上，若额度已经结算
    BackToAllowance --> [*]: 可用来支付一次重试
    BackToBalance --> [*]: 退款给买家<br/>并退回根授权书的计数器
    Captured --> [*]
```

在根仍在运行时失败的子调用，会把它的钱**退回分包额度**，而不是买家的余额，因此提供方可以在同一预算内重试——或改向别人购买。

### 谁得到付款，以什么形式

分包转移的是**枢纽额度**，从不是链上资金：分包额度只存在于额度轨道上。一次扣费意味着什么，取决于调用在哪里运行：

| 调用运行在 | 扣费时 |
|---|---|
| 本枢纽的某个提供方上 | 价格从买家的账户中花掉；如果上架条目的发布者在这里持有额度账户，它会获得价格的 `AIMARKET_PUBLISHER_SHARE_BPS`（默认 7000 = 70 %）入账。以 USDC 收款的发布者通过市场轨道收款，而分包不使用该轨道。 |
| 本枢纽代售的对等方上（`AIMARKET_SELLS_FOR`） | 本枢纽是登记卖家：它按完整标价扣费，不加路由费。`modelmarket.dev` 上的 GAIA 就是这样出售的。 |
| 本枢纽转售的对等方上（本枢纽在那里持有额度密钥，`AIMARKET_PEER_API_KEYS`） | 枢纽用自己在那里的账户向对等方付款，并扣取价格**加路由费**（`AIMARKET_ROUTING_FEE_BPS`，默认 100 = 1 %）。两者都从分包额度中扣出。 |

自行向买家收费、且本枢纽既不代售也不转售的对等方，根本无法在额度轨道上获得付款，因此也不能成为由 grant 出资的子调用。

### 谁承担哪种风险

| 发生了什么 | 谁付款 | 账单显示什么 |
|---|---|---|
| 分包方失败 | 没有人；它的预留回到分包额度 | 该节点为 `failed`，`price_usd` 为 0 |
| 分包方已交付，随后雇用它的提供方失败 | 根买家向分包方付款（**已消耗的物料要付钱**），而不向提供方付款 | 已交付的节点为 `captured`，外加根调用的错误和 `job_id`——即使根调用失败，其应答也携带账单 |
| 提供方在调用结束后仍持有令牌 | 没有人：购买被拒绝 | 什么也没有——不会创建节点 |
| 提供方泄露了 grant | 最多是该分包额度的剩余部分，直到根调用返回为止（最长 60 秒） | 窃贼买到的任何东西，作为该作业的节点 |
| 根调用在中途崩溃 | 根买家，为已扣费的子调用付款；分包额度的剩余部分通过清扫退回 | 清扫结算后，`spent_usd` / `released_usd` 会被填上 |
| 固定价格，分包方已交付，提供方失败 | 提供方，用它自己的轨道 | 该节点，`funded_by: "own"` |

因此，根买家的风险敞口以它所选择的分包额度为上限，而账单会准确显示是哪个提供方失败了。

### 叠加授权书

由授权书支付的根调用（[mandates.zh.md](mandates.zh.md)）只有在叶授权书允许时才能携带分包额度：

```json
"subcontract": { "perCallAllowance": 5000, "maxDepth": 2 }
```

（单位为 µUSD：5000 = $0.005。）此时：

- 分包额度必须 ≤ `perCallAllowance`（否则为 `402 mandate_limit`，`limit: "subcontract.perCallAllowance"`），且 `max_depth` ≤ `maxDepth`（否则为 `403 mandate_invalid`）；没有 `subcontract` 块的叶授权书拒绝任何分包额度（`403 mandate_invalid`）；
- 分包额度在链中的每一份授权书上预留，并计入 `perDay`、`total` 和 `perProductPerDay`——但**不**计入 `perCall`，后者涵盖的是根自己的价格；
- 每个由 grant 出资的子调用仍必须落在根授权书的范围之内（`403 mandate_scope`），但它**不会**在授权书上再预留一次：它的费用已包含在分包额度的预留之中；
- 根返回时，授权书为分包额度所做的预留按子调用实际支取的金额结算；此后被退款的子调用会退回授权书的计数器，因此限额永远不会多计。

## 枢纽对作业内购买的检查

```mermaid
flowchart TD
    P["购买到达 /ai-market/v2/invoke<br/>带 X-AIMarket-Job"] --> G1{"grant 与其他付款<br/>一同发送？"}
    G1 -- 是 --> R1["403 job_invalid"]
    G1 -- 否 --> G2{"要求自己的<br/>分包额度？"}
    G2 -- 是 --> R2["400 subcontract_unsupported"]
    G2 -- 否 --> T{"令牌由本枢纽签名、<br/>签发给本枢纽、未过期？"}
    T -- 否 --> R3["403 job_invalid"]
    T -- 是 --> D{"depth + 1 ≤ maxDepth<br/>且 capability 不在路径上？"}
    D -- 否 --> R4["403 job_limit<br/>depth 或 cycle"]
    D -- 是 --> GR{"发送了 grant？"}
    GR -- 是 --> GO{"grant 属于本作业，<br/>且仍开放？"}
    GO -- 否 --> R5["402 allowance_exhausted<br/>或 403 job_invalid"]
    GO -- 是 --> PR
    GR -- 否 --> PR{"父调用<br/>仍在运行？"}
    PR -- 否 --> R6["403 job_invalid"]
    PR -- 是 --> N{"作业少于 64 个调用，<br/>父调用少于 16 个子调用？"}
    N -- 否 --> R7["403 job_limit<br/>nodes 或 children"]
    N -- 是 --> F{"由 grant 出资？"}
    F -- 否 --> OWN["子调用运行，由提供方<br/>自己的付款支付"]
    F -- 是 --> S{"根由授权书支付，且<br/>子调用超出其范围？"}
    S -- 是 --> R8["403 mandate_scope<br/>节点记录为 refused"]
    S -- 否 --> C{"分包额度足以<br/>支付价格？"}
    C -- 否 --> R9["402 allowance_exhausted<br/>节点记录为 failed"]
    C -- 是 --> OK["价格从分包额度中<br/>扣出，子调用运行"]
```

无论买家要求什么，枢纽都执行以下限制：

| 限制 | 取值 | 如何保证 |
|---|---|---|
| 深度 | ≤ 3（枢纽代码中的常量，而不是配置项）；有分包额度时为买家的 `max_depth` | 对照已签名的声明（claims）检查 |
| 每个作业的调用数 | ≤ 64，含根 | 由一条带条件的 `UPDATE` 推进的计数器，因此并发加入无法越过它 |
| 每个调用的子调用数 | ≤ 16 | 同上 |
| 循环 | 不允许——已在路径上的 capability 会被拒绝 | 对照令牌的 `path` 检查 |
| 令牌有效期 | 60 秒（提供方 30 秒超时再加 30 秒） | 已签名声明中的 `exp` |
| grant 有效期 | 直到根调用返回，且最长为开启分包额度后 60 秒 | 根返回时由一条带条件的 `UPDATE` 关闭；否则由 `expires_at` 限定 |
| 每次根调用的分包额度 | `AIMARKET_SUBCONTRACT_MAX_ALLOWANCE_USD`，默认 $1.00 | 在预留任何东西之前检查 |

在加入树**之后**、运行之前被拒绝的子调用——超出根授权书的范围，或根授权书在此期间被撤销——会交还它占用的两个名额（作业 64 个调用中的一个、其父调用 16 个子调用中的一个），并在树中显示为 `refused`。分包额度无法覆盖的子调用会在扣出其价格时以 `402 allowance_exhausted` 被拒绝：它显示为 `failed`，`price_usd` 为 0，并保留它占用的名额。

## 作业令牌

```
X-AIMarket-Job: base64url(JCS(claims)) "." base64url(Ed25519 signature)
```

签名由枢纽的签名密钥——即其 `/.well-known/ai-market.json` 中的 `signer_public_key`——对字节串 `aimarket-job-token/1` + LF + `JCS(claims)` 做出。这个前缀保证作业令牌永远不会被验证为同一密钥所签的其他任何东西（清单、证明（attestation））。声明（claims）如下：

```json
{
  "v": 1,
  "iss": "https://modelmarket.dev",
  "job": "job_5346033bb2ce717936278f7c",
  "node": "node_…",
  "depth": 0,
  "maxDepth": 1,
  "exp": 1790000060,
  "path": ["weather.witness@v1"],
  "product": "weather-witness"
}
```

`node` 是令牌为之签发的那次调用；用它买到的任何东西都成为该节点的子节点。当枢纽在本地执行子调用时，子调用的提供方会得到它自己的令牌（`depth + 1`，子调用的 capability 追加到 `path` 末尾）——如果子调用由分包额度出资，还会得到同一个 grant——因此树可以继续向下生长，直到作业允许的深度。

**你的调用 URL 是公开的，所以在花任何钱之前先验证令牌。** 枢纽会给它执行的*每一个*提供方一个令牌；没有这些检查，另一个提供方就可以把它自己的令牌重放到你的 URL 上，让你在一个从未请求过你的作业中花钱。以下摘自见证服务：

```python
self._hub_key.get().verify(signature, TOKEN_DOMAIN + payload)   # the hub's signer_public_key
if claims.get("iss") != self._cfg.hub_url:                        # the hub you serve
    raise Refusal(403, "job_invalid", "the job token was issued by another hub")
if claims.get("exp") < self._now():                               # not expired
    raise Refusal(403, "job_invalid", "the job token has expired")
if claims["path"][-1] != CAPABILITY_ID:                           # issued for YOUR capability
    raise Refusal(403, "job_invalid", "the job token was issued for another capability")
if claims.get("product") != PRODUCT_ID:                           # and YOUR product
    raise Refusal(403, "job_invalid", "the job token was issued for another product")
if node in self._seen:                                            # each node served once
    raise Refusal(403, "job_replayed", "this job node has already been served")
```

`product` 之所以重要，是因为只有 `(capability_id, product_id, source_hub)` 这个组合是唯一的：另一个发布者可以用你的 capability id 上架它自己的产品，并拿到一个 path 以该 capability 结尾的令牌。从 well-known 读取一次密钥（或将其固定），并在枢纽密钥轮换后重启。

## 其他枢纽上的子调用

只有根必须在本枢纽上运行。子调用可以是本枢纽能路由的任何 capability，并且与本地子调用一样从分包额度中支付。

```mermaid
sequenceDiagram
    participant W as 提供方
    participant H as 本枢纽
    participant P as 对等枢纽

    W->>H: 调用 gaia.weather.read@v1<br/>source_hub https://iot.modelmarket.dev<br/>X-AIMarket-Job + X-AIMarket-Job-Grant
    Note over H: 加入作业，从分包额度中扣出价格<br/>（转售时再加路由费）
    H->>P: 路由调用——不带作业令牌，不带 grant
    P-->>H: 已签名的应答和收据
    Note over H: 扣费，完成节点
    H-->>W: 应答 + job 块
```

- **指明对等方。** 发送 `source_hub: <the peer URL /search returns>`（即 `/search` 返回的对等方 URL）。没有它，枢纽会寻找本地 capability，只找到对等方的上架条目并回答 `400`——而这次尝试仍会占用该调用 16 个子调用名额中的一个，并在账单中显示为失败的节点。
- **令牌和 grant 永远不会离开本枢纽。** 关联和资金都留在枢纽能计量的地方；对等方看到的是来自本枢纽的一次普通调用。
- **转售的子调用花费其价格加路由费**，两者都从分包额度中扣出；其节点的 `price_usd` 是两者之和，因此账单仍然对得上。
- **路由子调用上的 `max_price_usd` 以整美分比较。** 枢纽对路由的 capability 报价为其价格加路由费并向上取整到美分，因此低于 $0.01 的上限会以 `409 price_limit_exceeded` 拒绝一个 $0.001 的子调用。
- 被路由到对等方的**根调用**不能携带分包额度（`400 subcontract_unsupported`）：枢纽只能转付它自己计量的资金。

## 跨公司雇佣

子调用可以是另一家公司在其自己枢纽上的工作，也可以是某人托管在 HESTIA 上的智能体。任务、分包额度和账单的运作方式同上；变化的只是两家公司之间如何结算。

### 另一家公司的枢纽

枢纽用自己在对方那里的额度账户（`AIMARKET_PEER_API_KEYS`）向它**转售**的对等方付款。公司之间提前在链上结算：每个枢纽用 USDC 充值自己在对方那里的账户（[credits-topup.zh.md](credits-topup.zh.md)），之后每个子调用都只在两边的账本上移动额度，每次调用不花 gas。

| 何时 | 谁付款 | 付给谁 | 方式 |
|---|---|---|---|
| 提前 | 公司 A | B 枢纽的充值钱包 | 用 USDC 充值 A 在 B 上的账户（一笔 Base 交易） |
| 买方在 A 枢纽上的任务 | 买方的分包额度 | A 枢纽 | B 的价格 + A 的路由费 |
| 同一个子调用 | A 在 B 上的账户 | B 枢纽 | B 的价格，记在 B 的账本上 |

没有人需要出示这些付款或手动入账：每个枢纽的充值钱包都是专用的（`AIMARKET_TOPUP_PAY_TO`）并受到监视，付款公司的钱包只需与其账户关联一次。从该钱包（任何钱包应用）发出的普通 USDC 转账，在确认后约一分钟内变为额度（[无需任何人出示即可入账](credits-topup.zh.md#无需任何人出示即可入账)）。

自 2026-10-04 起已在 **Independent AI**（`independentai.network/hub`）与 **Attested Memory**（`hub.attestedmemory.net`）之间运行：双方各在对方枢纽上持有账户，并把充值收进自己的钱包。示例提供方 `examples/cross-company-check`（`claim.audit@v1`，由 Independent 运营）在买方的任务内购买 Attested 的 `claim.check@v1` 和 `contradiction.scan@v1`：

```json
{"product_id": "independent-claim-audit", "capability_id": "claim.audit@v1",
 "input": {"claim": "The vault holds 3 BTC",
           "evidence": [{"source_uri": "https://…", "excerpt_hash": "sha256:…", "stance": "supports", "quality": 0.8}],
           "statements": ["The vault holds 3 BTC", "The audit found 3 BTC"]},
 "subcontract": {"allowance_usd": 0.05, "max_depth": 1}}
```

分包额度中约 $0.032 用于 Attested 的两项检查（其价格 + 1 %），其余退回。如果 A 在 B 上的账户为空，子调用以 `upstream_unpaid` 失败，根调用返回 `502 child_failed`，买方不会为未交付的工作付任何钱。

### 按次用 USDC 付款，无需账户

预付账户是两家公司结算的一种方式。另一种方式在购买每个子调用的那一刻就在链上付款，完全不需要在另一家公司的枢纽上开设账户。Independent 以 `claim.audit.direct@v1` 出售同样的审计（$0.05，价格覆盖两项检查和 gas）；它的提供方在 Attested 自己的枢纽上购买 Attested 的两项检查，每项都用 EIP-3009 `transferWithAuthorization` 从自己的钱包付款到 Attested 的商品列表声明的收款地址。

| 步骤 | 谁 | 做什么 |
|---|---|---|
| 1 | 提供方 | 在 Attested 的枢纽上调用检查，收到带卖方条款的 `402`：金额、收款方、nonce、秘密值 |
| 2 | 提供方 | 对该 nonce 签署授权并发送到 USDC 合约（gas 由它支付） |
| 3 | 提供方 | 出示付款：同一个调用，附带 `X-Payment: <tx>`、`X-Payment-Nonce` 和 `X-Payment-Secret` |
| 4 | Attested 的枢纽 | 读取收据——针对其 nonce 的授权、给其卖方的转账、确认数——然后提供服务 |

提供方只向事先告知它的地址付款（`AUDIT_CHILD_PAYEES`），每项检查不超过其上限，并且在每日预算之内；指定其他收款方的 402 一分钱也不付。它的应答列出两笔交易。这些购买发生在 Attested 的枢纽上，因此不是买方在这里的任务节点——审计本身才是。该钱包是提供方服务器上的热钱包：只放少量资金，并从公司金库补充。这不是原子操作：钱在工作之前就转出，付款后失败的检查由卖方负责退款；如果只想为已交付的工作付款，请使用带 Pay-on-Verified 的托管通道。示例和设置：[`examples/cross-company-check`](../examples/cross-company-check/README.md)。

### HESTIA 上的智能体

HESTIA 上的智能体每次调用都在链上收取 USDC，枢纽无法从分包额度中这样付款。以下情况可以：hearth 持有该枢纽的密钥（`HESTIA_TENANT_HUB_KEYS`，与枢纽 `AIMARKET_PEER_API_KEYS` 中的条目同值），并且智能体属于 hearth 运营方，或其**所有者选择了该枢纽**并在那里指定了一个额度账户（`POST /v1/owners/me/billing` 或 `python -m hestia.owner_cli billing`）。此时：

1. 枢纽用自己的密钥调用智能体，并告知它向买方收取了多少（`X-AIMarket-Hub-Charged`）；
2. hearth 返回工作结果和一个由其提供方密钥签名的 `hub_billing` 块：智能体属于谁、哪个枢纽、哪个账户；
3. 枢纽用它为该 hearth **固定**的密钥验证这个块，检查它写的是本枢纽和本能力，按**本枢纽实际收取**的金额（绝不按 hearth 的数字）向所有者记入 `AIMARKET_PUBLISHER_SHARE_BPS`（默认 70 %），并在买方看到结果之前删除这个块；
4. 所有者在 `GET /v1/owners/me/statement` 中看到每一次这样的调用，用来与枢纽实际支付的金额核对。

免费试用（`X-AIMarket-Hub-Charged: 0`）不会为所有者的智能体提供服务：否则所有者等于白干。首笔交易，2026-10-04：Attested 的 `attested.contradiction.scan@v1` 经 modelmarket.dev 以 $0.009 售出；Attested 在那里的账户入账 $0.0063。

## 通过 A2A 分包

使用 [A2A 1.0](a2a.md) 的根买家开启的是同样的作业：`subcontract` 块放进 `SendMessage` 的调用部分（invoke part），桥接层通过枢纽自身的应用把确切的字节转发给 `/ai-market/v2/invoke`——相同的准入、预留和限制。

```mermaid
sequenceDiagram
    participant B as A2A 客户端（根买家）
    participant A as POST /a2a（桥接层）
    participant I as /ai-market/v2/invoke
    participant W as 提供方
    participant S as 分包方

    B->>A: SendMessage，data.invoke 部分带 subcontract<br/>X-API-Key，A2A-Version 1.0
    A->>I: 相同的调用字节（进程内）
    I->>W: X-AIMarket-Job + X-AIMarket-Job-Grant
    W->>I: 带令牌 + grant 的购买（REST，不是 A2A）
    I->>S: 子调用
    S-->>I: 已交付
    I-->>W: 应答 + job 块
    W-->>I: 结果
    I-->>A: 结果 + subcontracting + 收据
    A-->>B: 任务 COMPLETED<br/>metadata.aimarket.subcontracting = 账单
    B->>A: GetTask（稍后）
    A-->>B: 同一个任务，同一份账单
```

```json
{"jsonrpc": "2.0", "id": 1, "method": "SendMessage", "params": {"message": {
  "messageId": "m-1", "role": "ROLE_USER",
  "parts": [{"mediaType": "application/json", "data": {"invoke": {
    "product_id": "weather-witness", "capability_id": "weather.witness@v1",
    "input": {"city": "Berlin"},
    "subcontract": {"allowance_usd": 0.01, "max_depth": 1}}}}]}}}
```

- 应答是一个 A2A 任务（`Task`）。完成时，它携带结果工件（artifact）、网关收据、AWR/2 工作凭证，以及位于 `metadata.aimarket.subcontracting` 中的账单。`GetTask` 稍后可读回同一个任务。
- **失败的根调用仍在 `metadata.aimarket.subcontracting` 中携带账单**（一个 `FAILED` 或 `REJECTED` 任务），原因与 REST 应答相同：它已交付的分包方得到了付款，而账单正是解释这笔扣款的东西。（2026-09-28 修复；运行旧镜像的枢纽在失败的任务上只保留错误——扣款相同，而没有作业 id 就无法访问 `GET /ai-market/v2/jobs/{job_id}`。）
- **作业内的购买在 `/ai-market/v2/invoke` 进行，绝不在 `/a2a`。** 桥接层会以 JSON-RPC `-32602` 拒绝 `X-AIMarket-Job` / `X-AIMarket-Job-Grant`，而不是丢弃它们——被丢弃的作业头会悄无声息地把一次由分包额度出资的购买变成陌生人的购买。
- 授权书也可以通过 A2A 付款；它的证明对原始调用字节签名（见 [mandates.zh.md](mandates.zh.md#智能体用授权书付款)）。

使用 Python SDK：

```python
from aimarket_agent.a2a import A2AClient, task_result, task_state

a2a = A2AClient("https://modelmarket.dev", api_key=API_KEY)
task = a2a.invoke("weather-witness", "weather.witness@v1", {"city": "Berlin"},
                  subcontract={"allowance_usd": 0.01, "max_depth": 1})
task_state(task)                                   # "TASK_STATE_COMPLETED"
task["metadata"]["aimarket"]["subcontracting"]     # the bill of materials
task_result(task)["funding"]                       # "cost-plus"
```

## bill of materials 与收据

### 在根调用的应答中

枢纽通过提供方端点执行的每个调用都会获得一个作业 id，因此即使没有任何分包，其应答中也有 `subcontracting` 块（`"nodes": []`）。

| 字段 | 含义 |
|---|---|
| `job_id` | 作业；稍后可在 `GET /ai-market/v2/jobs/{job_id}` 读取。 |
| `nodes[]` | 分包出去的调用——根本身不在其中。每一项都有 `node`、`parent`、`depth`、`product_id`、`capability_id`、`price_usd`、`funded_by`（`allowance` \| `own`）、`status`（`running` \| `captured` \| `failed` \| `refused`）、`receipt_id`、`receipt_digest`。 |
| `nodes[].price_usd` | 对于由分包额度出资的节点：该调用实际从分包额度中取走的金额，含路由费。预留已被释放的失败节点显示 0；仍然花了钱的失败节点（对等方已交付，随后路由费的扣费失败）显示实际取走的金额。 |
| `spent_from_allowance_usd` | 由分包额度出资的节点的价格总和。 |
| `allowance_usd`、`spent_usd`、`released_usd` | 仅在有分包额度时出现。账本结算的结果；结算未完成时为 `null`。 |

### 在子调用的应答中

```json
"job": { "job_id": "job_…", "node": "node_…", "parent": "node_…", "depth": 1, "funded_by": "allowance" }
```

### 之后

`GET /ai-market/v2/jobs/{job_id}` 返回整棵树：相同的节点加上根自己的节点（`depth` 0）、`spent_from_allowance_usd`；有分包额度时还有 `allowance_usd`、`max_depth`、`allowance_status`（`open` \| `closed`），以及记录后的 `spent_usd` / `released_usd`。未知 id：`404 job_unknown`。**作业 id 是一个无法猜测的能力凭据（capability）**：持有它的人都能读取这棵树，而枢纽只把它交给根买家和该作业的提供方。

### 收据承诺整棵树

```mermaid
flowchart LR
    R["根工作凭证<br/>weather.witness@v1"]
    C1["子调用工作凭证<br/>gaia.weather.read@v1"]
    C2["子调用工作凭证<br/>gaia.air.read@v1"]
    H["HISTOR 收据日志<br/>（公开，只追加）"]
    R -- "credentialSubject.parents[0]<br/>id + digestSRI" --> C1
    R -- "credentialSubject.parents[1]<br/>id + digestSRI" --> C2
    R -. "摘要已锚定" .-> H
    C1 -. "摘要已锚定" .-> H
    C2 -. "摘要已锚定" .-> H
```

根的 AWR/2 工作凭证在 `credentialSubject.parents` 中列出每个**已交付**子调用的工作凭证：`id` 是子调用的 `receipt_id`，`digestSRI` 是它的 `receipt_digest`。每个子调用的凭证对它自己的子调用也做同样的事，所以这棵树是逐跳承诺的，而不只是报告出来的——持有凭证包的验证方可以解析每一条边（[awr-receipts.md](https://github.com/alexar76/aicom/blob/main/docs/awr-receipts.md)）。开启 HISTOR 锚定后，每张凭证的摘要也会进入公开的收据日志：2026-09-28 那次运行的三张凭证是叶 546、547 和 548，可在 `GET /ai-market/v2/p/provenance/anchor/{receipt_id}` 读取。

## 代码：买家与提供方

### 根买家

> 在本枢纽上没有账户的智能体，先开设账户并用 USDC 购买额度——见 [credits-topup.zh.md](credits-topup.zh.md)。分包额度从这些额度中预留。

```python
from aimarket_agent import AIMarketAgent

client = AIMarketAgent("https://modelmarket.dev", api_key=API_KEY)
r = client.invoke_single("weather-witness", "weather.witness@v1", {"city": "Berlin"},
                         subcontract={"allowance_usd": 0.01, "max_depth": 1})
bill = r["subcontracting"]
assert abs(bill["spent_usd"] + bill["released_usd"] - bill["allowance_usd"]) < 1e-9
```

把分包额度设为你愿意为分包支付的最高金额：没花掉的部分会在根返回的那一刻释放。`max_depth` 为 1 时，提供方可以购买，但它的分包方不能；只有当你确实打算为更深的树付款时才调高它。

### 提供方

```python
from aimarket_agent import AIMarketAgent, JobContext

def handle(request):
    job = JobContext.from_headers(request.headers)        # None when the hub sent no token
    # ... verify the token first (see "The job token") ...
    buyer = AIMarketAgent(job.hub or HUB, api_key=MY_OWN_KEY)
    r = buyer.invoke_single("gaia.gateway", "gaia.weather.read@v1", {"city": "Berlin"},
                            source_hub="https://iot.modelmarket.dev", job=job)
    r["job"]    # {"job_id", "node", "parent", "depth", "funded_by"}
```

作业带有 grant 时，SDK 发送令牌和 grant，并**不附加它自己的付款**——枢纽会拒绝两者同时出现。要在成本加成作业中自己支付某一次购买（固定价格），就传入不带 grant 的作业 `JobContext(token=job.token, hub=job.hub)`：SDK 随后只发送令牌和你自己的付款，该节点显示 `funded_by: "own"`。`job.headers(use_allowance=False)` 为你自己的客户端提供这些只含令牌的请求头。

### 其他客户端

- TypeScript、Rust 和 Dart SDK 还没有作业上下文辅助工具：请自己原样发送这两个头；存在 grant 时不带任何其他付款。
- ARGUS 可以签发带 `subcontract` 块的授权书（`aimarket-mandate.ts`，`subcontractAllowanceUsd` / `subcontractMaxDepth`）。它的 `subcontract_invoke` 工具是另一回事：ARGUS 作为普通买家，用自己的 USDC 钱包购买一个子任务，不带作业令牌。
- `scripts/subcontract_canary.py` 是一个没有依赖的完整根买家（REST 或 A2A）。

## 错误

| 状态码 | `error` | 何时 | 怎么做 |
|---|---|---|---|
| 400 | `subcontract_unsupported` | 分包额度出现在以通道、x402 或沙箱访客 id 付款的调用上，或出现在不带 `X-API-Key`/授权书的调用上；出现在被路由到对等方的根调用上；超出枢纽的上限；或由作业内的调用请求。 | 在额度轨道上支付根调用，在本地运行它，不超过 `max_allowance_usd`；只有根可以设定分包额度。 |
| 402 | `allowance_exhausted` | grant 已关闭（根已返回）或已过期，或剩余部分不足以支付子调用的价格。应答体会给出 `allowance_left_usd`。 | 买便宜些、买少些，或请根买家提供更大的分包额度。 |
| 402 | `mandate_limit` | `limit: "subcontract.perCallAllowance"`——分包额度超出叶授权书所允许的范围。 | 降低分包额度，或请所有者签发一份更宽的授权书。 |
| 403 | `job_invalid` | 不是作业令牌；不是本枢纽签名的；是为另一个枢纽签发的；已过期；它所签发给的调用已经结束；grant 没有随附其令牌、属于另一个作业，或与其他付款一同发送。 | 在调用运行期间，原样发送令牌和 grant，不带任何其他东西。 |
| 403 | `job_limit` | `limit` 为 `depth`、`cycle`、`nodes` 或 `children`。 | 把树变扁平；不要购买已在路径上的 capability。 |
| 403 | `mandate_invalid` | 叶授权书没有 `subcontract` 块，或 `max_depth` 超出其 `maxDepth`。 | 签发一份带 `subcontract` 块的授权书。 |
| 403 | `mandate_scope` | 由 grant 出资的子调用超出根授权书的范围。 | 保持在所有者所签署的范围之内。 |
| 404 | `job_unknown` | 对本枢纽不认识的 id 请求 `GET /ai-market/v2/jobs/{job_id}`。 | 检查 id；它是按枢纽区分的。 |
| 503 | `mandates_unavailable` | 额度轨道已关闭（`AIMARKET_CREDITS_ENABLED=0`）。 | 作业令牌（关联）仍然可用；分包额度不可用。 |
| JSON-RPC `-32602` | — | `/a2a` 收到了 `X-AIMarket-Job` 或 `X-AIMarket-Job-Grant`。 | 在 `/ai-market/v2/invoke` 进行作业内的购买。 |

## 运营者

### 配置

| 变量 | 默认值 | 作用 |
|---|---|---|
| `AIMARKET_CREDITS_ENABLED` | `0` | 分包额度需要额度轨道；关闭时，带分包额度的请求得到 `503 mandates_unavailable`。作业令牌在两种情况下都可用。 |
| `AIMARKET_HUB_URL` | `http://localhost:9083` | 枢纽的公开基础 URL：令牌的 `iss`，以及 `X-AIMarket-Hub`。提供方把 `iss` 与它所服务的枢纽进行比较。 |
| `AIMARKET_SUBCONTRACT_MAX_ALLOWANCE_USD` | `1.0` | 一次根调用可预留的最大分包额度。 |
| `AIMARKET_SUBCONTRACT_SWEEP_S` | `120` | 清扫滞留的分包额度的频率。`0` 关闭清扫；小于 10 的值会被提高到 10。 |
| `AIMARKET_PUBLISHER_SHARE_BPS` | `7000` | 本地扣费中，计入在这里持有额度账户的发布者的份额。 |
| `AIMARKET_SELLS_FOR` | 未设置 | 本枢纽作为登记卖家的对等方：按完整标价，不加路由费。 |
| `AIMARKET_PEER_API_KEYS` | 未设置 | 本枢纽在对等方处持有的额度密钥，`url=key,…`：这些对等方被转售，收取路由费。 |
| `AIMARKET_ROUTING_FEE_BPS` | `100` | 转售对等方时的路由费。 |

### well-known 中的块

```json
"subcontracting": {
  "spec": "aimarket-protocol/mandates.md#6-subcontracting-sub1", "version": "SUB/1",
  "job_tokens": true, "allowance": true, "max_allowance_usd": 1.0,
  "max_depth": 3, "max_nodes_per_job": 64, "max_children_per_node": 16,
  "jobs": "/ai-market/v2/jobs/{job_id}"
}
```

`allowance` 跟随 `AIMARKET_CREDITS_ENABLED`；`max_allowance_usd` 跟随 `AIMARKET_SUBCONTRACT_MAX_ALLOWANCE_USD`。客户端在发送任何内容之前先读取它。

### 滞留的分包额度

分包额度的存续时间应当与其根调用完全相同。如果根从未结算它——调用中途崩溃、释放一再失败——这笔钱就会一直被冻结。枢纽在启动时清扫一次，之后每隔 `AIMARKET_SUBCONTRACT_SWEEP_S` 秒清扫一次，在后台进行，从不在请求路径上：对于 grant 已过期超过五分钟且预留仍被占用的分包额度，枢纽将其关闭，释放剩余部分，把凭授权书的分包额度在授权书上的预留结算为子调用实际支取的金额，并记录结算结果，从而填上作业的 `spent_usd` / `released_usd`。每次清扫最多处理 50 个；结算了任何分包额度时，会以 WARNING 级别记录 `subcontract: settled N stale allowance(s)`。

### 表

| 表 | 迁移 | 保存什么 |
|---|---|---|
| `job_nodes` | 035, 038 | 树中每个调用一行：父节点、深度、产品、capability、`funded_by`、`amount_micro`（它实际支取的金额）、状态、收据摘要、`work_receipt_id`。 |
| `job_grants` | 035, 038 | 每个分包额度一行：grant 的**哈希**（从不保存秘密值本身）、分包额度预留、账户、授权书、金额、`max_depth`、过期时间、状态，以及结算后的 `spent_micro` / `released_micro` / `settled_at`。 |
| `job_counters` | 035 | 节点计数器和子调用计数器，每个都由一条带条件的 `UPDATE` 推进。 |
| `credit_holds.parent_receipt_id` | 035 | 标记从分包额度中扣出的子调用预留，使它在分包额度仍开放时释放回该分包额度。 |

每个通过提供方端点执行的调用在结束时都会写入一行 `job_nodes`，无论它是否进行了分包。µUSD 列为 `BIGINT`；在 034/035 仍写作 `INTEGER` 时就已应用它们的 PostgreSQL 枢纽，需要执行 [mandates.zh.md](mandates.zh.md#迁移-038) 中描述的 `ALTER`。

### 监控要点

- WARNING 级别的 `subcontract: settled N stale allowance(s)`——未能结算其分包额度的根调用。如果持续不断地出现，说明调用结束时有什么东西在失败。
- ERROR 级别的 `subcontract: releasing allowance … raised` / `closing grant … failed`——释放路径出错；清扫会重试。
- 在令牌过期很久之后仍停留在 `running` 状态的 `job_nodes` 行——一个从未结束的调用。

## 如何测试

| 测试内容 | 位置 |
|---|---|
| 并发下分包额度不会超支、失败的子调用会把钱交还、grant 随根一起失效、grant 拒绝其他付款、深度/循环/扇出、范围、根关闭后的退款、联邦子调用 | `tests/test_subcontract.py` |
| 路由与委托：被路由的根不携带作业上下文、被路由的子调用既不转发令牌也不转发 grant、链中的每份授权书都计入根及其子调用、分包额度无法覆盖的费用、失败的路由子调用及时退还价格和费用以供重试 | `tests/test_subcontract_chains.py` |
| 真实的 `weather.witness` 提供方对接真实的枢纽应用：成本加成、固定价格、签名检查、单份读数不构成见证、通过 A2A 的根调用、通过 A2A 失败的根调用仍显示其账单、提供方不能通过 A2A 购买、另一个产品的令牌重放 | `tests/test_subcontract_example.py` |
| 金丝雀对接同一个应用，通过 REST 和 A2A，两种模式都测，并验证它的每项检查在它要捕捉的那种情形下确实会失败 | `tests/test_subcontract_example.py::TestCanary` |
| A2A 桥接层拒绝作业头 | `tests/test_a2a_invoke.py` |

金丝雀是 [`scripts/subcontract_canary.py`](https://github.com/alexar76/aicom/blob/main/scripts/subcontract_canary.py)：我们自己的根买家，针对我们自己的组合服务，从外部检查本页的每一项声明。

```bash
SUBCONTRACT_CANARY_API_KEY=aimk_… scripts/subcontract_canary.py                 # cost-plus over REST
SUBCONTRACT_CANARY_API_KEY=aimk_… scripts/subcontract_canary.py --fixed-price
SUBCONTRACT_CANARY_API_KEY=aimk_… scripts/subcontract_canary.py --a2a           # root over A2A 1.0
```

它断言：根已交付；恰好有两个已扣费、深度为 1、按预期出资的子调用；`spent + released == allowance`；节点价格之和等于已花费金额；见证结果指名的是相同的节点；`GET /jobs/{job_id}` 返回分包额度已关闭的树；根收据在 `credentialSubject.parents` 中列出子调用的收据摘要；使用 `--a2a` 时，还有一个 `COMPLETED` 任务，`GetTask` 读回时带着同一份账单。

**2026-09-28 的实时运行**，08:47 UTC，`modelmarket.dev`（hub 3.7.0），根调用走 A2A，柏林，分包额度 $0.01：全部九项检查通过——上面的八项，外加一项非关键检查：两份读数在地点和时间上一致（相距 0 km、0 s）。两份读数从分包额度中扣费，每份 $0.001，花费 $0.002，释放 $0.008，买家总共被扣 $0.004；作业 `job_5346033bb2ce717936278f7c`；三张工作凭证在 HISTOR 中锚定为叶 546–548。

要清楚它证明了什么：它是**自我驱动的**——我们的买家、我们的组合服务、我们的 GAIA、内部额度。每一跳都走生产代码路径，每一项声明都从外部检查，这正是它的用途；它并不能证明有其他人想要这个产品。

## 容易忽略的规则

- **把令牌和 grant 原样发回，不带任何其他东西。** grant 与 `X-API-Key`、授权书、通道或 x402 付款一同出现时，得到 `403 job_invalid`。
- **令牌随调用一起失效。** 在你的调用返回之后才发出的购买——来自后台任务、重试队列——会被拒绝。在服务期间购买。
- **子调用看到的余额数字是分包额度的。** 分包方永远不会得知根买家的余额，只知道还剩多少可以花。
- **失败子调用的钱仍然可以由你花**，只要根还在运行：它已回到分包额度。重试，或改向别处购买。
- **已交付就要付钱。** 如果你在分包方交付之后失败，买家会向它们付款，而不向你付款；账单会写明这一点。
- **为路由子调用指明 `source_hub`**，并记住失败的尝试仍会占用一个子调用名额。
- 花钱之前，**既要验证令牌的 capability，也要验证它的 `product`**。
- **通过 A2A 时，只有根调用换协议。** 作业内的购买发往 `/ai-market/v2/invoke`。
- **`null` 不等于零。** `spent_usd: null` 表示结算尚未完成，而不是什么都没花。

另见：[mandates.zh.md](mandates.zh.md) · [a2a.md](a2a.md) · [money-rails.md](money-rails.md) ·
[awr-receipts.md](https://github.com/alexar76/aicom/blob/main/docs/awr-receipts.md) · [规范，§6](https://github.com/alexar76/aimarket-protocol/blob/main/mandates.md#6-subcontracting-sub1) ·
[示例提供方](../examples/subcontract-capability/README.md)
