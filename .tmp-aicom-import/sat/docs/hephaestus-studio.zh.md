# HEPHAESTUS — 锻造：在付费之前先给能力图算出价格

> **English:** [hephaestus-studio.md](./hephaestus-studio.md) · **Русский:** [hephaestus-studio.ru.md](./hephaestus-studio.ru.md) · **Español:** [hephaestus-studio.es.md](./hephaestus-studio.es.md) · **Français:** [hephaestus-studio.fr.md](./hephaestus-studio.fr.md)
>
> How to drive the page: [hephaestus-user-guide.zh.md](./hephaestus-user-guide.zh.md) · What to build with it: [hephaestus-use-cases.zh.md](./hephaestus-use-cases.zh.md)
>
> 内核：[`hephaestus/`](https://github.com/alexar76/hephaestus/tree/main/)。监视器节点：`hephaestus`。执行器：`POST /ai-market/pipelines`。 · **安装与截图:** [hephaestus/README.md](https://github.com/alexar76/hephaestus/blob/main/README.md)

---

## 这是什么

HEPHAESTUS 把市场上的能力组成一条链，**在支付任何费用之前算出它的成本**，提交给管线执行器，并保留返回的
已签名 bill of materials（物料清单）——包括链条失败时应当归责的那一跳（hop）。

它不是通用的工作流搭建器。每个节点都是枢纽（Hub）已签名清单中的真实一行：带价格、带声明的时延、并带
明确说明的可靠性证据量。差别就在这里：这样的图能回答*这会花多少钱*和*是谁弄坏的*，而画多少个方框都给不出
这两个答案。

两个界面，刻意分开：

| 界面 | 职责 |
|------|------|
| Alien Monitor 的 `hephaestus` 节点 | **观察。** 真实运行——成本、跳数、归责的那一跳——以及目录中究竟有多少能真正连线。 |
| 工坊页面 | **搭建。** 选能力、填参数、看成本预估、提交。 |

监视器负责观察，不承载编辑器。一个凭空编造数据流的观察界面比空白界面更糟，所以在没有任何运行记录时，
面板就照实这么说。

## 工坊页面

枢纽在 **`/studio`** 上提供它，这并非随意选择：它用于组装的目录正是枢纽自己的已签名清单，
而枢纽的 CORS 是 fail-closed 的，所以放在别处的页面根本读不到。同源、无需桥接、不需要第二个域名。

运行同样是同源的。管线执行器是另一个服务，浏览器无法跨源访问，因此枢纽通过
`POST /studio/run` 转发一个请求。这个转发被刻意限制得很窄：

* 目标地址取自枢纽上的 `AIMARKET_PIPELINE_EXECUTOR_URL`，**绝不取自请求体** —— 让调用方
  决定目标的转发器，无论叫什么名字都是 SSRF 工具，而这个端点任何浏览器都能访问；
* 未配置就返回 `503` 并点明该变量，而不是去猜某个本地端口；
* 请求体在任何东西离开枢纽之前就按形状和大小校验，上限与执行器一致，同为十六个节点；
* 不转发调用方的任何凭据：工坊的运行路径是免费（sandbox）路径，付费运行由调用方直接带着自己的
  通道去找执行器。

响应携带 `trace_url`，因此页面链接到已签名的 bill of materials，而不是要求你相信它自己的摘要。

```bash
cd hephaestus/studio && npm install && npm run build   # 产出 dist/，由 /studio 提供
```

本仓库不跟踪构建产物，因此该产物由枢纽镜像中的一个 Node 构建阶段生成（运行时镜像只有 Python）。
若某次部署仍然缺少 `hephaestus/studio/dist`，会返回 `503` 并点明缺哪个构建，而不是 404。

当外壳**实际宽度**低于 900px 时，三列会变成一次只显示一列——目录、画布、检查——由底部栏切换：在 375px 下，能力面板与检查面板只会给画布留下几个像素，而画布正是必须可用的那一块。两种布局下成本预估都留在页头：
页面存在的理由就是它。添加模块会跳到画布，点按模块会跳到它的参数，因此点按永远不会落在看不见的
面板上。

该断点是用 `ResizeObserver` 在元素上测量的，而不是去问视口：一个窗口可以在物理上很窄，却报告一个很宽的
CSS 视口——手机上的桌面 user agent、被缩放的窗口、嵌入的框架——在这些情况下媒体查询始终为假，而画布已经
被压成一条。

## 向导——把目标拿去和目录求解

一个向导 = 一个目标 + 一串有序的**角色**。角色是对能力所*声明*内容的判定：它产出哪些字段、要求
哪些字段、id 长什么样——而绝不是写死的 `product_id`。所以向导不可能推荐一行没在卖的能力，目录
变了它也照样成立；一份人工整理的配方清单两者都做不到。

求解为每个角色挑一个能力，排序依次是：这一跳从上一跳接过多少数据，然后还剩多少要人手填，然后这
一行背后有没有实测观察，最后才是价钱。价钱故意排在最后——最便宜却干不成事的链条不是省钱。

两道防线，都是因为真实目录打败了幼稚版本才加上的：

* **`consumes`**——至少有一个连上的字段要对应角色本该接到的东西。没有它，
  `platon.random@v1` 会通过 `num_bytes` 和 `platon.beacon@v1` 配上：抽取把自己的参数原样
  回显在输出里，而信标又把这个参数当输入，于是两者接得干干净净，却什么都没审计。一跳消费上一跳
  的*参数*，不等于消费它的*结果*。
* **`sameProductAsPrevious`**——对密码学材料来说这是正确性，不是偏好。`proof` 是字段名，不是
  格式：求解器曾心安理得地把 `platon.random@v1` 的 VRF 证明喂给 VDF 验证器
  `chronos.verify@v1`，只因为两边都叫 `proof`。这条链会为第一跳收钱，然后在第二跳读不懂的证
  明上失败。普通数据——读数、位置——不受这条限制，因为那里来自*另一个*提供方的第二意见比同一家
  的更值钱。

角色填不满的目标会被返回为**不可用，并附上失败的那个角色**，菜单会带着原因显示它，而不是把它藏
起来。今天四个里有两个不可用，两个原因都是真实的缺口：没有人为 `platon` 自己的抽取卖验证器；而
`atlas.situation.brief@v1` 要求一个边界框（`west/south/east/north`），目录里没有任何能力产
出它——`atlas.point.read@v1` 给出的是一个 `point` 对象。一个悄悄丢掉缺失步骤的向导，会把一条
名不副实的链条交到人手里，而这个人会先付钱、后知道。

## 成本预估

两条规则让这个数字保持诚实，并由 [`hephaestus/tests/estimate.test.ts`](https://github.com/alexar76/hephaestus/blob/main/tests/estimate.test.ts) 中的测试锁定：

1. **没有价格的能力会被点名，绝不当作免费。** 它被排除在总额之外并单独列出：一个悄悄吞掉未知项的总额
   不是预估。
2. **金额以整数微美元累加。** 目录里的真实价格是 $0.001 的传感器读取和 $0.004 的预言机调用；用浮点数把
   这些相加，误差恰好落在构成总额的那几位上。

凡是枢纽路由到对等方的情形，都采用路由后价格：按提供方报价计算，会让每一个联邦跳都少算一笔路由费。

时延以「已声明时延的最长路径」给出，也就是一个**下限**：执行器目前按顺序走完各跳，因此真实运行不可能
更快。未声明时延的能力按零计入并按名列出，这样数字绝不会被猜测抬高。

## 可信的可靠性——`reputation_basis` 规则

枢纽清单为每一行发布 `success_rate_30d`。对于从未被调用过的行，这个数字是刻意选定的中性占位值：爬虫
会忽略对等方自报的成功率，因为一个能给自己标 99% 的对等方，会在首次索引时就垄断路由。

后果是：线上目录全部 76 行都发布 `0.5`，而文档中没有任何东西能区分「测得的二分之一」与「未被观察的占位
值」。现在清单把证据放在数字旁边：

| 字段 | 含义 |
|------|------|
| `observations_30d` | 发布方枢纽在过去 30 天内观察到的调用次数。 |
| `reputation_basis` | `measured` — 该比率等于该窗口内的成功数/尝试数。`unobserved` — 没有任何运行，该比率是占位值。 |
| `by_hub[*].trust_basis` | 对等方层面的对应字段：`measured`、`unobserved`，或发布方枢纽自身的 `self`。 |

**对所有消费方（包括我们自己的界面）的规则：依据 `reputation_basis`，绝不依据那个数字。** 当依据不是
`measured` 时，显示「尚无调用」，而不是一个分数。内核会直接丢弃该值而不向下传递
（[`hephaestus/src/catalog.ts`](https://github.com/alexar76/hephaestus/blob/main/src/catalog.ts)）；早于这些字段的枢纽读作 `unknown`，而这与
「差」并不相同。

一旦某个能力被调用过，清单就提供**测得的**比率——爬虫的注释一直声称枢纽自己会计算它；实际上没人计算，
于是 `0.5` 就被冻结进了每一份已签名清单。

## 可组合性——为什么有些行根本无法连线

只有当一个能力既声明了输入字段（一个 `properties` 对象，即使为空——「不接受输入」也是一个答案），**又**
有非空的输出模式时，它才是可组合的。任一条件不满足的行虽然可被发现、也有价格，但无法与相邻节点连接，
工坊会明确说明，而不是画一个通向虚无的端口。

为让目录变得可组合，在来源侧补齐了三处缺口：

* **Platon，9 个能力。** oracle-family 聚合器只按标识符、描述和价格联邦 Platon，因此每一行都继承了
  oracle-core 的「没有字段」默认值，而 Platon 自己却写明了 `num_bytes`、`client_seed`、`prompt`、
  `round`、`question` 等等。现在聚合器把 Platon 自己的声明透传过来，而不是重述一遍：一切手工重述都正是
  当年让 `platon.verify@v1` 上架售卖的那种漂移。
* **ATLAS，6 个 SKU。** `output_schema` 完全缺失：六个付费的决策产物，买家只有先买一次才能知道结果长什么
  样。现在模式如实反映各处理函数构建的内容，测试套件还从两个方向校验真实输出：模式不得过度承诺，也不得
  落后于处理函数。
* **确实不接受输入的能力**（`platon.state@v1`、`platon.commit@v1`、`gaia.fleet.status@v1`）声明了显式为空
  的 `properties`。这是正确的，不是坏的：「不接受输入」与「没有说明」是两种不同状态，工坊也分别呈现。

## 执行器能表达什么，不能表达什么

对于执行器无法运行的图，工坊会给出理由直接拒绝，而不是导出一份稍后会失败的 JSON——更糟的是那种能跑通、
却从错误的上游取数据的情况。

* **每条管线最多 16 个能力**（`PipelineRequest.nodes`）。更大的工作要拆成多个阶段。
* **每一跳只有一个携带数据的父节点。** `input_from` 只指名一个节点，因此只能把一条入边标记为数据来源；
  其余入边只表达顺序。
* **各跳按顺序执行。** 时延预估是下限，不是预测。

### `input_from` 指名一个节点

`input_from` 被声明为节点标识符，实现上却是个布尔量：任何为真的值都会注入最后完成的那一跳的结果。在
一条直链里两者一致；在 DAG 里则不然——有两个父节点的跳，拿到的是拓扑排序恰好第二个完成的那个父节点的
结果。于是一个汇聚图可以被画出、被估价、被支付，并从错误的上游取数据，而 bill of materials 上的签名依然
有效。

现在该字段指名它真正想要的父节点，且结果按节点保存，因此也可以指名较远的祖先。不匹配任何已知节点的值
保持原来的「最后结果」行为，因此现有调用方不受影响。

## 运行：由谁执行，由谁付费

这家工厂不托管的跳会被路由到枢纽的联邦 invoke，因为工坊是从枢纽目录组装的——七十六行，全部属于对等方——
而执行器自己只托管九个。在这条路由存在之前，访客能搭出的任何图都只会返回 `404 capability not found`。

真正需要决定的是钱，不是代码：

* **绝不附带执行器的任何凭据。** 一个未经认证、却能花掉运维余额的 Run 按钮就是敞开的水龙头，而它产出的每一张
  收据都会写错买家。
* **访客自己的试用身份贯穿全链** —— 浏览器 → 枢纽 → 执行器 → 枢纽 —— 通过 `X-AIMarket-Sandbox-Visitor`
  传递。枢纽按访客计量可续期额度，因此转发访客的 id 而不是服务的 id，正是「每人各有额度」与「所有人共用一个
  已耗尽的桶」之间的差别。
* **需要付费的跳就以该跳的身份失败。** `402` 表示需要付款，`429` 表示额度已用尽——原因可见，绝不悄悄扣款。
  成本预估依然会告诉你它本来要花多少。
* **bill of materials 按跳记录 `payer`** —— `local`、`trial`、`channel` 或 `unpaid` —— 因此一次免费运行
  永远不会成为购买的已签名证据。

超出免费额度后，跳会按调用方掌控的支付通道结算，记录里写的就是那个通道。

## 把一次运行读回来

执行器为每次运行签发并持久化一份 bill of materials。在这些路由存在之前，没有任何东西能把它读回来：跳级
归责——争议以及由此产生的罚没（slashing）所依据的证据——只有发起原始 POST 的那一方能看到。

| 路由 | 返回 |
|------|------|
| `GET /ai-market/pipelines?limit=N` | 近期运行的**脱敏投影**：成本、跳数、逐跳状态、归责。 |
| `GET /ai-market/pipelines/{trace_id}` | **已签名**的 bill of materials，逐字返回。 |

这样切分是刻意的。签名覆盖的是写入时的那个对象，因此对按 id 的响应做过滤，会交回一份无法验证的东西。
枚举则是相反的问题：一个公开的运行流会公布哪个支付通道为哪次运行付了钱，以及逐跳的收据 nonce——那正是
带金额的公开收据的查询键。所以列表去掉 `channel_id` 和 `receipt_nonce`，并让每一行指明其已签名原件的
路径。

### 归责

管线失败是失败那一跳的责任，绝不是整张图的责任。bill of materials 指名归责的跳，并明确为已完成工作的
上游各跳免责，使争议只指向负有责任的提供方：

```json
{
  "policy": "hop-level",
  "at_fault": {"id": "v", "capability_id": "metis.verify@v1", "status_code": 500},
  "not_at_fault": ["s"],
  "not_executed": ["d"]
}
```

## 提交一张图

蓝图会转换为执行器的请求体。只有能力节点会被发送：触发器和输出是人阅读画布的方式，不是要向谁计费的跳：

```json
{
  "nodes": [
    {"id": "s", "product_id": "prod-mcp", "capability_id": "web.search@v1",
     "input": {"query": "a claim"}, "depends_on": []},
    {"id": "v", "product_id": "prod-metis", "capability_id": "metis.verify@v1",
     "input": {"claim": "a claim"}, "depends_on": ["s"], "input_from": "s"}
  ]
}
```

```bash
curl -s -X POST https://magic-ai-factory.com/ai-market/pipelines \
  -H 'content-type: application/json' --data @blueprint.json
```

响应携带 `trace_id`、已签名的 `bill_of_materials` 和 `final_result`。

## 各部分在哪里

| 路径 | 内容 |
|------|------|
| [`hephaestus/src/catalog.ts`](https://github.com/alexar76/hephaestus/blob/main/src/catalog.ts) | 清单 → 能力目录；信誉规则 |
| [`hephaestus/src/estimate.ts`](https://github.com/alexar76/hephaestus/blob/main/src/estimate.ts) | 成本与时延预估 |
| [`hephaestus/src/blueprint.ts`](https://github.com/alexar76/hephaestus/blob/main/src/blueprint.ts) | 校验；蓝图 → `PipelineRequest` |
| [`hephaestus/src/wizards.ts`](https://github.com/alexar76/hephaestus/blob/main/src/wizards.ts) | 目标 → 角色 → 一条基于当日目录的链 |
| `alien-monitor/backend/hephaestus_status.py` | 为节点轮询运行记录与目录就绪度 |
| `alien-monitor/frontend/src/components/HephaestusRuns.tsx` | 观察面板 |
| `web/backend/services/ai_market_protocol/pipelines.py` | 执行器、追踪存储、投影 |

内核刻意不带依赖、不碰 DOM：它既要服务工坊页面，也要服务任何需要给蓝图估价或做转换的界面，因此不能夹带
某个 UI 框架的立场。

```bash
cd hephaestus && npm install && npm run check    # 类型 + 57 个测试
```

## 需要直说的限制

* 预估不是报价。价格来自读取时的已签名清单，提供方可能在运行之前改价。
* `reputation_basis: measured` 意味着有人在 30 天内通过*这个*枢纽调用过该能力。这是证据，不是保证。
* 已签名的 bill of materials 证明的是这个执行器记录了什么，并不证明结果正确——那是验证层的职责。
