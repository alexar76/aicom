---
title: "Five Wallets Paid an x402 Seller. What Can We Say About Demand?"
published: true
description: "A five-wallet audit verifies 24 settlements while separating payment evidence, behavioral signals and unknown customer intent."
tags: mcp, blockchain, opensource, ai
---

**AI disclosure:** AI agents prepared this analysis, its implementation and this article under the project owner’s direction. I maintain HISTOR and AIMarket in the alexar76 ecosystem. Deterministic code produced the counts and transfer checks; no model inferred wallet identities. One research payment was ours, and it is identified below.

After our x402 delivery survey, [Martin Pisacreta reported](https://dev.to/alexar76/we-tried-to-buy-one-call-from-100-x402-sellers-most-delivered-almost-nobody-is-buying-2498#comment-3ioef) that textokit’s only repeat payer appeared to send the published `normativa-ar` inputExample. He asked whether HISTOR could flag wallets whose activity resembled a sweep. We implemented a local audit and checked all five external payers. The useful result is an evidence table with explicit unknowns.

## The payment totals hold up

The [public seller ledger](https://tienda.textokit.store/receipts.json), retrieved on **25 October 2026 at 05:16:44 UTC**, contained **80 settled sales**: 56 marked as own-wallet sales by the publisher and **24 external sales from five wallets**, totaling **0.055000 USDC**. Publisher ownership flags are source claims, not independently authenticated identities.

All **24 external entries** matched successful Base transaction receipts containing an official USDC Transfer from the stated payer to the seller for the exact stated amount. That verifies settlement. It does not verify service delivery or why somebody paid. The ledger is live; these are snapshot figures.

For context, we scanned outgoing USDC transfers from these five addresses over **11 October 2026, 05:23:11 UTC, through 25 October 2026, 05:23:11 UTC**: blocks **52453422–53058222**. All **605 consecutive log ranges** completed successfully, returning **23,254 raw events**. Two zero-value events were excluded from behavioral metrics. Collection finished at 05:27:36 UTC. The selected head was twelve blocks behind the initial node head, and its hash remained stable.

## What the five wallets show

Addresses below link to their public explorer pages. “Recipients” means distinct USDC recipient addresses, which are not necessarily merchants or x402 services. The outgoing-transfer counts exclude the two zero-value events.

| Wallet | textokit sales | USDC | Outgoing transfers / recipients | Recipients paid once | Transfers ≤0.01 USDC | Audit label |
|---|---:|---:|---:|---:|---:|---|
| [0x097e…475a](https://basescan.org/address/0x097e3f339d0b023605e12a6b81e2d6cb7571475a) | 1 | 0.001000 | 5 / 4 | 3 (75.0%) | 1 (20.0%) | `known-probe` |
| [0x7722…5e4a](https://basescan.org/address/0x7722dfae6bbed2fd02dc07455c2f5bf14be25e4a) | 1 | 0.001000 | 1,262 / 1,010 | 909 (90.0%) | 1,051 (83.3%) | `unknown` |
| [0xa1d1…1978](https://basescan.org/address/0xa1d1c0cf717402ff3651aa4873ccf96410b01978) | 1 | 0.001000 | 1,896 / 1,632 | 1,416 (86.8%) | 1,449 (76.4%) | `unknown` |
| [0xc9c7…1670](https://basescan.org/address/0xc9c7b38c0942914fc8ea12063bc92dcd3b581670) | 1 | 0.001000 | 1,979 / 730 | 442 (60.5%) | 1,518 (76.7%) | `unknown` |
| [0xec2a…d034](https://basescan.org/address/0xec2abd3eda89bed90124736e317e847d5fb6d034) | 20 | 0.051000 | 18,110 / 648 | 217 (33.5%) | 16,320 (90.1%) | `probe-like` |

**0x097e…475a was our research probe.** Its single 0.001 USDC `x402-ping` purchase on 20 October matches our recorded survey transaction. The label applies to that purchase, not every future action by the address.

**0xec2a…d034 made twenty purchases across seventeen services**, including four `normativa-ar` purchases, between 20 and 24 October. Martin reports that it sends the published inputExample. We associated his statement with those four ledger rows by service and time. Their request payloads are not public, so exact per-transaction input matches were not independently verified. This supports a source-annotated `probe-like` indication; it does not establish a monitor’s identity. Without that annotation, the strict automatic label is `unknown`.

**The remaining three wallets show broad small-payment activity, with unknown intent.** The first two reached 1,010 and 1,632 recipients. Our earlier “more than a thousand” description holds, but “nearly all” should be replaced by the exact fractions above. The third reached 730 recipients and repeated recipients more often. Their individual 0.001 USDC textokit purchases establish neither an organic workflow nor monitoring.

## The function exists; the labels remain cautious

The local, **unreleased** `histor payer-audit` command accepts public receipts, optional bounded chain evidence and transaction-scoped source annotations. It exports JSON and Markdown containing input hashes, the observation window, payer metrics, policy, settlement references and coverage limits. It needs no wallet keys or production database. Its collector allows five read RPC methods and never sends transactions or paid service requests.

The initial broad-pattern heuristic requires at least **50 transfers**, **50 recipients**, **90% singleton recipients** and **90% transfers of at most 0.01 USDC**. These uncalibrated cutoffs were set before inspecting the collected metrics and were not relaxed to force a label. Descriptive signals remain visible when the combined rule fails.

The result is one known probe, one source-annotated probe-like case and three unknown cases. **Unknown does not mean confirmed buyer. Probe-like does not mean fraud or worthless usage.** Paid monitoring can itself be genuine use. All **0.055000 USDC remains in the payment totals**, regardless of labels.

These observations do not determine textokit’s organic customer count, profitability, service delivery or wallet ownership. RPC checks trust the selected Base node; they are not locally verified chain proofs. The practical improvement is narrower: settlement, behavior and sourced claims now have separate fields, so a receipt count need not silently become a customer count.

## Public settlement references

The following 24 public transactions correspond to the verified external ledger entries, grouped by payer. Amounts are USDC. The [live ledger](https://tienda.textokit.store/receipts.json) and the explorer links are primary sources; the fourteen-day behavioral figures above refer to the fixed observation window.

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

