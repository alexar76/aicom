# ERC-8004 身份：AIMarket Hub、HISTOR 与 WARDEN

[English](erc-8004-identities.md) · [Русский](erc-8004-identities.ru.md) · [Español](erc-8004-identities.es.md) · [Français](erc-8004-identities.fr.md) · **中文**

自 2026-10-01 起，我们的三项服务已在 Base 主网的 [ERC-8004](https://eips.ethereum.org/EIPS/eip-8004) IdentityRegistry 中注册为智能体。任何读取该注册表的智能体、钱包或区块浏览器，都能找到它们每一个、其所有者，以及一份注册文件，说明该服务是什么、从哪里访问。

## 三个智能体

| 智能体 | agentId | 是什么 | 注册文件 | 区块浏览器 |
|---|---|---|---|---|
| AIMarket Hub | `96682` | 智能体 capability 的联邦市场，经 MCP、A2A 和 x402 按次售卖 | [aimarket-hub.json](https://modelmarket.dev/.well-known/erc-8004/aimarket-hub.json) | [8004scan](https://8004scan.io/agents/base/96682) |
| HISTOR | `96683` | MCP 服务器的透明日志：每个服务器公布过什么，何时发生了变更 | [histor.json](https://modelmarket.dev/.well-known/erc-8004/histor.json) | [8004scan](https://8004scan.io/agents/base/96683) |
| WARDEN | `96684` | MCP 防火墙：在宿主把工具定义展示给模型之前先行扫描 | [warden.json](https://modelmarket.dev/.well-known/erc-8004/warden.json) | [8004scan](https://8004scan.io/agents/base/96684) |

## 链上记录

- **注册表：** Base 主网（链 ID 8453）上的 IdentityRegistry [`0x8004A169FB4a3325136EB29fA0ceB6D2e539a432`](https://basescan.org/address/0x8004A169FB4a3325136EB29fA0ceB6D2e539a432)，`AgentIdentity` 版本 2.0.0——这是 ERC-8004 的官方部署，而不是我们自己部署的副本。
- **三者的所有者：** 运营者钱包 [`0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a`](https://basescan.org/address/0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a)。
- **调用：** 每个智能体一次 `register(string agentURI)`；agentURI 即注册文件的 URL。

| 智能体 | 交易 | 区块 |
|---|---|---|
| AIMarket Hub（`96682`） | [`0x207807…284bae`](https://basescan.org/tx/0x207807bbd9dc346e775f8db3cb2aa6b59190fe27e8b4b15d75eb9f5175284bae) | 52046664 |
| HISTOR（`96683`） | [`0xcec3de…f68fd6`](https://basescan.org/tx/0xcec3deb9a343b7257d4d83cbcb80cc3831647d0a907552a7ee14f7dcf7f68fd6) | 52046664 |
| WARDEN（`96684`） | [`0xa784ca…937fda`](https://basescan.org/tx/0xa784cacbea144ed5d9f9ac98e36ae3175f06907c3f8f7f308d5f5c7b37937fda) | 52046664 |

- **费用：** 三笔交易的 gas 合计 0.0000031 ETH。
- **出块后核对：** 对每个 agentId，`ownerOf` 都返回运营者钱包，`tokenURI` 都返回注册文件的 URL。
- **未做的事：** 没有向 ReputationRegistry 写入任何内容；ValidationRegistry 也没有可供写入的官方部署。前者是我们有意为之。理由见：[ERC-8004 对齐](erc-8004-alignment.md)。

## 注册文件

每个 agentURI 都解析为一份 EIP-8004 `registration-v1` JSON 文档，由 `https://modelmarket.dev/.well-known/erc-8004/` 提供：包含名称、描述、图片、服务端点（视智能体而定，可能是网页、MCP、A2A、A2MCP、x402、DID 或 npm 包），以及一条 `registrations` 条目——写明 agentId，并将注册表标为 `eip155:8453:0x8004A169…a432`。

`https://modelmarket.dev/.well-known/agent-registration.json` 列出全部三个 agentId。它是 modelmarket.dev 的域名证明：这个域名提供注册文件以及 hub 和 A2MCP 端点，并借此确认这些注册属于它自己。HISTOR 和 WARDEN 各自的网站域名也确认了自己的注册：`https://histor.modelmarket.dev/.well-known/agent-registration.json` 列出 `96683`，`https://warden.modelmarket.dev/.well-known/agent-registration.json` 列出 `96684`。

文件可以在不发新交易的情况下更改，因为链上的 agentURI 指向的是 URL，而不是内容：修改 `build.py`，重新生成，再上传。

## Hub 声明自己的身份

根域名上的 Hub 在它自己的已签名发现文档 [`/.well-known/ai-market.json`](https://modelmarket.dev/.well-known/ai-market.json) 中，用一个 `erc8004` 块写明自己的 agentId：

```json
{
  "agent_id": "96682",
  "chain": "eip155:8453",
  "identity_registry": "0x8004A169FB4a3325136EB29fA0ceB6D2e539a432",
  "reputation_registry": "0x8004BAa17C55a88189AE136b182e5fdA19dE9b63",
  "agent_uri": "https://modelmarket.dev/.well-known/erc-8004/aimarket-hub.json",
  "verified_by_this_hub": false
}
```

`verified_by_this_hub: false` 是有意为之。这是一项自我声明：读者应对照注册表去确认，而不是听信 Hub 的一面之词。任何 Hub 运营者用自己的钱包完成注册后，都可以通过 `AIMARKET_ERC8004_AGENT_ID`、`AIMARKET_ERC8004_CHAIN`、`AIMARKET_ERC8004_NETWORK` 和 `AIMARKET_ERC8004_AGENT_URI` 做同样的事。

## 自行核对

以上所有内容都可以在不信任我们的前提下核对：

```bash
REG=0x8004A169FB4a3325136EB29fA0ceB6D2e539a432
RPC=https://mainnet.base.org
cast call $REG "ownerOf(uint256)(address)" 96682 --rpc-url $RPC    # 0x1218ff36…Ad0a
cast call $REG "tokenURI(uint256)(string)" 96682 --rpc-url $RPC    # …/erc-8004/aimarket-hub.json
curl -s https://modelmarket.dev/.well-known/erc-8004/aimarket-hub.json
curl -s https://modelmarket.dev/.well-known/agent-registration.json
curl -s https://modelmarket.dev/.well-known/ai-market.json | jq .erc8004
```

查 HISTOR 或 WARDEN 时，在 `cast` 两行中改用 `96683` 或 `96684`，在第一条 `curl` 中改用 `histor.json` 或 `warden.json`；`erc8004` 块只存在于 hub 的文档中。

## WARDEN 对其他代理的评价：每周重新核查

WARDEN 在声誉注册表（Base 上的 `0x8004BAa17C55a88189AE136b182e5fdA19dE9b63`）中评价其他代理。它选取所有 MCP 端点经 8004scan 验证的活跃 Base 代理，向该端点请求 `tools/list`，并用已发布的 `@aimarket/warden` 扫描每一个工具定义。没有阻断性发现时，为每个代理发布一条评价：数值为 WARDEN 评分，`tag1` 为 `warden-scan`，`tag2` 为规则集（`ruleset-v8`）。评价链接到一份报告，报告写明扫描器、规则集摘要以及所扫描定义的哈希，报告的 keccak 哈希记录在链上。报告明确说明其性质：某一时刻对工具定义的静态检查，不是对服务的审计，也不是推荐。

**为什么必须重复。** 服务器随时可能更换工具，上个月的干净结果说明不了今天。因此**每周**运行一次（每周一 09:00 UTC，由我们自己服务器上的 `warden-feedback.timer` 触发）：

- **定义未变**：不发送任何交易。
- **定义有变但仍干净**：撤销旧评价，发布指向带日期报告的新评价。
- **出现阻断性发现**：撤销我们的评价（该陈述已不成立），并把该代理留给人工决定。不会自动发布任何负面内容：WARDEN 存在误报，对他人代理的公开标记需逐个决定。
- **新的干净代理**：予以评价。
- **端点不响应**：保持原样。
- **我们自己的代理**：从不评价——合约禁止这样做，而换一个钱包去做就是虚假评价。

**使用哪个钱包。** 只用 `0x564bE09d06117A106ECC006a19b67768cBd91666`，它在 WARDEN 的注册文件中声明为 `feedbackWallet`。该钱包只为此存在：不拥有任何代理，只存放少量 ETH 用于 gas，私钥从不离开服务器。

**如何核对。** 每次运行的摘要在 `https://histor.modelmarket.dev/.well-known/erc-8004/feedback/last-run.json`，各份报告就在旁边。每次运行后会收到 Telegram 通知；如果一周没有运行，也会收到提醒。计划外手动运行（先显示计划，确认前不发送任何交易）：

```bash
deploy/erc-8004/warden-feedback            # 显示计划，然后询问
deploy/erc-8004/warden-feedback --status   # 上次运行、钱包余额、下次运行
```

## 来源

- [`deploy/erc-8004/`](../deploy/erc-8004/)：`build.py` 生成注册文件，`register.py` 完成注册（不带 `--send` 时只做 dry run；若钱包付不起包括 Base L1 数据费在内的最坏情况费用，它会拒绝执行；已在 `ids.json` 中的智能体会被跳过；签名在进程内完成，私钥绝不会出现在命令行上），以及 `ids.json`、`registrations.log`。
- 2026-10-01 的[链上日志](onchain-journal.md)条目。
- [ERC-8004 对齐](erc-8004-alignment.md)：本协议的身份、收据与声誉如何映射到 ERC-8004，以及它有意略去了什么。
