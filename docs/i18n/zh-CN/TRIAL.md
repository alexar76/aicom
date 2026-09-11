# 免费试用与升级

Personal 提供 7 天试用，Team 提供 14 天试用，Expert Market 提供 1 天试用。
每个经过验证的 actor 在每个产品上只能领取一次。

浏览器会创建 Ed25519 actor proof，Gateway 无需付款即可发放一个 `ask_...`
试用密钥。密钥会自动过期，并使用与付费密钥相同的 introspection、rotation
和 revoke 规则。

升级时，Gateway 会在 Base 上创建精确的 canonical USDC invoice。KOVA 验证交易，
达到所需 confirmations 后自动发放新的付费密钥。
