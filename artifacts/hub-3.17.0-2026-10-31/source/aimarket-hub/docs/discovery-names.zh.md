# Discovery 名称 — 同一份文档的两种写法

> **English:** [discovery-names.md](./discovery-names.md) · **Русский:** [discovery-names.ru.md](./discovery-names.ru.md) · **Español:** [discovery-names.es.md](./discovery-names.es.md) · **Français:** [discovery-names.fr.md](./discovery-names.fr.md)
>
> 代码：[`discovery_names.py`](../aimarket_hub/discovery_names.py) · [`hub_routes/wellknown.py`](../aimarket_hub/hub_routes/wellknown.py) · [`crawler.py`](../aimarket_hub/crawler.py) · 草案：[`aimarket-protocol/ietf/`](https://github.com/alexar76/aimarket-protocol/tree/main/ietf)

自 2026-10-30 起，Hub 以两个名称提供 discovery 文档，以两个名称发送 crawler 请求头，并接受其中任一个。
没有任何东西被重命名或下线：网络中的每个 peer 仍在读取旧名称，新名称只是正在审议中的提案。

## 为什么

`aimarket-protocol/ietf/` 中的两份 Internet-Draft 面向 IETF DAWN 工作组描述了本 Hub 的 discovery 与联邦机制。
作为标准提案的文档不能在 well-known URI 中携带某个产品的品牌，而请求头的 `X-` 前缀也已废弃（RFC 6648）。
因此草案使用 `/.well-known/agent-marketplace` 与 `Agent-Marketplace-Crawler`，声称实现草案的 Hub 必须提供这些名称，
同时不能破坏任何现有 peer。

## Hub 做了什么

| | 旧名称（线上契约） | 草案（提案） |
|---|---|---|
| Discovery 文档 | `GET`/`HEAD /.well-known/ai-market.json` | `GET`/`HEAD /.well-known/agent-marketplace` |
| 目录位置 | `manifest_url` | `catalogue_url`（同一 URL） |
| 签名配置 | 隐含 | `signature_profile: "ed25519-pipe-2"` |
| 已准入的 peer | `peers`：带 `url`、`name`、`trust_score` 等的对象 | `peers`：discovery 文档的 URI |
| Crawler 自报身份 | `X-AIMarket-Crawler: <hub url>` | `Agent-Marketplace-Crawler: <hub url>` |

- **提供。** 草案文档由旧文档生成，因此密钥、目录与计数永远不会不一致。它还带有 `manifest_url` 和
  `legacy_discovery_url`，供只认识旧名称的读者使用。`peers` 列出本 Hub 对每个已准入 peer 实际读取的 discovery URI：
  只提供旧路径的 peer 用旧路径，peer 宣布草案路径后用草案路径。处于 pending 状态的 peer 不会出现在任何一份文档里。
- **发送。** Crawler 每次抓取都以相同的值发送两个请求头。
- **接受。** 两条路由都读取两个请求头。两者同时到达时以旧值为准——peer 一直是以它来识别的。其余不变：在请求路径之外记录，
  做语法校验，任何抓取前先做 SSRF 检查，开放联邦下以 *pending* 准入，绝不仅凭请求头给予信任。
- **读取。** 发布草案形态（`catalogue_url`、`peers` 为 URI）的 peer 会在校验、抓取与评估之前归一化为旧形态，
  因此与其他 peer 一样被索引。以草案路径 URI 列出的 peer 会按该路径访问，而不是按它可能并不提供的旧路径。

签名目录在两个名称下逐字节相同：规范字符串保留了 `tools_hash` 这个键名，因此对一方读者有效的签名对另一方同样有效。

## 检查一个 Hub

```bash
curl -s https://modelmarket.dev/.well-known/agent-marketplace | jq '{catalogue_url, signature_profile, peers}'
curl -sI https://modelmarket.dev/.well-known/agent-marketplace | head -1          # HEAD → 200
python3 aimarket-protocol/conformance/run.py --hub https://modelmarket.dev          # 含草案检查
```

一致性检查工具在该路径有响应时记录草案检查，在只提供旧名称的 Hub 上则**跳过**它们。草案是提案；旧路径才是契约。
