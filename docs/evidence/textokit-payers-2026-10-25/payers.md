# Payer evidence report

Seller: `0x6b5af9924f4cd35643c11a9fd1c983f77261a6e1` · Base USDC.
Ledger generated: 2026-10-25T05:16:45.484Z.

Seller-reported external: **5 wallets**, **24 sales**, **0.055000 USDC**.
RPC-verified external transfers: **24**, **0.055000 USDC**.

Chain window: 2026-10-11T05:23:11+00:00 — 2026-10-25T05:23:11+00:00; blocks 52453422–53058222; complete: **True**.

| Payer | Label | Sales | USDC | Verified settlements |
|---|---|---:|---:|---:|
| `0x097e3f339d0b023605e12a6b81e2d6cb7571475a` | known-probe | 1 | 0.001000 | 1/1 |
| `0x7722dfae6bbed2fd02dc07455c2f5bf14be25e4a` | unknown | 1 | 0.001000 | 1/1 |
| `0xa1d1c0cf717402ff3651aa4873ccf96410b01978` | unknown | 1 | 0.001000 | 1/1 |
| `0xc9c7b38c0942914fc8ea12063bc92dcd3b581670` | unknown | 1 | 0.001000 | 1/1 |
| `0xec2abd3eda89bed90124736e317e847d5fb6d034` | probe-like | 20 | 0.051000 | 20/20 |

## 0x097e3f339d0b023605e12a6b81e2d6cb7571475a

