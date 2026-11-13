# ModelMarket publisher custody rollout

The apex Hub switched to image `7c41749d850c` at 20:15 UTC on November 12, 2026. The offline build used the exact live parent `0d2aeefc891c` and twenty custody files. Both the new image and the previous image started on copies of the migrated Hub and channel ledgers. The switch took fresh backups of both ledgers and verified Hub and THEMIS health. The previous containers are available for rollback. [Rollout log](rollout.log) · [Public health](public-health.json)

## Receipt guarantee

The production canary redeemed the configured minimum top-up of 0.01 Base USDC into a zero-grant test buyer. Its 0.00002 USDC sale captured once under receipt `rcpt_ee6d172db08ebb1f727bd2315bac59cd`. The identical invoke replay returned the same receipt. The publisher ledger showed one payout of 0.00001 and one backing marker for that same amount. Reapplying the payout was a no-op and a conflicting amount was refused. The temporary capability was removed. [Production ledger checks](accrual.json) · [Top-up receipt](https://basescan.org/tx/0x46929e16ed8c343ba875b426bb1ff81105354b67aa0664f6de7e27a9ede24c23)

A separate test on the exact live image used disposable SQLite ledgers and disabled Docker networking. Process termination before crediting and after crediting before acknowledgement both converged to one debit and one publisher credit. The live escrow-only channel policy stayed in force. [Channel recovery evidence](channel-outbox-crash-smoke.json)

## Base payout

The repeated signed request returned the same withdrawal ID. The operator worker sent 10 atomic units of canonical Base USDC, or 0.00001 USDC. The Base mainnet RPC verified the exact Transfer in finalized block 56,622,348. The Hub's background reconciler set `paid` and wrote one requested and one paid entry. Two later reconciliations returned the same record and hash. [Reservation](reservation.json) · [Finalized Base receipt](chain-finalized.json) · [Production reconciliation](withdrawal-final.json) · [Payout transaction](https://basescan.org/tx/0x8e9a69e4bb87f1ee99f41f4e78106a7cda28656376ff12fa7326de52b531d68a)

The production signer was funded with 20 atomic units and 0.000008 ETH. The key stays in an owner-only file on the operator host and is mounted only in the worker. After the test the wallet held 10 atomic units. The queue worker completed a live run with an empty queue and its timer is enabled. Hub and THEMIS were running with zero restarts at the final check. [Balances and network fees](base-canary-costs.json) · [Worker status](worker-status.log) · [Final public health](final-health.json)

## Security

The candidate and previous image inventories match for all 76 Python distributions and 133 Debian packages. Vulnetix and OSV found no matching affected Python versions. CISA KEV had no matches in the correlated advisories. Debian still lists inherited notices, including four with available updates for `apt` and `zlib`. [Security report](security/README.md)
