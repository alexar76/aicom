# Expert Memory Market 实施指南

本指南说明 buyer、publisher 与 agent integrator 的真实 production 路径。
Public discovery、paid delivery、publisher accounting 与 proof 是有意分离的 contract。

## 集成前选择 access 路径

- 使用1天 trial，在无需 wallet transaction 的情况下验证 UX 与 API。
- Expert Pass 使用 scoped `ask_` key 提供7天 storefront 探索。
- 当每个已交付 Memory Unit 都需要归因并支付给 publisher 时，使用 per-read。
- 不要混淆 pass 与 publisher revenue：pass 支持 storefront，Meter capture 支持 publisher split。

## 购买前检查 listing

无需 key 即可调用 `GET /market/v1/listings?q=<topic>`。每个条目公开 summary、
`rank_score`、`rank_reasons`、Truth、Provenance、price 与 publisher。
`GET /market/v1/listings/<memory_id>` 永远不会返回付费正文。

如果公开 evidence 不足以满足你的 policy，请拒绝该 listing。高 score 不是信任指令。
Rejected claim 低于 unverified，popularity 不是 ranking signal。

## 从免费 trial 开始

使用 `trial=expert-market` 打开 `/`，或使用 setup wizard。Browser 创建 Actor
Identity 并在本地保留 private signing key。Gateway 为每个 actor/product 发放
一次1天 trial。将 `ask_` 存在 secret vault 中，切勿放入 URL、log 或 client analytics。

Trial 用于验证 product fit，不创建 payment、split 或永久 entitlement。

## 购买 pass 或已交付 read

Expert Pass：打开 `/billing?plan=expert.pass.7d`，创建精确 invoice，在 Base 上
发送 canonical USDC，并等待 KOVA finality。Gateway 发放7天 key；checkout
recovery 有效48小时。

Per-read：在 Attested Meter 创建并充值 account，将 `amk_` 保留在 server-side，
然后使用 `x-meter-key` 与 `{"memory_id":"<id>"}` 调用
`POST /market/v1/read`。Meter 先 reserve 价格，仅在 content 交付后 capture；
失败或拒绝会释放 reserve。

## 发布 expert memory 并设定价格

- 创建包含精确 title、有用 public summary、tags 与 `source_refs` 的 Memory Unit。
- 收费前添加可用的 Truth / Provenance evidence。
- 使用签名 identity 与 Base payout address 调用 `POST https://meter.attestedmemory.net/v1/publishers`。
- 保密 publisher key，仅通过 `/v1/publishers/me/prices` 为自己的 `expert.read:<memory_id>` 定价。
- 向 buyer 推广前先检查 public listing。

Standard split 为 publisher 70% / platform 30%；Publisher Pro 为 85% / 15%。
达到最低额后，operator 发放签名 `attested.payout/v1` 并记录 transaction hash。

## 集成 autonomous agent

- 分离 discovery 与 purchase；评估 metadata 后再授权 spend。
- 设置 maximum price、allowed publisher、Truth state 与 source policy。
- 将 `ask_`、`amk_` 保存在 server secrets，并从 traces 中清除。
- `401` 表示 credential，`402` 表示 access/balance，`403` 表示 scope，`429` 表示 backoff。
- 将 listing ID、rank reasons、charge ID、provenance receipt 与结果一同保存。
- Invoice 使用 idempotency；不要用不同 amount 重试 transfer。

## 在 team 中 rollout

- 定义首个 knowledge category 及其要改善的 decision。
- 邀请 buyer 前准备10–20条高质量 listing。
- 约定 public summary 与必需 source 的最低标准。
- 测试成功、unknown memory、insufficient balance、upstream failure 与 revocation。
- 监控 discovery-to-read、refusal、capture/release、accrual 与 payout backlog。

## 理解 trust 与 money 边界

Memory Market 负责 ranking 与 entitled memory 交付；Attested Meter 负责 reserve、
capture、accounting 与 payout；Attested Prove 负责无需 key 的 receipt verification。
KOVA 通过 authenticated service-to-service 验证 subscription settlement，并可在
federation 中独立使用。

任何组件都不会索取 seed phrase 或 wallet private key。USDC 直接发送给 recipient，
payout 另行执行。参见 [KOVA_CAPABILITIES.md](KOVA_CAPABILITIES.md) 与
[MARKET_USE_CASES.md](MARKET_USE_CASES.md)。
