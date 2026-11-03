# 谁算"我们"：SELF 与 EXT 流量

[English](traffic-classes.md) · [Русский](traffic-classes.ru.md) · [Español](traffic-classes.es.md) · [Français](traffic-classes.fr.md) · [中文](traffic-classes.zh.md)

枢纽记录的每一次调用，要么是 **SELF**，要么是 **EXT**。类别出现在以下位置：
- `/ai-market/v2/stats/live`：每个事件的 `traffic_class` 字段；
- 首页：`ext` / `self` 标签、筛选器和滚动条；
- 累计计数器 `external_invocations` 与 `operator_self_invocations`。

EXT 是你对外引用的需求数字，所以它不能包含你自己的流量，也不能漏掉任何一个真实客户。

## 规则

- **SELF** 是枢纽本身，以及绑定在它上面、属于**它自有生态**的组件：你为这个枢纽运行的服务，例如自己的 desk、监控、金丝雀和自营提供方。
- **EXT** 是其他所有人：
  - 买家与代理；
  - 其他生态；
  - 自行部署这份开源代码的任何人；
  - **通过付费通道接入的外部服务**，即使它们运行在你的硬件上。为玩家购买能力的游戏是客户，不是生态的一部分。

不做任何配置时，枢纽只认识自己：管理员冒烟测试、`local` 和枢纽自己的 URL 是 SELF，其余全部是 EXT。生态的其余部分写在一个文件里：`ecosystem.json`。

## 由什么决定类别

| 依据 | 适用范围 | 判定时机 | 结果 |
|---|---|---|---|
| 枢纽本身：管理员 Bearer 冒烟测试、`local`、枢纽自己的 URL | 任意调用 | 读取时 | 始终 SELF |
| **转发**的调用。另一个枢纽把买家路由到这里：它会发送 `X-AIMarket-Routing-Hub` / `X-AIMarket-Buyer`，或 `hub-fed-…` 试用访客。另一个枢纽购买的 seller operation 也属于此类 | 任意调用 | 写入时 | 在本枢纽永不为 SELF |
| `external.networks`、`external.wallets` | 任意调用 | 写入时 | EXT，无论其他条件是否匹配 |
| `external.accounts` | 由信用账户扣费的调用 | 读取时 | EXT，无论其他条件是否匹配 |
| `self.accounts` | 由信用账户扣费的调用：`X-API-Key`、授权（mandate）、任务额度 | 读取时 | SELF |
| `self.wallets` | x402 调用：经链上验证的付款钱包（支付通道 id 来自请求头，不能为任何事作保） | 写入时 | SELF |
| `self.networks` | 仅限**既无付款方也无试用访客**的调用：枢纽的 MCP 网关、无身份调用 | 写入时 | SELF |

表中各行按顺序检查，第一个匹配项生效。因此 `external` 总是优先于 `self`，转发的调用永远不是 SELF。唯一的例外：经链上验证的 x402 付款方无论从哪里到达都是依据，所以 `self.wallets` / `external.wallets` 在转发中同样适用。来自不在 `AIMARKET_TRUSTED_PROXIES` 中的对端、却带有 `X-Forwarded-For`、`Forwarded` 或 `X-Real-IP` 的请求，是自报身份的转发者，按转发处理。

**"读取时"**意味着修改文件会重新归类历史。把一个账户从 `self.accounts` 移除，它过去的调用会在下次加载页面时变回 EXT。

**"写入时"**意味着依据本身（调用方地址、付款钱包）不会被保存。枢纽在写入该行时判断一次，只保留结论。今天新增的服务器或钱包，只影响从现在起的调用。但每一行会记住是**哪一条**条目为它作保，所以从文件中删掉错误的条目，这些行会重新变回 EXT。

## 为什么地址永远不能为付费调用作保

枢纽自身的管道会让你的服务器成为大量他人流量的直接调用方：

- 对等枢纽路由陌生人的购买时，请求来自**那个枢纽的地址**；
- 在另一个枢纽购买的付费 Studio 步骤，来自**购买方枢纽**；
- 用陌生人额度支付的分包子调用，由**你的提供方主机**发出；
- 工厂执行器为网页访客运行免费流水线，请求来自**工厂主机**。

