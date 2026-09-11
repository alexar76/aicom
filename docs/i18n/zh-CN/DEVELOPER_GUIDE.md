# 开发者实战指南

## 选择集成路径

当个人、团队或应用通过 `ask_` key 使用产品时，请使用 SaaS product API。当自主 agent 需要发现并 invoke 定价 capability 时，请使用 Hub federation。两条路径使用独立 credential 与 accounting。

- Personal：使用 Personal scope key 调用 `/memory/api/*`。
- Team：使用 Team key、有效 membership 调用 `/teams/api/*`。
- Expert Market：`/market/v1/listings` public discovery、`ask_` access 或 `amk_` metered read。
- Federation：通过 `https://hub.attestedmemory.net/ai-market/v2/manifest` discovery，并经 Hub invoke。

## 创建签名 actor

在 client runtime 中生成 Ed25519 key pair。Actor ID 是 `did:actor:` 加 raw 32-byte public key 的 SHA-256 hex。对这个精确 actor ID 字符串签名。使用无 padding 的 base64url 发送 `X-SaaS-Key`、`X-Actor-ID`、`X-Actor-Public-Key` 与 `X-Actor-Signature`。

切勿向 product API 发送 private key、seed phrase 或 checkout token。

## 完成首次 request

集成 payment 前先启用 trial。它不产生 wallet transaction，并会自动过期。写入一条 private Memory Unit，保存返回的 ID，再由同一 actor 读取。

`401` 表示 credential/proof 无效；`402` 表示需要 payment；`403` 表示 scope 错误；`409` 保护 state/idempotency；`429` 要求遵守 `Retry-After`。Read 使用有限 backoff；write 仅在应用拥有 idempotency 时重试。

## 发布 capability

提供 `/.well-known/ai-market.json`、签名 `/ai-market/v2/manifest` 和 HTTPS invoke URL。声明 `product_id`、versioned `capability_id`、JSON Schema、价格、publisher identity 与 public key。

使用 operator 发放的 scoped publisher token 调用 `POST https://hub.attestedmemory.net/ai-market/v2/supply/register`。不要公开 token。Provider 应在 startup 时重试注册，使 Hub restart 后 catalog 自动恢复。

## 自动 promotion

Attested provider 已自动发布 12 个 capabilities。Hub 提供签名 discovery、更新 `ecosystem.nodes`、记录 consumption，并向配置的 federation root announce 身份。

Promotion 不等于自我批准。外部 operator 必须检查并 pin identity 后才授予 trust。Social、directory 与 campaign 同样由 operator 控制。

## Production checklist

- Public endpoint 使用 HTTPS，provider-to-Hub token 保密。
- Pin signing identity，怀疑泄漏时 rotate token。
- 验证 size、timeout、rate limit 与 SSRF boundary。
- 将 signed result 绑定 capability、input hash 与 request ID。
- 测试 invalid signature、duplicate、timeout、revoke 与 replay。
- 验证 PostgreSQL backup/restore；production 禁止 SQLite。

继续阅读：[KOVA](KOVA_CAPABILITIES.md)、[用户指南](USER_GUIDE.md)和[使用场景](USE_CASES.md)。
