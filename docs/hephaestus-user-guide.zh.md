# HEPHAESTUS — 用户指南

> **English:** [hephaestus-user-guide.md](./hephaestus-user-guide.md) · **Русский:** [hephaestus-user-guide.ru.md](./hephaestus-user-guide.ru.md) · **Español:** [hephaestus-user-guide.es.md](./hephaestus-user-guide.es.md) · **Français:** [hephaestus-user-guide.fr.md](./hephaestus-user-guide.fr.md)
>
> 页面：**[modelmarket.dev/studio](https://modelmarket.dev/studio)** · 内部如何运作：[hephaestus-studio.zh.md](./hephaestus-studio.zh.md) · 能用来做什么：[hephaestus-use-cases.zh.md](./hephaestus-use-cases.zh.md) · **安装与截图:** [hephaestus/README.md](https://github.com/alexar76/hephaestus/blob/main/README.md)

---

## 一段话说清能做什么

从市场里挑选能力、把它们连起来、在**运行之前**看到这条链要花多少钱、运行它，并保留一份关于实际发生了什么的
已签名记录——包括某一步失败时该由哪一步负责。无需账号。前几次运行免费。

## 打开

访问 **[modelmarket.dev/studio](https://modelmarket.dev/studio)**。它不会以空白画布开场，而是打开一个
可用的示例：两个能力已经连好、算好价、可以直接运行。页头显示的正是这个页面存在的理由：

```
$0.0030 · 2 hops · ≥101 ms          5 free runs left · every hop has an observed success rate
```

* **$0.0030** —— 运行这张图的花费。由实时价目表求和得出。
* **2 hops** —— 付费的步骤。`Start` 与 `Result` 不是步骤，它们只标记图的起点和终点。
* **≥101 ms** —— 是下限而不是预测：目前各步依次执行，因此真实运行不可能更快。
* **5 free runs left** —— 你的免费余额，计在本浏览器中保存的一个随机 id 上。它不是账号，也不包含任何关于你的信息。

![刚打开的页面：左侧目录、两跳的图、页首的估价](https://github.com/alexar76/hephaestus/blob/main/docs/screenshots/opens-on-a-real-chain.png)

*页面刚打开就是这样：一条已经接好、也已经算好价钱的链。*

## 从目标出发，而不是从能力 id 出发

七十六行叫作 `gaia.verify@v1` 之类的名字，那是一份目录，不是答案。如果你要的是*一个能在争论
中站得住的测量值*，你得先知道：读数和对它的裁定是两笔独立的购买，而且前者要喂给后者。

页首的 **Wizards** 按钮改为直接说出目标。每一项都会先展示它用今天的目录会搭出的链条，以及价
钱，然后才由你决定是否载入：

![打开的向导菜单：两个目标带着链条和价钱，另两个写明为什么搭不出来](https://github.com/alexar76/hephaestus/blob/main/docs/screenshots/wizards-are-goals.png)

*目标，以及各自要花多少钱——还有两个目录今天满足不了的。*

点一下，链条就落到画布上，已经接好、已经填好，就像你亲手搭的一样。之后没有任何东西被藏起来：
它就是一张普通的图，可以改、可以重新估价、也可以丢掉。

市场**满足不了**的目标仍然留在列表里，并写明原因——例如*「这里在卖的东西里，没有一个能填上
『接受一个位置的简报』这一步」*。这不是你的错，而是当前在售内容里的一个缺口，在围绕它做采购计
划之前值得知道。

向导永远不会做两件事。它不会为了让目标看起来可行而缩短链条：某一步没有候选，整个目标就是不可
用。它也不会仅仅因为两跳共用一个字段名就把它们连起来：一跳必须消费上一跳的*结果*，而一旦涉及
密码学材料，还必须来自同一个提供方。这两条规则的由来，是目录里确实存在看着能连、实际不能连的
组合。

## 三个面板

| 面板 | 用途 |
|------|------|
| **目录**（左） | 所有在售能力：标识符、价格，以及其可靠性背后有多少证据。可按 id 或描述过滤。点击即添加。 |
| **画布**（中） | 图本身。拖动可移动；从一个模块下方的圆点拉到另一个模块上方的圆点即可连接。点击连线可切换它是否携带数据。 |
| **参数 / 检查 / 上次运行**（右） | 所选模块的字段、图中所有问题，以及上次运行返回了什么。 |

在手机上，三个面板变成一次只显示一个，由底部栏切换。

<p>
  <img src="../hephaestus/docs/screenshots/mobile-canvas.png" alt="390px 下的画布" width="220">
  <img src="../hephaestus/docs/screenshots/mobile-catalogue.png" alt="390px 下的目录标签页" width="220">
</p>

*同一个页面在 390px 下——「目录」和「画布」用底部的横条切换。*

## 如何读一行目录

```
gaia.weather.read@v1
$0.0010   127 calls (30d), 99.2% ok
```

价格就是将向你收取的金额，含任何路由费。第二行是**证据，不是评分**：只有当过去三十天真的有人通过这个枢纽
调用过该能力时才会出现。若无人调用过，它会写 **「no calls yet」**——今天 76 行里有 49 行正是这种诚实的
状态。这不是差评，而是没有评分。

某一行也可能被置灰并给出原因，例如 *「declares no output schema — nothing downstream can use it」*。
这类行无法与任何东西相连，页面会直说，而不是让你画一个通向虚无的端口。

## 填写参数

选中一个模块。它的字段完全来自提供方的公开声明，没有任何臆造。必填字段标有 `*`。有些能力根本不接受输入，
并会明确说明。

**字段可以从前一步读取，而不必写死一个值。** 写：

```
${read.reading}
```

运行时该值就来自名为 `read` 的那一步。`${read}` 交出该步的完整结果；
`${read.reading.values.temperature_c}` 深入其中取一项；`seen at ${read.ts}` 把值放进一句话里。正是这一点
让一条链成为管线，而不是一串彼此无关的调用——开场示例演示的就是它。

引用会在你能运行之前被校验：它必须指向画布上存在的步骤、不能指向自己，而且那一步必须保证先执行。若不成立，
**检查**面板会说明是哪一个以及为什么。

![选中验证器；它的 reading 和 attestation 两个字段里写着 ${read.reading} 和 ${read.attestation}](https://github.com/alexar76/hephaestus/blob/main/docs/screenshots/references-in-the-fields.png)

*一个字段读取上一跳的结果。检查面板会写明哪个字段流向哪里。*

## 检查

所有会妨碍图运行的问题，一次列清，用平实的话：

* `"gaia.verify@v1" needs "reading" (object)` —— 必填字段为空。
* `"Start" is not connected to anything` —— 有模块无法到达。
* `Pipelines take at most 16 capabilities` —— 执行器的上限；把工作拆开。
* `"check" is fed by 2 connections at once` —— 一步只能从一个上游步骤取数据；把其中一条连线标为数据来源。

警告是黄色的，不会阻止运行：没有公开价格、或没有声明返回内容的能力仍然可用，只是你对它了解更少。

## 运行

**Run** 提交这张图。返回的是一份真实记录，而不是摘要：

```
tr_c87f3be013e4
$0.0030 · 2 hops · 771 ms
✓ gaia.weather.read@v1 · $0.0010
✓ gaia.verify@v1 · $0.0020
signed bill of materials →
```

点链接可看已签名的原件——争议时所依据的就是同一份文件。若某步失败，记录会指名归责的那一步，并明确为已完成
工作的步骤免责：

```
at fault: gaia.verify@v1 (HTTP 500) · cleared: read
```

**Copy request** 会把精确的 JSON 复制到剪贴板，因此同一张图也可以从终端、CI 任务或你自己的智能体运行。
页面是便利，不是关卡。

![一次跑完的运行：追踪号、两跳各自的价钱，以及裁定](https://github.com/alexar76/hephaestus/blob/main/docs/screenshots/signed-bill-of-materials.png)

*跑完之后：追踪号、每一跳花了多少，以及验证器的裁定。*

## 花多少钱，以及谁付

* **免费运行。** 每位访客都有一份可续期的小额余额，计在本浏览器的随机 id 上。清空存储后你就是一位新访客、
  拥有新余额：这是试用，不是安全边界。
* **免费额度不包含什么。** 用付费模型生成答案的能力每次调用都花真实预算，因此不可能免费。这类步骤会返回
  要求付款。
* **不会悄悄从任何人账上扣款。** 既无余额又没有自己的通道时，付费步骤会带着原因失败。而成本预估依然会告诉你
  它本来要花多少。
* **真正付费。** 超出免费额度后，步骤需要一个由你掌控的支付通道。运行随后按它结算，并且记录里写的是该通道，
  而不是替你转发请求的那个服务。

## 动手之前值得知道的限制

* 每次运行最多 **16 个能力**。
* **每步只有一个数据来源** —— 可能需要多个步骤先完成，但只有一个交出其结果。
* **各步依次执行。** 时延数字是下限。
* **预估不是报价。** 价格来自读取时的已签名列表，提供方可能在你运行前改价。
* **已签名记录证明执行器做了什么，而不是答案正确。** 结果是否*为真*是验证类能力的职责——而你可以把一个放进
  图里，开场示例正是这么做的。

## 如果看起来不对

| 你看到的 | 含义 |
|----------|------|
| 每行都是 `no calls yet` | 三十天内没人通过这个枢纽调用过这些能力。诚实，不是坏了。 |
| 某步以 `402` 失败 | 它需要付款，而没有附上通道。 |
| 某步以 `429` 失败 | 你的免费余额暂时用完了；它会续期。 |
| `unresolved reference: …` | 上游那一步跑完了，但没有返回你引用的字段。它的输出模式会告诉你它到底返回什么。 |
| `executor_not_configured` | 这套部署没有管线执行器。这由运维处理，不是你。 |
| 目录是空的 | 页面读不到枢纽的清单。由于页面本就是枢纽提供的，这通常意味着枢纽本身不可达。 |
