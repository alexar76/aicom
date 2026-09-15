# HEPHAESTUS — 使用场景

> **English:** [hephaestus-use-cases.md](./hephaestus-use-cases.md) · **Русский:** [hephaestus-use-cases.ru.md](./hephaestus-use-cases.ru.md) · **Español:** [hephaestus-use-cases.es.md](./hephaestus-use-cases.es.md) · **Français:** [hephaestus-use-cases.fr.md](./hephaestus-use-cases.fr.md)
>
> 如何操作页面：[hephaestus-user-guide.zh.md](./hephaestus-user-guide.zh.md) · 内部如何运作：[hephaestus-studio.zh.md](./hephaestus-studio.zh.md) · **安装与截图:** [hephaestus/README.md](https://github.com/alexar76/hephaestus/blob/main/README.md)

---

下面每条链都由**今天**在售的能力搭成——来自 GAIA、预言机家族与 ATLAS 的 76 行——价格取自实时价目表实际发布的
数值。JSON 就是 `Copy request` 给出的内容，因此每条都能原样从终端或智能体运行。

---

## 1. 一份站得住脚的传感器读数

**给谁用：** 任何决策依赖别人设备上的数字的人。
**成本：** $0.0030 · **2 跳** · 免费额度即可覆盖。

孤立的读数只是一个说法。这条链先买读数，再为它买一个第二意见——来自一个统计验证器，它检查取值范围、变化速率
以及与同类设备的一致性——并把两步都保留在一份已签名记录里。

```json
{"nodes": [
  {"id": "read", "product_id": "gaia.gateway", "capability_id": "gaia.weather.read@v1",
   "input": {}, "depends_on": [], "source_hub": "https://iot.modelmarket.dev"},
  {"id": "check", "product_id": "gaia.gateway", "capability_id": "gaia.verify@v1",
   "input": {"reading": "${read.reading}", "attestation": "${read.attestation}"},
   "depends_on": ["read"], "source_hub": "https://iot.modelmarket.dev"}
]}
```

返回的是一个裁定，而不是感觉：

```json
{"verified": false, "score": 0.6667, "summary": "failed: sibling:pressure_hpa",
 "checks": [{"name": "known_device", "ok": true}, {"name": "device_attestation", "ok": true}]}
```

**为什么值这个钱：** 验证器不同意传感器，并指出是哪一项检查没通过。这就是「我们拿到了一个读数」和「我们拿到了
一个读数，并且知道该信它几分」之间的差别。工坊开场用的就是这条链。

---

## 2. 不需要相信任何人的抽签

**给谁用：** 组织抽奖、分配额度、抽取随机审计样本的人。
**成本：** 约 $0.0060 · **2 跳**。

`platon.random@v1` 返回随机字节，并附可复现证明与 Ed25519 签名；`chronos.eval@v1` 是可验证延迟函数——证明确实
经过了真实的顺序时间。把二者串起来，得到的抽签既无法事后重摇，也不可能被提前算出。

```json
{"nodes": [
  {"id": "seed", "product_id": "prod-platon", "capability_id": "platon.random@v1",
   "input": {"num_bytes": 32}, "depends_on": [],
   "source_hub": "https://oracles.modelmarket.dev/family"},
  {"id": "delay", "product_id": "prod-chronos", "capability_id": "chronos.eval@v1",
   "input": {"seed": "${seed.random_hex}", "difficulty": 200},
   "depends_on": ["seed"], "source_hub": "https://oracles.modelmarket.dev/family"}
]}
```

**为什么值这个钱：** 把追踪记录公开，参与者可以自己核验这次抽签。你不需要请求别人相信你。

---

## 3. 在敲定设计之前先演练成本

**给谁用：** 需要回答「这条管线跑一百万次要多少钱」的人。
**成本：** $0 —— 你根本不按 Run。

把正在考虑的图搭出来。页头按已签名价目表给出每次运行的价格、逐跳拆分，另加一个时延下限。乘上你的量级。把某一跳
换成更便宜的提供方，看数字如何变化。

成本预估拒绝做两件事，而这正是它有用的原因：

* 没有价格的能力会被**点名**，绝不算作免费；
* 金额按整数微美元累加，因为一份由 $0.001 读取构成的目录，在浮点相加中无法完整保留。

**为什么值得做：** 这个答案站得住脚。它出自对等方签名的价格，而不是某人手敲的表格。

---

## 4. 争议时的证据

**给谁用：** 在一个工作流里向多个提供方付费的任何人。
**成本：** 你已经做过的那次运行。

当一条链失败时，已签名的 bill of materials 会指名归责的那一跳，并**明确为**已完成工作的跳**免责**：

```json
{"policy": "hop-level",
 "at_fault": {"id": "check", "capability_id": "gaia.verify@v1", "status_code": 500},
 "not_at_fault": ["read"], "not_executed": []}
```

每一跳还记录了由谁付费——`trial`、`channel` 或 `local`——因此一次免费运行绝不会被误认为一笔购买。

**为什么值这个钱：** 没有跳级归责，失败的链就只剩一张账单和一场争吵。有了它，上游提供方拿到钱，失败者被指明，
并且有一份可以指着看的已签名文件。生态的罚没机制读的正是这个。

---

## 5. 判断某个能力值不值得买

**给谁用：** 在多个报价之间挑选的集成方。
**成本：** 免费，在额度之内。

目录按行公布：价格、声明的时延、它是否声明了输入与输出，以及其可靠性背后有多少证据。今天的情况是
**27 行有实测成功率、49 行完全没有**——对后一组，页面写的是「no calls yet」，而不是把占位数值当成评分展示。

把这一行加进来、填好字段、用免费额度跑一次、读真实结果。然后再决定。

**为什么值得做：** 你用自己的输入评估，而不是卖家挑选的演示，并且一分钟内就能知道模式是否与现实相符。

---

## 6. 把一张图交给你自己的智能体

**给谁用：** 正在构建一个应当真去购买工作、而不是假装完成的智能体的人。
**成本：** 图值多少钱，就按你的通道付多少。

手工搭好并检查这张图，按 **Copy request**，把 JSON 贴进你的智能体。它会把同样的请求体发给执行器，拿回同样的
已签名记录。工坊是人推敲形状的地方；智能体负责把它跑一千遍。

```bash
curl -s -X POST https://magic-ai-factory.com/ai-market/pipelines \
  -H 'content-type: application/json' --data @graph.json
```

**为什么值得做：** 你测过的东西，与真正运行的东西逐字节相同。

---

## 它不适合做什么

* **通用流程引擎。** 没有循环、分支、重试或 HTTP 节点；加上它们，就换掉了这里唯一的优势——每个节点都是一行
  有价格、可验证的市场记录。
* **数据转换工具。** 值通过 `${hop.field}` 在跳之间传递，但不会被重塑。转换本身应当是某人出售的一个能力。
* **存放机密的地方。** 字段会送到提供方。不要在字段里写任何你不愿直接交给该提供方的东西。
* **答案为真的证明。** 已签名记录证明执行器做了什么。结果是否正确，是验证跳的职责——见第一个场景。
