# 声明你的生态，让它正确显示

> ## ⚠️ 免责声明 —— 请先读这一段
>
> **监视器和对等 hub 显示的，正是你的 hub 所声明的内容。仅此而已。**
>
> 没有任何监视器会去猜测你服务的公开地址，也不应该猜：猜测意味着扫描你的主机寻找开放端口，
> 然后把凡是有响应的都公布出去。如果你声明的是 `http://memory-market:8810`，那么任何人打开
> 任何一张地图 —— 你自己的，或者别的运营者的 —— 看到的都会是 `http://memory-market:8810`：
> 一个全世界只在一台机器上能解析、对其他所有人毫无用处的地址。
>
> **一个没有声明公开地址的 hub，不是「配置错了、别人能替你修好」。它是唯一知道答案的一方。**

## 节点是从哪来的（这不是发现机制）

监视器并不会去「找到」你的提供方。它读取 `/.well-known/ai-market.json` 并解开
`ecosystem.nodes` —— 仅此而已。不扫端口，不试探子域名，不猜：

```python
# alien-monitor/backend/hub_discovery.py
ecosystem = well_known.get("ecosystem")
declared_nodes = ecosystem.get("nodes") if isinstance(ecosystem, dict) else []
```

所以链条是：**能力发布在你的 hub 上 → 你的 hub 据此构建 `ecosystem.nodes` → hub 提供它 →
监视器把它画出来。** 节点之所以存在，就是因为它注册在 hub 上，仅此一个原因。子域名不是找到它
的方式；子域名只是它的**地址**恰好长成那样 —— 前提是你把服务发布在那个名字下。

## 会出什么问题，以及为什么看起来像地图的 bug

提供方是用 **你的 hub** 调用它时所用的地址注册的。在单机部署上，那个地址就是容器名：

```
http://memory-market:8810
http://truth-layer:8811
http://provenance-ledger:8812
```

随后你的 hub 会把它们发布在 `/.well-known/ai-market.json` 的 `ecosystem.nodes` 里，而监视器
画出来的正是这些。节点出现了，名字也对，能力数量也报了 —— 但它的地址谁都打不开。看到的人
很自然会认为地图坏了。地图报告得很忠实。

2026-09-07 在 `hub.attestedmemory.net` 上实测：三个提供方，三个容器名，三张无法使用的卡片。
而在 `independentai.network/hub` 上，同样这三个字段里放的是
`https://kova.independentai.network`、`https://aegis.independentai.network` 和一个公开的
invoke URL —— 相同的代码、相同的监视器、正确的结果。差别在配置，而在此之前根本没有可以放它的
变量：名字可以设（`AIMARKET_ECOSYSTEM_LABELS`），地址不行。

## 三个变量

三个都要设。它们回答三个不同的问题。

| 变量 | 它回答的问题 | 示例 |
|---|---|---|
| `AIMARKET_HUB_URL` | **这个 hub** 在哪里可访问？ | `https://hub.example.net` |
| `AIMARKET_ECOSYSTEM_LABELS` | 我的提供方**叫什么**？ | `memory-market:Memory Market,truth-layer:Truth Layer` |
| `AIMARKET_ECOSYSTEM_URLS` | 我的提供方**在哪里可访问**？ | `memory-market=https://memory.example.net,truth-layer=https://truth.example.net` |

漏掉就会浪费时间的细节：

* `AIMARKET_ECOSYSTEM_LABELS` 用 `:` 分隔 —— 值是名字。
* `AIMARKET_ECOSYSTEM_URLS` 用 **`=`** 分隔 —— 值是 URL，本身已经含冒号。
* 条目以 **`publisher_id`** 为键，即该能力发布时所用的 id：不是显示名，也不是 product id。
  `GET /ai-market/v2/manifest` 里能看到。
* 凡不是 `http://…` 或 `https://…` 的都会被忽略，而不是被发布。格式错误的条目会保留推导出的
  地址，不会把节点清空。
* 声明的地址**优先于**任何能从 invoke URL 推导出的地址。这正是重点：你的 hub 从一条路径拨号
  给提供方，而世界从另一条路径找到它。
* `AIMARKET_HUB_URL` 必须是你的**公开**地址。一个宣告 `http://localhost:9084` 的 hub，等于在
  告诉每个对等方去拨打它自己的回环地址。

## 如何部署

1. **先把服务发布出去。** 声明是一个承诺；先让它成真。每个提供方一个子域名，是本生态采用的
   做法（`kova.`、`aegis.`、`charon.`）：

   * 为每个名字添加一条 DNS `A` 记录，指向该主机；
   * 为每个名字添加一个 nginx `server` 块，反代到本地端口；
   * 签发证书（`certbot --nginx -d memory.example.net …`）—— HTTP-01 要求 DNS **先**能解析，
     所以顺序就是这样。

   在单一域名下用路径（`https://example.net/memory`）也可以，且不需要新的 DNS 和证书，但服务
   必须能在前缀下被访问 —— 这类服务大多在根路径提供 `/v1/…`，并不支持。

2. **设置变量**，位置取决于你的部署把环境放在哪里（`.env`、compose 的 `environment:` 块、
   systemd 的 `EnvironmentFile`）。

3. **重启 hub。** 这些变量在构建 well-known 文档时读取。

4. **去验证** —— 不要想当然：

   ```bash
   curl -s https://hub.example.net/.well-known/ai-market.json \
     | python3 -c 'import json,sys; d=json.load(sys.stdin); \
       print([(n["name"], n["url"]) for n in (d.get("ecosystem") or {}).get("nodes") or []])'
   ```

   这个列表里的每个地址，都必须能**从另一台机器**粘进浏览器打开。然后在监视器上打开该节点：
   声明过的公开地址会渲染成可点击的链接；内部地址会渲染成灰色文字并标注
   **internal address**，永远不会被当作链接提供。

## 检查清单

- [ ] 每个提供方服务都能在公开地址上响应
- [ ] `AIMARKET_HUB_URL` 是该 hub 的公开地址，不是回环地址
- [ ] `AIMARKET_ECOSYSTEM_LABELS` 为每个提供方命名
- [ ] `AIMARKET_ECOSYSTEM_URLS` 为每个提供方给出地址，分隔符是 `=`
- [ ] 键用的是取自 manifest 的 `publisher_id`
- [ ] well-known 文档已从**另一台**机器验证过
- [ ] 监视器上的节点卡片显示的是链接，而不是「internal address」

## 相关

* [federation-admission.zh.md](./federation-admission.zh.md) —— 对等 hub 如何被接纳。
* [federation-peer-keys.zh.md](./federation-peer-keys.zh.md) —— 它的密钥如何被固定。
* [who-gets-a-sphere.zh.md](./who-gets-a-sphere.zh.md) —— 为什么你的节点可能不出现在别人的地图上，以及改变它的三种方式。