如果地址能把这些调用变成 SELF，真实需求就会从 EXT 中消失。所以付费调用按**谁付的钱**（账户或钱包）判断，永远不看它从哪里来。地址规则只覆盖既没有付款方、也没有试用访客的调用：从服务器发来的试用访客几乎总是转发。

转发的调用由完成路由的那个枢纽归类：只有它看到了真实买家。这样每个枢纽自己的数据流都保持如实。汇总多个枢纽时，请去掉 `traffic_basis: "forwarded"` 的行，以免一次购买被计算两次。

## 配置文件

**位置：**
1. 若设置了 `AIMARKET_ECOSYSTEM_FILE`，使用它；
2. 否则使用枢纽数据库（`AIMARKET_DB_PATH`）旁边的 `ecosystem.json`。在 Docker 镜像中即 `/app/data/ecosystem.json`，位于数据卷上；
3. 否则使用 `./data/ecosystem.json`。

请把它留在服务器上。它列出了你的服务器和账户，绝不应进入公开仓库。仓库提供 [`examples/ecosystem.example.json`](../examples/ecosystem.example.json)，其中只使用文档专用地址段。

**格式。** JSON。每个条目是一个字符串，或对象 `{"value": "...", "note": "为什么放在这里"}`。枢纽忽略 `note`，它是写给下一个编辑文件的人看的。

```json
{
  "version": 1,
  "self": {
    "accounts": [{"value": "acct_0123456789abcdef", "note": "演示 desk"}],
    "networks": [{"value": "198.51.100.7", "note": "desk 与监控主机"}, "2001:db8:7::7"],
    "wallets":  [{"value": "0x1111111111111111111111111111111111111111", "note": "测试买家"}]
  },
  "external": {
    "accounts": [{"value": "acct_aaaaaaaaaaaaaaaa", "note": "我们托管的游戏：是客户"}],
    "networks": ["203.0.113.80"],
    "wallets":  []
  }
}
```

**校验：**

- **结构错误会拒绝整个文件**：未知键、类型错误、`version` 不是 `1`。否则一个拼错的 `"netwroks"` 会悄无声息地丢掉整张列表。
- **单个错误值**会被跳过并报告，其余照常生效。
- **枢纽会拒绝**从枢纽内部看永远不可能是你服务器的网络：
  - 回环、`0.0.0.0/8` 与 `::`；
  - RFC 1918 和 CGNAT `100.64.0.0/10`；
  - 链路本地、IPv6 唯一本地地址和组播；
  - IPv4 翻译前缀（NAT64 `64:ff9b::/96`、6to4 `2002::/16`）；
  - 比 IPv4 `/24` 或 IPv6 `/56` 更宽的范围：请列出你的服务器，而不是托管商的整段地址；
  - 任何包含 `AIMARKET_TRUSTED_PROXIES` 中地址的网络。

  MCP 网关、进程内桥接、docker 网关和代理恰恰从这些地址到达，携带的都是他人的调用。
- IPv4 映射的 IPv6（`::ffff:198.51.100.7`）按对应的 IPv4 处理。
- 同时出现在两个列表中的条目按外部计算。

**修改无需重启即生效。** 枢纽在下一次调用时就会发现文件已修改。如果某次编辑使文件无效，**最后一个有效版本继续生效**：`status` 变为 `invalid`，错误写入日志。一个笔误不应把你自己的流量翻成 EXT。删除文件则恢复默认规则。

**保存前先检查：**

```bash
python -m aimarket_hub.ecosystem check /path/to/ecosystem.json
# 退出码 0 正常，2 部分条目被拒，1 文件被拒或不存在
```

**在 Docker 部署的枢纽上**，把文件放进数据卷，让枢纽用户（uid 10001）可读，并在枢纽自己的环境里检查：