Label: **known-probe**; buyer intent: **unknown**.
Ledger observations: 2026-10-20T04:51:24.352Z — 2026-10-20T04:51:24.352Z.
Observed outgoing USDC transfers: 5; distinct recipients: 4; singleton recipients: 3; transfers ≤0.01 USDC: 1. Complete window: True.
Descriptive signals: majority-recipients-paid-once.
- annotation:known-probe (source-reported) ([source](https://dev.to/alexar76/we-tried-to-buy-one-call-from-100-x402-sellers-most-delivered-almost-nobody-is-buying-2498)): Our own research probe on 2026-10-20. Exact settlement is recorded in scripts/delivery-survey/results/2026-10-20.json; payer association also appears in the seller public ledger.

Settlement references:
- [0x62c01526c5beb13cad96634ec80e837e576df496905f1bac8019c6ffa3e358c3](https://basescan.org/tx/0x62c01526c5beb13cad96634ec80e837e576df496905f1bac8019c6ffa3e358c3) — 0.001000 USDC; verified

## 0x7722dfae6bbed2fd02dc07455c2f5bf14be25e4a

Label: **unknown**; buyer intent: **unknown**.
Ledger observations: 2026-10-23T22:13:32.660Z — 2026-10-23T22:13:32.660Z.
Observed outgoing USDC transfers: 1262; distinct recipients: 1010; singleton recipients: 909; transfers ≤0.01 USDC: 1051. Complete window: True.
Descriptive signals: broad-recipient-spread, majority-transfers-at-most-0.01-USDC, majority-recipients-paid-once.

Settlement references:
- [0x8d2ccd6a3e04a769ecc680f298999dd082a0a2eba936f00a96c0e4ec5902b934](https://basescan.org/tx/0x8d2ccd6a3e04a769ecc680f298999dd082a0a2eba936f00a96c0e4ec5902b934) — 0.001000 USDC; verified

## 0xa1d1c0cf717402ff3651aa4873ccf96410b01978

Label: **unknown**; buyer intent: **unknown**.
Ledger observations: 2026-10-21T21:18:17.136Z — 2026-10-21T21:18:17.136Z.
Observed outgoing USDC transfers: 1896; distinct recipients: 1632; singleton recipients: 1416; transfers ≤0.01 USDC: 1449. Complete window: True.
Descriptive signals: broad-recipient-spread, majority-transfers-at-most-0.01-USDC, majority-recipients-paid-once.

Settlement references:
- [0x58ddb2e77e574ddda75fd74df6f3dbf94e2795e22c36f8a01a506c544ff4ada3](https://basescan.org/tx/0x58ddb2e77e574ddda75fd74df6f3dbf94e2795e22c36f8a01a506c544ff4ada3) — 0.001000 USDC; verified

## 0xc9c7b38c0942914fc8ea12063bc92dcd3b581670

Label: **unknown**; buyer intent: **unknown**.
Ledger observations: 2026-10-20T15:31:14.134Z — 2026-10-20T15:31:14.134Z.
Observed outgoing USDC transfers: 1979; distinct recipients: 730; singleton recipients: 442; transfers ≤0.01 USDC: 1518. Complete window: True.
Descriptive signals: broad-recipient-spread, majority-transfers-at-most-0.01-USDC, majority-recipients-paid-once.

Settlement references:
- [0x3ca4f2791f4f851a574f4abd7cb949e1b05fb00dadeb77b83fb3d0e36a608fb2](https://basescan.org/tx/0x3ca4f2791f4f851a574f4abd7cb949e1b05fb00dadeb77b83fb3d0e36a608fb2) — 0.001000 USDC; verified

## 0xec2abd3eda89bed90124736e317e847d5fb6d034

Label: **probe-like**; buyer intent: **unknown**.
Ledger observations: 2026-10-20T07:06:48.303Z — 2026-10-24T14:01:45.472Z.
Observed outgoing USDC transfers: 18110; distinct recipients: 648; singleton recipients: 217; transfers ≤0.01 USDC: 16320. Complete window: True.
Descriptive signals: broad-recipient-spread, majority-transfers-at-most-0.01-USDC.
- annotation:example-input-match (source-reported) ([source](https://dev.to/alexar76/we-tried-to-buy-one-call-from-100-x402-sellers-most-delivered-almost-nobody-is-buying-2498#comment-3ioef)): Publisher reports that this payer sends the published normativa-ar inputExample. These four transaction references are associated by ledger service and time, not by public request payloads. Exact per-transaction payload matches were not independently verified. This is a source-reported indication, not a confirmed monitor identity.

Settlement references:
- [0x8c0acafc219977d53b7431c734b1d29b7ef6db90cab5091c7aabe4a0f69a2c0a](https://basescan.org/tx/0x8c0acafc219977d53b7431c734b1d29b7ef6db90cab5091c7aabe4a0f69a2c0a) — 0.005000 USDC; verified
- [0xef5f2a2c81b7f6021c73a966eceb453055481a333256a2475a8ac8f011183ffd](https://basescan.org/tx/0xef5f2a2c81b7f6021c73a966eceb453055481a333256a2475a8ac8f011183ffd) — 0.002000 USDC; verified
- [0xcc3231d1e3d39a27838c4e3fbb87db85fb61da5048c49690e5511e844fc83b7e](https://basescan.org/tx/0xcc3231d1e3d39a27838c4e3fbb87db85fb61da5048c49690e5511e844fc83b7e) — 0.005000 USDC; verified
- [0xa7662362f207a4d0059b32c1204f1171fa7ec7fae9b8567b9ef7cc6cd1f37885](https://basescan.org/tx/0xa7662362f207a4d0059b32c1204f1171fa7ec7fae9b8567b9ef7cc6cd1f37885) — 0.005000 USDC; verified
- [0xd197a66ab0eb069c0acfddfd280dcefe123ec576878d1a924f5407e8f87afda9](https://basescan.org/tx/0xd197a66ab0eb069c0acfddfd280dcefe123ec576878d1a924f5407e8f87afda9) — 0.003000 USDC; verified
- [0x68a7bb46a2839d40c1001e1bf1dab036abb849939203e7a4131183581158d8ce](https://basescan.org/tx/0x68a7bb46a2839d40c1001e1bf1dab036abb849939203e7a4131183581158d8ce) — 0.002000 USDC; verified
- [0x4f712436cfe5bb039f55d2a536a484b2847e5e29cb86edc97ec6c33552bd9c13](https://basescan.org/tx/0x4f712436cfe5bb039f55d2a536a484b2847e5e29cb86edc97ec6c33552bd9c13) — 0.002000 USDC; verified
- [0x9fe21127d045e4398ca6b9d6889241a15c861f7f08d812d7ef66e1846e8cfe04](https://basescan.org/tx/0x9fe21127d045e4398ca6b9d6889241a15c861f7f08d812d7ef66e1846e8cfe04) — 0.002000 USDC; verified
- [0x23207988c28a9bd13e4d2fcd3dffd4e1ae47594077802890ca57fafeb4215bb0](https://basescan.org/tx/0x23207988c28a9bd13e4d2fcd3dffd4e1ae47594077802890ca57fafeb4215bb0) — 0.001000 USDC; verified
- [0x0e65e22cea86dadeeb4bb1736f94bd8f28538011e8024c98eb4d4fc7d25d4121](https://basescan.org/tx/0x0e65e22cea86dadeeb4bb1736f94bd8f28538011e8024c98eb4d4fc7d25d4121) — 0.001000 USDC; verified
- [0x56eafab52aa8a3889b97ba4a013ea3f508cafa934c0acb7958bbd3ec43d78bb6](https://basescan.org/tx/0x56eafab52aa8a3889b97ba4a013ea3f508cafa934c0acb7958bbd3ec43d78bb6) — 0.001000 USDC; verified
- [0x55049b036d022dc9970490abbdf079d70bf15f8afdf35f65782472b8f115ef89](https://basescan.org/tx/0x55049b036d022dc9970490abbdf079d70bf15f8afdf35f65782472b8f115ef89) — 0.001000 USDC; verified
- [0x6322b987ed57b94367753a7cfdb4bb1b31bf9efaf183d2ccf0036a057c75959f](https://basescan.org/tx/0x6322b987ed57b94367753a7cfdb4bb1b31bf9efaf183d2ccf0036a057c75959f) — 0.005000 USDC; verified
- [0x415ec0e389ce17a9936de89a28b7ba0fc1717b2f50e756196e074851d712bd9b](https://basescan.org/tx/0x415ec0e389ce17a9936de89a28b7ba0fc1717b2f50e756196e074851d712bd9b) — 0.001000 USDC; verified
- [0x4feb47e132ac06e7b5081756cdfb8b6b5436fae1ab62701d04139982b74f0186](https://basescan.org/tx/0x4feb47e132ac06e7b5081756cdfb8b6b5436fae1ab62701d04139982b74f0186) — 0.001000 USDC; verified
- [0x9bb91375a64c6da4a5fc78e8df817fe86b51487a36c3c98a73a78513edd4d637](https://basescan.org/tx/0x9bb91375a64c6da4a5fc78e8df817fe86b51487a36c3c98a73a78513edd4d637) — 0.001000 USDC; verified
- [0x3bc01e29b53d187320b18bd1794526c85b8addc456fc0e8e7756fd17fd971ea6](https://basescan.org/tx/0x3bc01e29b53d187320b18bd1794526c85b8addc456fc0e8e7756fd17fd971ea6) — 0.001000 USDC; verified
- [0x068b1930266c6235ee31cbfa87690b8ef14c519bba4f1dafd0b36872b836fe95](https://basescan.org/tx/0x068b1930266c6235ee31cbfa87690b8ef14c519bba4f1dafd0b36872b836fe95) — 0.002000 USDC; verified
- [0x4700749eb35c98129e0abc6adb2f9ee66d76dc7bc8ba2e509341f858146d35d6](https://basescan.org/tx/0x4700749eb35c98129e0abc6adb2f9ee66d76dc7bc8ba2e509341f858146d35d6) — 0.005000 USDC; verified
- [0xf93149b946d87295924977c2d46f76f163b4d93354bc3fa7aa1f5c04e392736d](https://basescan.org/tx/0xf93149b946d87295924977c2d46f76f163b4d93354bc3fa7aa1f5c04e392736d) — 0.005000 USDC; verified

## Limits

- Seller ownership flags and annotations are source claims, not independently established identities.
- Labels describe these observations; they do not establish a wallet's permanent purpose.
- Recipients are USDC addresses, not verified sellers or x402 services.
- The pattern rule is an uncalibrated heuristic, not a probability or proof of intent.
- All amounts remain in totals regardless of label. Unknown is not evidence of no demand.
- RPC verification trusts the supplied Base node; it is not an independently verified chain proof.
