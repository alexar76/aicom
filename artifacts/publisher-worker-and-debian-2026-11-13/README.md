# ModelMarket payout worker and Debian updates

The payout wallet received exactly 1 Base USDC from the established operator treasury. The pre-existing ten atomic units brought the resulting balance to 1.00001 USDC. The worker reused the remaining verified credit from the previous canary to accrue one new publisher share. The same signed request was submitted twice and reserved a single withdrawal. [Funding receipt](funding.json) · [Accrual](accrual.json) · [Reservation](reservation.json)

The production systemd timer picked up `pwd_cddb98bea2fe4d1da2f0fddf2b769ec5` in 30 seconds and broadcast 10 atomic units of canonical USDC. The timer's service journal shows the exact withdrawal ID and transaction hash. Base finalized the transfer in block 56,758,477. The Hub set `paid` automatically and recorded one reservation and one paid entry. The wallet then held exactly 1 USDC. [Worker journal evidence](worker-broadcast.json) · [Finalized chain receipt](chain-finalized.json) · [Hub paid entry](hub-auto-paid.json) · [Final balance](final-balance.json)

The Debian update targets `apt` and `libapt-pkg7.0` 3.0.4 for CVE-2026-109518, and `zlib1g` `1:1.3.dfsg+really1.3.1-1+deb13u1` for CVE-2026-27171, CVE-2026-76844 and CVE-2026-85091. The `.deb` hashes and lengths match the package index authenticated by two Debian archive signatures. [Package provenance](security/debian-package-provenance.json) · [DSA-6607-1](https://security-tracker.debian.org/tracker/DSA-6607-1) · [DSA-6613-1](https://security-tracker.debian.org/tracker/DSA-6613-1)

ModelMarket apex switched to `c62951ec599a` at 04:15 UTC after the canary was `paid`. The image changes the three Debian packages and preserves the Hub source and 76 Python distributions. Both images opened copies of the two production ledgers without new migrations. The switch backed up both ledgers and restored the payout timer. Hub and THEMIS passed health checks. The updated Hub returned the same `paid` record, and the timer completed another successful run. [Tracker verification](security/candidate-debian-verification.json) · [Rollout](debian-rollout.log) · [Live image and package versions](post-deploy.log) · [Post-deploy timer](post-deploy-worker.json)

## Repeat on the patched image

The repeat canary used existing backed buyer credit and the existing payout-wallet balance. The same request reserved one withdrawal, and the scheduled worker on image `c62951ec599a` broadcast 10 atomic units after 65 seconds. The systemd invocation ID binds the withdrawal ID and transaction hash to the same worker run. [Accrual](patched-accrual.json) · [Reservation](patched-reservation.json) · [Worker journal](patched-worker-broadcast.json)

The Hub recorded `paid` 22 minutes and 34 seconds after broadcast, with one reservation and one paid ledger entry for `pwd_86535455c02e4e8c9b82ed2cd8553f60`. Public Base RPC verified a single 10-unit USDC transfer in canonical block 56,850,358 and a finalized head of 56,852,306. The payout wallet had 0.99999 USDC after settlement and its nonce advanced once. [Finalized chain receipt](patched-chain-rpc-finalized.json) · [Hub paid entry](patched-hub-auto-paid.json) · [Final balance](patched-final-balance.json)

## Catalogue comparison

The public manifest contains 286 callable offers, five local and 281 federated. Its callable IDs and prices match the reconstructed November 11–13 production snapshots. The observed x402 catalogue grew from 21 to 36 priced routes on November 11. It added four PriorSeal routes and eleven OracleInsight routes. [Dated comparison](catalogue-comparison.json)

CoinMarketCap, Tavily and Laso are absent from the public manifest and observed seller list. The ARGUS and ARGUS UNI production images also lack their local adapters. The Hub observer in the patched production image has SHA-256 `b1104ce8131d696eee3e4f836bd7442a6c01c35fcd3ccae1000ce691476ca79f`, matching the file before the explicit GET probe added in `d6a77ce9f`. [Unpaid provider preflight](../../docs/evidence/x402-integration-preflight-2026-11-12/live-unpaid.json)
