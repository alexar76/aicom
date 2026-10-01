# Attested 中的 KOVA capabilities

## KOVA 是什么

KOVA 是独立的 Base / USDC 服务，不部署在 Attested Hub 内部。它向 Hub 发布六个
product，agent 可通过 federation 发现、定价并 invoke。

## Agent 如何调用

Agent 调用 Hub 的 `POST /ai-market/v2/invoke`，而不是 KOVA 的 private provider URL。
Hub 应用访问与 settlement policy，记录 invoke 后将请求路由到 KOVA。

Capabilities 包括 `kova.network.status@v1`、`kova.asset.balance@v1`、
`kova.usdc.invoice.create@v1`、`kova.usdc.invoice.status@v1`、
`kova.usdc.invoice.cancel@v1` 和 `kova.usdc.webhook.register@v1`。

## Checkout 为什么使用另一条路径

Attested subscription 通过认证的 service-to-service 连接调用 KOVA invoice API，
不会为了验证当前购买再次购买 paid capability。这样可避免 recursive billing，并保证
一个 order 只创建一个 entitlement。

## 谁为 KOVA 付费

购买 Attested subscription 时，买家的 USDC 会直接发送到
`SAAS_PAYMENT_RECIPIENT`。该 transfer 不会自动为 KOVA split，也没有百分比分成。
Gateway 使用专用 `KOVA_API_KEY`；如果 key 来自付费 KOVA Pro 或 Business plan，
operator 需要单独购买或续期。Federated capability call 是第三条独立计量路径：
per-call price 和 Hub routing fee 作为 capability consumption 记录，绝不会从 Attested
subscription payment 中扣除。

## 可观察内容

Hub 记录 federated invoke 的 price、status 与 receipt。受保护的 Operator ledger 显示
Attested order、trial/paid key 和 request 数。KOVA Settlement desk 显示自己的 order、
key prefix 与 API usage；两者均不展示完整 key。

## 安全边界

Provider route 要求 private `X-AIMarket-Internal-Token`，校验 route/body identity，并对
write capability 使用更严格的限流。`X-Provider-Signature` 使用 Ed25519 绑定
`product_id`、`capability_id`、input hash 与 result，防止在不同 input 上 replay。

## 安全配置

设置随机且不少于32字符的 `KOVA_CAPABILITY_TOKEN`，与 Hub 的
`AIMARKET_CAPABILITY_TOKEN` 保持一致。配置 `KOVA_HUB_URL`、`KOVA_INVOKE_BASE`，
并仅在 private service network 内开放 provider endpoint。