```bash
docker cp ecosystem.json modelmarket-hub:/app/data/ecosystem.json
docker exec -u 0 modelmarket-hub chown 10001:10001 /app/data/ecosystem.json
docker exec modelmarket-hub python -m aimarket_hub.ecosystem check
curl -s https://your-hub.example/ai-market/v2/stats/live | jq '.summary.traffic_policy'   # status 为 ok，loaded_at 已更新
```

不要单独挂载这个文件（单文件 bind mount）：以重命名方式保存的编辑器会让容器继续使用旧副本。备份数据卷时要包含它。最后一个有效版本只能在无效编辑后保持到下一次重启。由于修改账户会重新归类历史，`external_invocations` 不是单调的：按差值统计的仪表盘会在注册表变化时看到跳变。

`AIMARKET_OPERATOR_ACCOUNTS`（逗号分隔的账户 id）仍然有效，会并入 `self.accounts`；如果同时存在文件，枢纽会在日志中警告——请只在一处维护列表。

## 公开哪些内容

- **每个事件**都带有 `traffic_class`（`operator_self` 或 `external`）和说明原因的 `traffic_basis`：`operator`、`account`、`address`、`wallet`、`forwarded`、`override`（`external` 条目）或 `null`（普通外部调用）。
- **用途**：事件可带有 `purpose`，即调用方在 invoke 中发送的简短标签（`"purpose": "feed"`），用来说明调用目的。这是调用方自己的标注，枢纽不核实。只保留符合 `[a-z][a-z0-9-]{0,23}` 的值，其他值会被丢弃，但调用不会被拒绝。为空表示调用方未发送。
- **摘要中**的 `summary.traffic_policy` 公开：
  - 各列表的条目数量；
  - 规则来源（`default`、`env`、`file`、`file+env`）；
  - 文件是否加载成功（`absent`、`ok`、`partial`、`invalid`）及加载时间。
- **永不公开**：地址、账户 id、钱包和文件路径。存储的结论列 `caller_class` 不会离开枢纽。

```bash
curl -s https://your-hub.example/ai-market/v2/stats/live | jq '.summary.traffic_policy'
curl -s https://your-hub.example/ai-market/v2/stats/live | jq '[.events[] | {capability_id, purpose, traffic_class, traffic_basis}]'
```

## 把某样东西列为"自己的"之前

- **服务器**：只有当它自己的进程作为本枢纽生态的一部分调用本枢纽时才列入。绝不要列入转发他人请求的主机：另一个枢纽、网关、工厂执行器、运行第三方代码的租户平台或沙箱、自托管的 `aimarket-mcp`。这类服务器要么不列，要么放进 `external.networks`。
- **IPv6**：双栈服务器要同时列出 IPv4 和 IPv6。
- **不要列入枢纽自身的地址**：如果枢纽所在主机上还运行着转发他人请求的程序，就不要列入该主机的公网地址，否则枢纽访问自己公网 URL 的调用会变成 SELF。
- **受信代理**：`AIMARKET_TRUSTED_PROXIES` 必须指向你真实的反向代理（见[生产部署](production-deployment.zh.md)）。否则每个调用方看起来都像代理，地址规则什么也匹配不到。地址的可信度取决于这张列表：任何*从*受信代理地址访问枢纽的进程（例如经 docker 网关访问的主机进程）都可以随意声明客户端地址。列表中只保留反向代理；如果不受信任的代码能以这种方式访问枢纽，就不要使用 `self.networks`。
- **账户**：列入你自己的组件用来消费的账户。绝不要列入你*为*客户开的账户：在关闭注册的枢纽上，所有账户都由运营方开出，客户的也一样。通过授权（mandate）或任务额度支付的调用带的是**出资**账户，因此绝不要把已列入账户的授权或额度交给外部提供方。也不要列入其他枢纽在本枢纽使用的账户：它的密钥承载着他人的购买。
- **钱包**：列入为你的测试和生态流量付款的钱包。绝不要列入代他人付款的枢纽、中继或对等通道钱包。

## 历史数据

3.15.0 之前记录的行没有保存的结论，只按标签归类；修改账户会像其他数据一样重新归类它们。地址和钱包规则只作用于添加条目之后记录的调用。
