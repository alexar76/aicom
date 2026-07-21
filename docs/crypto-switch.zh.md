# 加密 / 链上经济 — 总开关

AICOM 默认**不使用任何区块链**。除非你明确选择启用，否则加密功能处于**关闭**
状态。开关关闭时，任何组件都不会加载钱包、连接链/RPC、开启支付通道、返回
`402 Payment Required`、在链上验证交易或结算 UNI/彩票。所有组件仍然运行 ——
能力在免费层级提供，联邦签名和内部记账继续工作 —— 只是从不接触资金。

## 在 Alien Monitor 中你会看到什么

监视器显示**真实**状态，绝不伪造：

| 模式 | 链上下文 | 链上节点 (chain · escrow · NFT · ACEX · lottery) |
|------|----------|--------------------------------------------------|
| **TEST** | 从不 | 脚本化/模拟 |
| **UNI** | **始终**（私有本地 Anvil —— 绝不使用 Base） | 在本地链上实时运行 |
| **LIVE**，加密 **OFF** | 无 | **变灰 / 禁用** + 徽章「设置中已禁用真实区块链」 |
| **LIVE**，加密 **ON** | Base mainnet | 在 Base 上实时运行、点亮 |

这与代理端的契约 `shouldBuildChainContext(mode, cryptoEnabled)`
（`argus/src/ecosystem/networks.ts`）一致：`uni → 始终`、`live → 仅在加密开启时`、
`test → 从不`。安全不变式：`shouldBuildChainContext("live", false) === false`。

## 如何启用真实的链上经济

1. **总开关。** 在生态系统的 `.env` 中设置 `AIFACTORY_CRYPTO_ENABLED=1`。真值：
   `1`、`true`、`yes`、`on`。其他任何值（或未设置）= OFF。
2. **按组件配置。** 每个组件仍需要自己的真实配置：RPC 端点、接收方/合约地址
   以及钱包密钥。
3. **生产环境联锁。** 在生产环境中，现有的 `AIFACTORY_PROD` fail-closed 门控仍在
   开关之上生效。
4. **特别是 Alien Monitor。** 以 LIVE 模式部署，使其绑定到真实链：
   ```bash
   ALIEN_MODE=real AIFACTORY_CRYPTO_ENABLED=1 ./scripts/deploy_alien_monitor.sh --live
   ```
   在 UNI 模式下，监视器始终使用其私有本地 Anvil 链，且无论此开关如何都绝不
   接触 Base。

## 安全

只有当你确实打算运行**真实的链上经济**（Base 上的真实资金）时才启用加密。保持
关闭是安全的默认设置，可让整个生态系统在免费层级上完全可用。
