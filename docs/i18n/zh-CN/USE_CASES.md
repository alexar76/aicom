# 使用场景

Attested Memory 面向那些 **遗忘代价很高**、**盲目信任更糟** 的场景。这些例子说明：何时笔记、聊天记录或向量库不够用——以及何时身份、truth state、provenance 与精确 settlement 能把上下文变成可据此行动的东西。

路由名、请求头与支付术语在各语言中保持原样。只本地化说明文字。

## 能扛住 context rot 的创始人第二大脑

**适用对象。** 每天在工具、智能体与设备之间切换的创始人、研究者或运营者。

**问题。** 决策散落在聊天、Notion 导出和半成品提示词里。六周后，没人说得清 *为什么* 做了那个选择、信任了哪些来源，或是哪个智能体编造了一份方便的摘要。

**运作方式。**

1. 写入一条 Memory Unit：决策、理由、标签与 `source_refs`。
2. 以 actor 身份签名（`X-Actor-ID` / public key / signature）。私钥留在客户端。
3. 之后通过 `/memory/api/search` 检索，并在新计划或智能体运行中复用前检查 truth + provenance。

**为何需要 attestation。** 你取回的不是「相似段落」，而是带有 actor 与谱系的可移植主张。

**开始。** [Personal Memory](/memory) · [用户指南](USER_GUIDE.md) · [/billing](/billing) 上的 trial。

## 保留决策轨迹的故障 war-room

**适用对象。** 值班工程师、SRE、安全响应人员。

**问题。** 故障频道比 wiki 更快。事后复盘靠记忆写成，每次决策的归属模糊；下周智能体又重复了被否决的缓解方案——因为共享 namespace 里从未签过任何东西。

**运作方式。**

1. 打开 Team Memory OS workspace，创建 team namespace。
2. 成员用 actor 签名写入故障笔记、被否决选项与最终动作。
3. SaaS gateway 校验 membership；Hub 只接受匹配的 `team:<id>` 记录。查询不会渗漏到其他团队。

**为何需要 attestation。** handoff 可审计。offboarding 撤销密钥；短生命周期的 team assertions 到期，无需在聊天记录里做取证。

**开始。** [Team Memory OS](/teams) · [用户指南 § Team](USER_GUIDE.md)。

## 出售专家知识而不泄露语料库

**适用对象。** 领域专家、研究机构、顾问精品店。

**问题。** 免费公开全部语料会毁掉生意；只发预告又毁掉信任。买家付款前需要看到 provenance；卖家需要有时限的访问，而不是默认永久副本。

**运作方式。**

1. 发布 Memory Unit：公开 summary 字段，正文使用付费 visibility。
2. 买家搜索目录、检查 truth/provenance，然后开出精确的 Base USDC invoice。
3. KOVA 验证转账；Gateway 签发 scoped entitlement。访问随套餐到期。

**为何需要 attestation。** discovery 诚实，settlement 精确。entitlement 是产品的密码学 scope，不是「凭信誉」的 PDF 链接。

**开始。** [Expert Memory Market](/market) · [支付](/billing)。

## 具备密码学连续性的多智能体 handoff

**适用对象。** 智能体运营者、编排团队、自主工作流。

**问题。** 智能体 A 把聊天摘要甩给智能体 B。摘要未签名、部分幻觉、且无来源。失败看起来像「下一个模型很笨」，真正的 bug 却是 provenance 的静默丢失。

**运作方式。**

1. 智能体 A 写入已签名的 handoff Memory Unit：约束、所用工具、来源、未决风险。
2. 智能体 B 按相同的 actor/team 策略取回，并在继续前验证 provenance。
3. truth state 随 unit 一起传递——矛盾会暴露出来，而不是被抹平成自信的散文。

**为何需要 attestation。** 连续性是记录的属性，不是谁碰巧开着标签页的属性。

**开始。** [Developers](/developers) · [用户指南 § Actor identity](USER_GUIDE.md)。

## 用绑定来源的 claims 做尽职调查与研究

**适用对象。** 分析师、法律顾问、投资与供应商审查团队。

**问题。** 尽职调查笔记引用「幻灯片」「电话会」「Slack 里的某条」。当 claim 被质疑时，保管链只是一种感觉。

**运作方式。**

1. 将每条重要主张记为带显式 `source_refs` 的 Memory Unit。
2. 证据到达时附加或更新 truth state（confirmed、disputed、insufficient）。
3. 之后用 provenance receipts 重建卷宗，而不是用重构的传说。

**为何需要 attestation。** 审阅者争论的是 claim 与证据，而不是谁的笔记「更新」。

**开始。** Personal 或 Team 产品 · [术语表](GLOSSARY.md)。

## 浏览器关闭后仍可完成的自动付费访问

**适用对象。** 从 wallet 应用付款的买家、结算 invoice 的脚本，以及无法盯着结账标签页的运营者。

**问题。** 传统结账在关闭标签页后即失效。「粘贴 tx hash」的手动流程制造支持工单与模糊的部分付款。

**运作方式。**

1. 使用唯一的 `Idempotency-Key`、套餐与 payer 调用 `POST /v1/billing/orders`。
2. 在 Base 上向 invoice 收款方发送精确的 canonical USDC 金额。
3. KOVA 核对 token、payer、recipient、amount 与 confirmation depth。
4. Gateway 自动激活产品密钥。用 checkout token 轮询 `GET /v1/billing/orders/{id}`，在 confirmed 后返回密钥——即使原始浏览器会话已消失。

**为何需要 attestation。** 资金流动与 entitlement 签发由精确的 invoice 身份绑定，而不是钱包截图。

**开始。** [Billing](/billing) · [用户指南 § Buy access](USER_GUIDE.md)。

## 不让机构记忆成孤儿的安全 offboarding

**适用对象。** 团队负责人、security、IT。

**问题。** 离职运营者仍持有含真实 runbook 的聊天导出与个人笔记。撤销 Slack 并不能撤销从未进入受控系统的机构记忆。

**运作方式。**

1. 将运营知识放在 Team Memory OS 的显式 namespace 下。
2. 离职时立即 rotate/revoke SaaS 密钥。
3. team assertions 在数分钟内过期；Hub 策略仍要求受保护读写具备 actor proofs。

**为何需要 attestation。** 访问结束是 control plane 事件，而不是指望有人删了 Drive 文件夹。

**开始。** [Team Memory OS](/teams)。

## 不适合的用途

- 没有身份或来源纪律的通用聊天归档。
- 存放钱包 private keys、seed phrases 或原始 credentials 的地方。
- 跳过 visibility 策略的无范围「与全世界分享」倾倒。
- 四舍五入或近似的加密支付——精确的 USDC 金额本身就是 invoice。

若你的工作流能容忍作者身份、来源与支付终局性的静默丢失，笔记本就够了。若不能，从上方对应的产品入口开始，并保持 Hub 合约精确。
