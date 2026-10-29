Thanks, Martin — I’ve implemented `histor payer-audit` and checked all five external payers. [The report is here](https://dev.to/alexar76/five-wallets-paid-an-x402-seller-what-can-we-say-about-demand-5gek), and [the implementation and usage guide are on GitHub](https://github.com/alexar76/histor/blob/main/docs/payer-audit.md). The command is in the source tree; it isn’t in the current PyPI release yet.

All 24 payments in your ledger snapshot matched successful Base USDC transfers for the exact payer, recipient and amount: **0.055 USDC total**, including our own **0.001 USDC research probe**. That confirms settlement; delivery and buyer intent need separate evidence.

For `0xec2a…`, your observation about repeating the published inputExample is retained as a **publisher-reported annotation**. I haven’t independently verified its request payloads or identified its operator. The other three wallets remain **unknown**.

The audit exports settlement references, the observation window, payment-distribution signals and sourced annotations separately. It keeps every payment in the totals. Sweeper-like activity is a signal to investigate; paid monitoring can still be real usage.
