# 用户指南

## 支付与密钥

在 `/billing` 选择 Personal、Team 或 Market。invoice 会显示金额、收款地址、
token、chain 和有效期。在 Base 上发送精确金额，等待确认后输入 tx hash。`ask_...`
付费密钥可使用 checkout secret 在48小时内恢复，之后仅保留 hash。即使浏览器关闭，
Gateway 也会自动核对支付状态。使用 `GET /v1/keys/me` 查看，使用 `POST /v1/keys/rotate` 轮换，
使用 `POST /v1/keys/revoke` 撤销。

## identity 与 memory

调用产品 API 时将有效付费密钥放在 `X-SaaS-Key` 中；它与 actor proof 分开。

受保护请求必须包含 `X-Actor-ID`、`X-Actor-Public-Key` 和
`X-Actor-Signature`。private key 始终留在客户端。写入使用 `/memory/api/memories`，
搜索使用 `/memory/api/search`。

## 团队

通过 `/teams/api/teams` 创建团队，通过 `/teams/api/teams/{team_id}/members` 管理成员，
每次操作都必须带上 `team_id`。Gateway 验证 membership，Hub 验证短期 assertion 和 actor signature。

`401` 表示认证无效，`403` 表示 scope 错误，`402` 表示需要支付，`429` 表示超过速率限制。不要向 API 发送 private key。

## Trial

通过 `/v1/trials` 开始 trial：Personal 为 7 天，Team 为 14 天，Expert Market
为 1 天。Gateway 无需付款即可发放绑定 actor 的 `ask_...` 密钥；同一签名 actor 可在
有效期内恢复密钥。到期后权限自动失效；如需继续使用，请完成 Base 上精确的 USDC 付款。详见
[TRIAL.md](TRIAL.md)。

## KOVA capabilities 与 checkout

Agent 通过 Hub federation 发现 KOVA；Attested checkout 使用独立的认证
service-to-service 路径。两条路径、receipt 与安全边界详见
[KOVA_CAPABILITIES.md](KOVA_CAPABILITIES.md)。
