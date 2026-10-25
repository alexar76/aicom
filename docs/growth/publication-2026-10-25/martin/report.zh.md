# 五个钱包向一家 x402 卖家付款。这能说明多少需求？

披露：我在 alexar76 生态中维护 HISTOR 和 AIMarket。本分析、相关实现和本文在生成式 AI 的实质性协助下完成。计数和转账核验由确定性代码产生，没有用模型推断钱包身份。其中一笔研究付款来自我们自己，下文会明确标注。

在我们的 x402 服务交付调查之后，[Martin Pisacreta 表示](https://dev.to/alexar76/we-tried-to-buy-one-call-from-100-x402-sellers-most-delivered-almost-nobody-is-buying-2498#comment-3ioef)，textokit 唯一的重复付款者似乎在发送 `normativa-ar` 公开的 inputExample。他问 HISTOR 能否标记行为类似批量探测的钱包。我们实现了本地审计，并检查了全部五个外部付款钱包。真正有用的结果是一张明确保留未知项的证据表。

## 付款总额得到核实

我们于 **2026 年 10 月 25 日 05:16:44 UTC** 获取的[卖家公开账本](https://tienda.textokit.store/receipts.json)包含 **80 笔已结算销售**：发布者将其中 56 笔标为自有钱包付款，另有**来自五个钱包的 24 笔外部销售**，合计 **0.055000 USDC**。钱包归属标记属于来源方的陈述，并非独立核实的身份。

全部 **24 条外部记录**都与 Base 上成功的交易收据吻合：收据包含官方 USDC Transfer 事件，付款地址、收款卖家和金额均与记录完全一致。这验证的是结算，并未验证服务交付，也未验证付款原因。账本持续变化，这些数字仅代表该时间点的快照。

为了解背景，我们扫描了这五个地址在 **2026 年 10 月 11 日 05:23:11 UTC 至 2026 年 10 月 25 日 05:23:11 UTC** 期间的 USDC 转出记录，对应区块 **52453422–53058222**。**605 个连续日志区间**全部成功读取，共返回 **23,254 条原始事件**。其中两条零金额事件未计入行为指标。采集于 05:27:36 UTC 完成。选定的最高区块比节点初始链头落后十二个区块，期间该区块哈希保持稳定。

## 五个钱包表现出的行为

下列地址链接到公开区块浏览器页面。“收款地址”指不同的 USDC 收款地址，不一定对应商家或 x402 服务。转出计数不包含那两条零金额事件。

| 钱包 | textokit 销售笔数 | USDC | 转出笔数 / 收款地址数 | 仅收款一次的地址 | ≤0.01 USDC 的转账 | 审计标签 |
|---|---:|---:|---:|---:|---:|---|
| [0x097e…475a](https://basescan.org/address/0x097e3f339d0b023605e12a6b81e2d6cb7571475a) | 1 | 0.001000 | 5 / 4 | 3 (75.0%) | 1 (20.0%) | `known-probe` |
| [0x7722…5e4a](https://basescan.org/address/0x7722dfae6bbed2fd02dc07455c2f5bf14be25e4a) | 1 | 0.001000 | 1,262 / 1,010 | 909 (90.0%) | 1,051 (83.3%) | `unknown` |
| [0xa1d1…1978](https://basescan.org/address/0xa1d1c0cf717402ff3651aa4873ccf96410b01978) | 1 | 0.001000 | 1,896 / 1,632 | 1,416 (86.8%) | 1,449 (76.4%) | `unknown` |
| [0xc9c7…1670](https://basescan.org/address/0xc9c7b38c0942914fc8ea12063bc92dcd3b581670) | 1 | 0.001000 | 1,979 / 730 | 442 (60.5%) | 1,518 (76.7%) | `unknown` |
| [0xec2a…d034](https://basescan.org/address/0xec2abd3eda89bed90124736e317e847d5fb6d034) | 20 | 0.051000 | 18,110 / 648 | 217 (33.5%) | 16,320 (90.1%) | `probe-like` |

**0x097e…475a 是我们自己的研究探测。** 10 月 20 日那笔 0.001 USDC 的 `x402-ping` 购买，与我们调查中保存的交易一致。该标签只适用于这笔购买，不代表该地址未来的所有行为。

**0xec2a…d034 在 10 月 20 日至 24 日间向十七项服务购买了二十次**，其中包括四次 `normativa-ar`。Martin 表示，该钱包发送的是公开的 inputExample。我们按服务和时间将他的陈述关联到这四条账本记录。请求内容不公开，因此未独立核验每笔交易的输入是否精确匹配。这支持一个注明来源的 `probe-like` 迹象，但不能确定监控者身份。没有这条注释时，严格自动规则给出的标签仍是 `unknown`。

**其余三个钱包呈现广泛的小额付款活动，但意图未知。** 前两个分别向 1,010 和 1,632 个地址付款。我们此前“超过一千个”的描述成立，但“几乎全部”应改为表中的准确比例。第三个涉及 730 个收款地址，重复向相同地址付款的情况更多。它们各自一笔 0.001 USDC 的 textokit 购买，既不能证明正常业务流程，也不能证明监控用途。

## 功能已经实现，标签仍保持审慎

本地且**尚未发布**的 `histor payer-audit` 命令接受公开账本、可选的限定时间范围链上证据，以及关联到具体交易的来源注释。它导出 JSON 和 Markdown，包含输入哈希、观察时间窗、付款者指标、规则、结算引用和覆盖限制。它不需要钱包密钥或生产数据库。采集器只允许五种只读 RPC 方法，从不发送交易或付费服务请求。

初始广泛分布启发式规则要求至少 **50 笔转账**、**50 个收款地址**、**90% 的收款地址只收到一次付款**，以及 **90% 的转账不超过 0.01 USDC**。这些未经校准的阈值在查看采集指标之前就已设定，没有为了贴标签而放宽。即使不满足组合规则，描述性信号仍会保留。

结果是一例已知探测、一例基于来源注释的 probe-like，以及三例未知。**Unknown 不代表已确认的买家。Probe-like 不代表欺诈或无价值使用。** 付费监控本身也可能是真实使用。无论标签如何，全部 **0.055000 USDC 都保留在付款总额中**。

这些观察无法确定 textokit 的自然客户数量、盈利能力、服务交付情况或钱包归属。RPC 核验信任所选 Base 节点，并不是本地验证的链证明。实际改进更为有限：结算、行为和注明来源的陈述有了各自独立的字段，避免把收据数量悄然当成客户数量。

## 公开结算引用

以下 24 笔公开交易与已核验的外部账本记录对应，按付款者分组。金额单位为 USDC。[实时账本](https://tienda.textokit.store/receipts.json)和区块浏览器链接是第一手来源；上文十四天的行为指标对应固定观察时间窗。

### 0x097e3f339d0b023605e12a6b81e2d6cb7571475a

- [0x62c01526…](https://basescan.org/tx/0x62c01526c5beb13cad96634ec80e837e576df496905f1bac8019c6ffa3e358c3) — 0.001000 USDC

### 0x7722dfae6bbed2fd02dc07455c2f5bf14be25e4a

- [0x8d2ccd6a…](https://basescan.org/tx/0x8d2ccd6a3e04a769ecc680f298999dd082a0a2eba936f00a96c0e4ec5902b934) — 0.001000 USDC

### 0xa1d1c0cf717402ff3651aa4873ccf96410b01978

- [0x58ddb2e7…](https://basescan.org/tx/0x58ddb2e77e574ddda75fd74df6f3dbf94e2795e22c36f8a01a506c544ff4ada3) — 0.001000 USDC

### 0xc9c7b38c0942914fc8ea12063bc92dcd3b581670

- [0x3ca4f279…](https://basescan.org/tx/0x3ca4f2791f4f851a574f4abd7cb949e1b05fb00dadeb77b83fb3d0e36a608fb2) — 0.001000 USDC

### 0xec2abd3eda89bed90124736e317e847d5fb6d034

- [0x8c0acafc…](https://basescan.org/tx/0x8c0acafc219977d53b7431c734b1d29b7ef6db90cab5091c7aabe4a0f69a2c0a) — 0.005000 USDC
- [0xef5f2a2c…](https://basescan.org/tx/0xef5f2a2c81b7f6021c73a966eceb453055481a333256a2475a8ac8f011183ffd) — 0.002000 USDC
- [0xcc3231d1…](https://basescan.org/tx/0xcc3231d1e3d39a27838c4e3fbb87db85fb61da5048c49690e5511e844fc83b7e) — 0.005000 USDC
- [0xa7662362…](https://basescan.org/tx/0xa7662362f207a4d0059b32c1204f1171fa7ec7fae9b8567b9ef7cc6cd1f37885) — 0.005000 USDC
- [0xd197a66a…](https://basescan.org/tx/0xd197a66ab0eb069c0acfddfd280dcefe123ec576878d1a924f5407e8f87afda9) — 0.003000 USDC
- [0x68a7bb46…](https://basescan.org/tx/0x68a7bb46a2839d40c1001e1bf1dab036abb849939203e7a4131183581158d8ce) — 0.002000 USDC
- [0x4f712436…](https://basescan.org/tx/0x4f712436cfe5bb039f55d2a536a484b2847e5e29cb86edc97ec6c33552bd9c13) — 0.002000 USDC
- [0x9fe21127…](https://basescan.org/tx/0x9fe21127d045e4398ca6b9d6889241a15c861f7f08d812d7ef66e1846e8cfe04) — 0.002000 USDC
- [0x23207988…](https://basescan.org/tx/0x23207988c28a9bd13e4d2fcd3dffd4e1ae47594077802890ca57fafeb4215bb0) — 0.001000 USDC
- [0x0e65e22c…](https://basescan.org/tx/0x0e65e22cea86dadeeb4bb1736f94bd8f28538011e8024c98eb4d4fc7d25d4121) — 0.001000 USDC
- [0x56eafab5…](https://basescan.org/tx/0x56eafab52aa8a3889b97ba4a013ea3f508cafa934c0acb7958bbd3ec43d78bb6) — 0.001000 USDC
- [0x55049b03…](https://basescan.org/tx/0x55049b036d022dc9970490abbdf079d70bf15f8afdf35f65782472b8f115ef89) — 0.001000 USDC
- [0x6322b987…](https://basescan.org/tx/0x6322b987ed57b94367753a7cfdb4bb1b31bf9efaf183d2ccf0036a057c75959f) — 0.005000 USDC
- [0x415ec0e3…](https://basescan.org/tx/0x415ec0e389ce17a9936de89a28b7ba0fc1717b2f50e756196e074851d712bd9b) — 0.001000 USDC
- [0x4feb47e1…](https://basescan.org/tx/0x4feb47e132ac06e7b5081756cdfb8b6b5436fae1ab62701d04139982b74f0186) — 0.001000 USDC
- [0x9bb91375…](https://basescan.org/tx/0x9bb91375a64c6da4a5fc78e8df817fe86b51487a36c3c98a73a78513edd4d637) — 0.001000 USDC
- [0x3bc01e29…](https://basescan.org/tx/0x3bc01e29b53d187320b18bd1794526c85b8addc456fc0e8e7756fd17fd971ea6) — 0.001000 USDC
- [0x068b1930…](https://basescan.org/tx/0x068b1930266c6235ee31cbfa87690b8ef14c519bba4f1dafd0b36872b836fe95) — 0.002000 USDC
- [0x4700749e…](https://basescan.org/tx/0x4700749eb35c98129e0abc6adb2f9ee66d76dc7bc8ba2e509341f858146d35d6) — 0.005000 USDC
- [0xf93149b9…](https://basescan.org/tx/0xf93149b946d87295924977c2d46f76f163b4d93354bc3fa7aa1f5c04e392736d) — 0.005000 USDC

