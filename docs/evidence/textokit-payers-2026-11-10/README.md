# textokit payers, second window (2026-10-27 to 2026-11-10)

Read-only evidence for the joint payer study planned with YuTao (PromoMaterials/outreach/x402-payers-2026-11-10).
The first window, 2026-10-11 to 10-25, is `../textokit-payers-2026-10-25/`.

## Files

- `receipts.json`: textokit's public ledger, https://tienda.textokit.store/receipts.json.
  - `generatedAt` is 2026-11-10T06:29:44.567Z (server time; this Mac's clock ran ~58 min ahead).
  - 270 sales; 214 external, from 18 payers. On 2026-10-25 it had 24 external sales from 5 payers.
- `collect.log`: the first collection, for all 18 external payers. It stopped on the 2,000-request budget after the
  RPC split the window into 2,363 ranges, 394 of them unavailable. It wrote no chain file.
- `receipts-four-wallets.json`: the sales of the four wallets from the first window that were `unknown` or
  `probe-like` (0x7722…, 0xa1d1…, 0xc9c7…, 0xec2a…): 34 sales.
- `chain-four-wallets.json`: `python -m histor.payer_collect` (aimarket-histor 0.7.0 from PyPI) over that subset.
  - RPC https://base.gateway.tenderly.co, `--days 14 --max-requests 4000`.
  - Blocks 53,147,009–55,512,942, 2026-10-27T06:42:45Z to 11-10T06:42:44Z (block times).
  - Complete: 2,366 ranges and 2,432 reads, all successful, 3,937 USDC transfer logs. Log: `collect-four-wallets.log`.
- `payers-four-wallets.json`: `histor payer-audit` over those two files, with no annotations.
  - 34 of 34 settlements verified.
  - All four labels are `unknown`, because the first window's source annotation for 0xec2a is not repeated here.

## What the window shows

| Wallet | Transfers | Recipients | One-off recipients | Transfers ≤ 0.01 USDC | First window, recipients |
|---|---:|---:|---:|---:|---:|
| 0x7722… | 153 | 88 | 90.9% | 88.2% | 1,010 |
| 0xa1d1… | 2,022 | 1,969 | 98.0% | 76.3% | 1,632 |
| 0xc9c7… | 1,518 | 542 | 61.6% | 84.3% | 730 |
| 0xec2a… | 244 | 19 | 21.1% | 86.1% | 648 |

Overlap of the three wallets named in alexar76/aimarket-hub#23, `python3 overlap.py chain-four-wallets.json`:

| Recipients | Count |
|---|---:|
| Distinct | 2,030 |
| Paid by at least two | 506 |
| Paid by all three | 63 |

In the first window the same figures were 1,848, 1,088 and 436. The pattern holds, but its size moves with each
wallet's activity: 0x7722 nearly stopped, while 0xa1d1 reached more addresses than before.

Limits:
- Recipients are USDC addresses, not verified x402 services.
- Chain reads trust one RPC.
- Intent is unknown.
