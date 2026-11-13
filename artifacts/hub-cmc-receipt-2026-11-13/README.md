# ModelMarket CoinMarketCap receipt rollout

The production ModelMarket apex moved from `3f372add6d13` to `618ea971f7b6`. The offline build changed only `x402_bridge.py` and kept the 76 Python distributions and 129 Debian package entries. Both images started on disposable copies of the two ledgers and added zero migrations. Hub and THEMIS passed local health checks after the switch. Public health, the 36 observed routes, the bridge, and the registration and withdrawal authentication checks passed. [Build and smoke](prepare.log) · [Rollout](rollout.log) · [Public checks](public-postdeploy.json)

The fixed CoinMarketCap GET accepts the vendor's `txHash` receipt on a successful HTTP 200 once one Base RPC node confirms the exact signed nonce and adjacent canonical USDC transfer. A conflicting network, hash, payer, or amount fails verification. The focused suite passed 153 tests, including the exact registered route, mismatches, and refusal to issue a second authorization while a receipt is unresolved. The installed image verified the existing 10,000-atom transaction in canonical block 56863462 and rejected a different nonce. The finalized head at the time was 56861681. This rollout reused that transaction as read-only evidence. [Tests](tests.log) · [Installed chain verification](live-cmc-chain.log)

The 10-atom publisher payout remained `paid` with one reservation and one paid posting. The payout timer resumed and its next worker run exited successfully. There were zero pending withdrawals. The Hub has no publisher signer key and its bridge wallet reported zero USDC. CoinMarketCap and Tavily remain unlisted. [Payout and timer](post-switch-custody.log) · [Public checks](public-postdeploy.json)

## Rollback

Run `bash /root/cmc-receipt-20261113/deploy.sh rollback` on `factory-vps`. The operator kit waits for the active payout worker, backs up both current ledgers, switches to the previous image, checks Hub and THEMIS, and resumes the timer. Run `python3 kit/stage.py <empty-directory>` to reproduce staging from the reviewed local source. The staging script verifies the deployed `d6a77ce9f` preimage and records checksums for the preimage and new source.
