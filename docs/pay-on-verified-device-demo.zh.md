# 为物理效果按验证付费——只有电表证明插座确实打开了，代理才付款

> 🌐 [English](pay-on-verified-device-demo.md) · [Русский](pay-on-verified-device-demo.ru.md) · [Español](pay-on-verified-device-demo.es.md) · [Français](pay-on-verified-device-demo.fr.md) · **中文**

Base 主网，2026-10-16，Hub modelmarket.dev（版本 `899ecbdb4`）。一个买方代理支付 **$0.05**，让一个插座打开
60 秒。价格一直托管在 escrow 中，直到 GAIA 的验证器检查了已签名的指令以及前后的电表读数。一小时内无人上诉，
于是 Hub 在链上扣款 $0.05，买方从 $1.00 的存款中拿回 **$0.95**。第一次演示（代理雇用两个陌生人分解一个数）
见[这里](pay-on-verified-demo.zh.md)；设备控制的原理见 [GAIA 文档](https://github.com/alexar76/gaia/blob/main/docs/i18n/ACTUATION.zh.md)。

## 谁是谁——请先读这里

- **卖方是我们的。** GAIA（`gaia.gateway`，发布者 `gaia`）由 modelmarket.dev 的运营方运行。
- **插座是模拟的。** `plug-sim-01` 是一台只存在于软件中的 1500 W 电暖器，每个回答都会注明（`"simulated": true`）。
  这证明的是资金和验证的路径，而不是硬件。真实硬件是带电能计量芯片的 Tasmota 插座
  （[ACTUATION](https://github.com/alexar76/gaia/blob/main/docs/i18n/ACTUATION.zh.md)）。
- **买方钱包是独立的，但由我们出资：** `0x097e3F339D0b023605e12A6B81E2d6Cb7571475a`，与第一次演示相同。为了这次运行，
  所有者从运营方钱包 `0x1218…Ad0a` 向它充值了 0.50 USDC。这证明的是机制，而不是第三方需求。
- **裁判是卖方自己的验证器。** Hub 把 `gaia.actuate@v1` 交给 `gaia.verify@v1`——GAIA 的精确检查——而不是交给它的
  LLM 评审团。于是 GAIA 既是卖方也是裁判。之所以可以接受，只是因为这项检查是对已签名证据的确定性检查，任何人都
  可以重跑，并且买方可以把“通过”上诉到 Hub 的上诉法庭，那是另一个验证器。见“这不能说明什么”。

## 事先必须改变什么，以及原因

这项能力是在同一天早上开始出售的。在它和一次付费、经过验证的调用之间，隔着五件事。

| # | 问题 | 我们做了什么 | 原因 |
|---|---|---|---|
| 1 | Hub 对所有能力只有一个验证器：Metis 的 LLM 评审团。 | 按能力设置验证器路由，`AIMARKET_VERIFY_ROUTES`（Hub `71be57610`）。`gaia.actuate@v1` → `gaia.verify@v1`；其余一切仍交给 Metis。 | 语言模型无法检查 Ed25519 签名或电表的物理规律，评审团还可能弃权，让诚实的效果得不到付款。不可用的路由会**拒绝**验证，绝不会悄悄退回到 Metis。 |
| 2 | 生产环境中 GAIA 的验证端点对所有人都返回 503：compose 文件从未把 `GAIA_VERIFY_TOKEN` 传入容器。 | 在 GAIA 的主机上生成令牌并传入容器（`c718f810e`）；Hub 从路由指定的环境变量中读取它，作为 Bearer 发送。 | 一个“通过”的判定会推进 GAIA 的防重放标记，因此开放的验证端点可能让所有待结算的款项失败。只有 Hub 可以调用它。 |
| 3 | modelmarket.dev 运行的是一个手工打过补丁的旧版本，没有路由代码。 | 对线上容器中的每个文件计算哈希并与 git 比较：没有只存在于服务器上的修复。然后用 `deploy_hub_rebuild.sh` 从 main 完整发布，并保留旧容器以便回滚。 | 代码必须在真正运行的东西里，而一次发布不能悄悄丢掉只存在于服务器上的补丁。 |
| 4 | `gaia.actuate@v1` 只作为联邦能力列出，而按验证付费只为 Hub 自己执行的能力托管资金。 | 一个本地条目：发布者 `gaia`（运营方自有发布者），固定 GAIA 的签名密钥，要求响应签名。 | 没有它，`verify` 块会被跳过，什么也不会被托管。 |
| 5 | 支付金丝雀报警：“付费工作被免费提供”。 | 那是 Independent 自己的免费试用，发生在 Hub 只做中介的对等节点上。金丝雀现在知道 Hub 为谁销售（`899ecbdb4`）。 | 关于钱的误报会让人学会忽略真正的警报。 |

在花任何钱之前，先用一次免费的沙盒试用证明了路由：插座消耗 1491 W，判定为 `passed`，签名为
`verifier: gaia.verify@v1`（追踪 `gaia_c12c4efa209ea762`）。没有资金流动。

## 付费运行，逐步说明

| # | 步骤 | 发生了什么 |
|---|---|---|
| 1 | 任务和上限 | “把 plug-sim-01 打开 60 秒。”上限：一笔 $1.00 的托管存款，合约不允许代理超出。 |
| 2 | 找到卖方 | `GET /ai-market/v2/search` 返回 `gaia.actuate@v1`、`gaia.gateway`、$0.05、发布者 `gaia`。买方只选**本地**条目，因为联邦条目从不经过验证。 |
| 3 | 带证据的工作 | GAIA 签署指令（`act_0aec0a640ed36476`），先读电表，再打开，然后再读一次。预期 20 秒内 ≥ 1000 W；**实测 1506.2 W**。插座在 10:53:15 UTC 自行关闭。整个调用耗时 15.5 秒。 |
| 4 | 判定 | `gaia.verify@v1`：**passed**，得分 1.0，Hub 的门槛为 0.7（追踪 `gaia_e34da88c0a648c51`）。在上诉窗口于 11:52:29 UTC 关闭之前它是临时的；无人上诉，于是成为最终判定。 |
| 5 | 资金 | Hub 的签名者在 12:03 UTC 于链上扣款 **$0.05**。买方请求关闭，等过一小时的结算窗口后完成结算：**$0.05 给 Hub，$0.95 退回**。 |

买方成本：**$0.05**，外加约 0.000007 ETH 的 gas。余额 1.094148 → 1.044148 USDC。
运行日志：[`pov-demo/runs/2026-10-16T105204Z.json`](../pov-demo/runs/2026-10-16T105204Z.json)。

## 交易（Base 主网）

合约：托管 AIMarketEscrowV2 [`0xa4cb6ef7…1B2Eb`](https://basescan.org/address/0xa4cb6ef73B982B847fB06Ec75540d05D0311B2Eb)，
由 Hub 的签名者 [`0xBE0bBE44…C5f1`](https://basescan.org/address/0xBE0bBE44cceCfEb048dd53f601C37525a3D6C5f1) 扣款，
USDC [`0x833589fC…02913`](https://basescan.org/address/0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913)。
托管通道 `0x8c89c278…e8f3`。

| 步骤 | 谁 | 区块 | 交易 |
|---|---|---|---|
| `USDC.approve(escrow, 1.00)` | 买方 | 52679290 | [`0xf765fe99…b52d`](https://basescan.org/tx/0xf765fe99e6570fb7590abb4f9a492b8544d52f96185eb8990931215e3e01b52d) |
| `openChannel` $1.00 | 买方 | 52679291 | [`0x6ed3cdb4…19c8`](https://basescan.org/tx/0x6ed3cdb421b1a1619d8a695f857feb34dceac398f27cf9fabd678f9e7c1b19c8) |
| `gaia.verify@v1` 判定 **passed**，上诉窗口后成为最终判定 | — | — | — |
| `debitChannel` $0.05 | Hub 签名者 | 52681416 | [`0x6973d111…fe10`](https://basescan.org/tx/0x6973d11160f4f58951f42c8ee65ba3639d2b376b02e037e5747663ea7d28fe10) |
| `requestClose` | 买方 | 52681422 | [`0xbfb451bd…52cf`](https://basescan.org/tx/0xbfb451bd33db3af0db7f3258c6f0fab56ded47204e9c4f9a28540df575db52cf) |
| `settleChannel`：$0.05 给 Hub，**$0.95 退回** | 买方 | 52683232 | [`0x1e2b0aa7…9f25`](https://basescan.org/tx/0x1e2b0aa794924a373635dc651e20afd6a1baa2be5e5f3d80724fbff1fcef9f25) |

## 途中出了什么问题

1. **信任预言机无法访问。** 那天 Hub 主机与预言机主机之间的链路质量下降：LUMEN 要么 4 到 35 秒才响应，要么完全不
   响应。对于没有已存信任值的发布者，Hub 会询问 LUMEN，因此前五次免费试用都被以“trust oracle unavailable”拒绝，
   没有任何扣款。第六次得到了响应，Hub 为 `gaia` 存下 0.70 的信任值，付费运行使用的就是这个已存的值。网络问题本身
   尚未解决。
2. **太短，不够安全。** 那次通过信任检查的试用请求 5 秒，GAIA 拒绝了：`plug-sim-01` 只接受 10 到 900 秒，以免任何
   东西无限制地保持打开。没有扣款。
3. **第一次提交扣款失败**，15 分钟后的下一轮清扫成功提交。已签名的授权比上诉窗口多活两个小时，正是为了让重试依然
   有效。
4. **发布本身也有陷阱。** Hub 的发布检查要求已发布的 pipeline 客户端与 Hub 版本一致。当时提供的客户端是 3.15.1，
   而 Hub 是 3.15.28，发布本会自行回滚。于是先重新构建了客户端。

## 这不能说明什么

- 真实硬件：插座是模拟的。Tasmota 插座签署的是其电表所报告的内容——这是对报告的保管，而不是证明硬件不会说谎。
- 独立的裁判：GAIA 既出售也验证。证据是用 GAIA 持有的密钥签名的，因此任何验证器——无论 GAIA 还是 LLM——都发现不了
  持有密钥者伪造的证据。买方的保护在于任何人都可以重跑检查（`POST /v1/verify`，或用证据包调用 `gaia.verify@v1`），
  以及上诉法庭。
- 第三方需求：卖方和买方的钱都是我们的。

## 自己运行

```bash
python3 pov-demo/buyer.py --key-file <你的钱包 json> --task actuate --duration 60 --yes
```

需要在 Base 上准备 $1.00 USDC 和约 0.00005 ETH。加上一小时的上诉窗口和一小时的结算窗口，整个运行大约需要两个小时；
除 $0.05 外全部退回。
