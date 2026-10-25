# textokit: evidence report for five external payers

Disclosure: we maintain HISTOR and AIMarket. This report and the implementation were prepared with AI assistance. Counts, transfer checks and labels below are produced by deterministic code; no model inferred wallet identities. Our own research payment is included and explicitly identified.

## Snapshot and result

The [seller ledger](https://tienda.textokit.store/receipts.json), retrieved at **2026-10-25T05:16:44.230432+00:00**, reports **80 settled sales**, including **56 own-wallet sales** and **24 external sales from five payers**, worth **0.055000 USDC**. All **24/24** external entries match successful Base transaction receipts containing an official USDC Transfer from the stated payer to the seller for the exact stated amount. This checks settlement, not delivery of the service.

The chain scan covers **2026-10-11T05:23:11+00:00 to 2026-10-25T05:23:11+00:00**, blocks **52453422–53058222**. All **605** consecutive log ranges succeeded; **23,254** raw Transfer events were returned for these five senders. Two zero-value events are excluded from behavioural metrics. Collection finished at 2026-10-25T05:27:36.498130+00:00. The head was fixed twelve blocks behind the initial node head, and its hash remained stable.

## Five payers

| Payer | textokit sales | USDC | Outgoing transfers / recipients in window | Recipients paid once | Transfers ≤0.01 USDC | Label |
|---|---:|---:|---:|---:|---:|---|
| [`0x097e3f339d0b023605e12a6b81e2d6cb7571475a`](https://basescan.org/address/0x097e3f339d0b023605e12a6b81e2d6cb7571475a) | 1 | 0.001000 | 5 / 4 | 3 (75.0%) | 1 (20.0%) | `known-probe` |
| [`0x7722dfae6bbed2fd02dc07455c2f5bf14be25e4a`](https://basescan.org/address/0x7722dfae6bbed2fd02dc07455c2f5bf14be25e4a) | 1 | 0.001000 | 1,262 / 1,010 | 909 (90.0%) | 1,051 (83.3%) | `unknown` |
| [`0xa1d1c0cf717402ff3651aa4873ccf96410b01978`](https://basescan.org/address/0xa1d1c0cf717402ff3651aa4873ccf96410b01978) | 1 | 0.001000 | 1,896 / 1,632 | 1,416 (86.8%) | 1,449 (76.4%) | `unknown` |
| [`0xc9c7b38c0942914fc8ea12063bc92dcd3b581670`](https://basescan.org/address/0xc9c7b38c0942914fc8ea12063bc92dcd3b581670) | 1 | 0.001000 | 1,979 / 730 | 442 (60.5%) | 1,518 (76.7%) | `unknown` |
| [`0xec2abd3eda89bed90124736e317e847d5fb6d034`](https://basescan.org/address/0xec2abd3eda89bed90124736e317e847d5fb6d034) | 20 | 0.051000 | 18,110 / 648 | 217 (33.5%) | 16,320 (90.1%) | `probe-like` |

1. **0x097e…475a — our known research probe.** One 0.001 USDC `x402-ping` purchase on 20 October. Its [transaction](https://basescan.org/tx/0x62c01526c5beb13cad96634ec80e837e576df496905f1bac8019c6ffa3e358c3) is the exact purchase in our saved delivery-survey run. This label applies to that purchase, not to all future use of the wallet.
2. **0xec2a…d034 — source-reported example use; probe-like indication.** Twenty purchases between 20 and 24 October, covering 17 services; four are `normativa-ar`. [Martin reports](https://dev.to/alexar76/we-tried-to-buy-one-call-from-100-x402-sellers-most-delivered-almost-nobody-is-buying-2498#comment-3ioef) that this payer sends the published `normativa-ar` inputExample. We associate the statement with the four ledger rows by service and time; their payloads are not public, and exact per-transaction input matches were not independently verified. This is not a confirmed monitor identity. Without the sourced annotation the strict automatic label is `unknown`.
3. **0x7722…5e4a — broad small-payment activity, intent unknown.** 1,010 recipients and 1,262 positive outgoing transfers. 90.0% of recipients were paid once; 83.3% of transfers were at most 0.01 USDC. These are signs worth reviewing for a sweep, but the current strict label rule does not pass its 90% small-transfer requirement.
4. **0xA1d1…1978 — broad small-payment activity, intent unknown.** 1,632 recipients and 1,896 transfers. 86.8% of recipients were paid once; 76.4% of transfers were at most 0.01 USDC. The strict rule does not pass. Our earlier public “more than a thousand” recipient description is supported; “nearly all” should be replaced by these exact fractions.
5. **0xc9c7…1670 — also broad activity, intent unknown.** 730 recipients and 1,979 transfers, with more repeat-recipient activity than the previous two wallets. One 0.001 USDC `cuit-ar` sale at textokit does not establish either a real workflow or monitoring. It is not silently counted as an organic customer.

## Implemented function

The local, unreleased `histor payer-audit` command reads public receipts, optional bounded chain evidence and transaction-scoped source annotations. It exports JSON and Markdown with input hashes, policy, observation window, payer metrics, evidence sources, settlement references and coverage limits. It needs no production database or wallet keys. The collector permits only five read RPC methods and never sends transactions or paid service requests.

The explicit, uncalibrated broad-pattern rule requires at least 50 transfers, 50 recipients, 90% singleton recipients and 90% small transfers. These initial cutoffs were set before inspecting the collected chain metrics; they were not relaxed to force these wallets into a category. Descriptive signals remain visible below the combined cutoff. The labels are one known probe, one source-annotated probe-like case and three unknown cases. **Unknown does not mean confirmed buyer, and probe-like does not mean worthless or fraudulent use.** Automated monitoring can itself be genuine paid use.

All 0.055 USDC remains in the payment totals. The report does not establish how many organic customers textokit has, whether anyone is profitable, or whether a service delivered the purchased result. A USDC recipient address is not necessarily a seller or an x402 endpoint. Wallet identities and publisher ownership flags are not independently authenticated. RPC checks trust the selected Base node, not a locally verified chain proof.

## Reproduce and inspect

- [Command, input formats, exact policy and exit codes](https://github.com/alexar76/histor/blob/main/docs/payer-audit.md).
- [Machine-readable five-payer report](../evidence/textokit-payers-2026-10-25/payers.json).
- [Full generated report with all 24 settlement references](../evidence/textokit-payers-2026-10-25/payers.md).
- [Captured seller ledger](../evidence/textokit-payers-2026-10-25/receipts.json), [chain observations](../evidence/textokit-payers-2026-10-25/chain.json), [source annotations](../evidence/textokit-payers-2026-10-25/annotations.json), [source metadata](../evidence/textokit-payers-2026-10-25/sources.json).
- [Our recorded 20 October purchase](../../scripts/delivery-survey/results/2026-10-20.json).

This report and the implementation are local drafts. No reply, publication, deployment or new payment was sent by this task.
