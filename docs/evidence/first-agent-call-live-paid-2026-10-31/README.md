# Live MCP and A2A channel audit — 31 October 2026

[Русский](README.ru.md)

The live Hub was exercised at `https://modelmarket.dev`, using the local Python SDK and `aimarket-hub/examples/first-agent-call.py`. Three real **0.001 USDC** Base-mainnet payments succeeded: one initial A2A test, one A2A test after the fix, and one MCP test. Each provider receipt passes independent Ed25519 verification, while a modified price and the Hub's different key are rejected. The transaction's Transfer and AuthorizationUsed events match the buyer, seller, amount and invoice nonce.

The first paid A2A response exposed a real defect: the Task completed with a signed receipt but a null result. The fix was deployed; subsequent live A2A and MCP calls delivered weather data and valid provider receipts, using **granted service credits**, not new on-chain payments. A fresh on-chain purchase after the fix and a separate on-chain MCP purchase subsequently passed after the user explicitly authorized two additional 0.001-USDC transfers with a combined $0.02 fee-inclusive cap. Automatic approval review had rejected a second transfer before that explicit authorization; it was not bypassed. Each payment has its own journal and invoice nonce.

## Real payment and cost

- Transaction: [0xf60ed00b…70ce3d70](https://basescan.org/tx/0xf60ed00ba4a4887b2a8367b5ff610b5b7dcf55fdc5b266fcf4f8fb2e70ce3d70).
- Buyer: `0x097e3F339D0b023605e12A6B81E2d6Cb7571475a`.
- Seller of record: `0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a`.
- Payment: **0.001 USDC**; network fee: **0.000000501902005655 ETH**.
- At the recorded Chainlink price, total cost was approximately **$0.00212273**. Token and ETH amounts are transaction facts; USD conversion is approximate.
- This is an operator-authorized ecosystem integration test with an operator-provided buyer wallet. It is not independent customer traction.

## Final paid checks after the fix

- **A2A:** [0x478637aa…af036de9](https://basescan.org/tx/0x478637aabfeb2a2ab0a0627cd706a6d75862e894d478488cc34db15baf036de9). The actual example exited 0, delivered `om-wx-01` weather, and verified the provider receipt. Repeating the same CLI command performed only reads, without SendMessage or another payment. Evidence: `a2a-fixed/checks.json`, `a2a-fixed/example.stdout.txt`.
- **MCP:** [0x6d1082db…652ce342](https://basescan.org/tx/0x6d1082db9b7fe841b5700a88c27c52e6e310077bc6a9eb5f811da391652ce342). Weather and the provider receipt were delivered; resubmitting the same settled payment was rejected. Evidence: `mcp-paid/checks.json`, `mcp-paid/paid-delivery.json`.
- Each of the three payments independently passes the 10 signature/chain checks. `audit-summary.json` records the totals. **Total service: 0.003 USDC; total with network fees: approximately $0.00637264.** The two additional tests total approximately $0.00424991, within the explicitly authorized $0.02 limit.

## Defects fixed

1. Hub A2A completion read only `result`, dropping oracle-core's `output`. It now preserves that output and retains explicit `result` precedence, including an explicit null.
2. SDK x402 and input-resume follow-ups chose the signer from a waiting Task that had no source metadata. They now use the completed answer, consistently with GetTask. This SDK source fix is local; no package release was published.
3. The example accepted a valid receipt with no weather result. It now returns exit `4`, and supports reading or continuing the same Task with an already settled transaction.
4. The deployment script chose port 8080 / host 9460 instead of the Hub's healthcheck port 9083, and failed to reproduce a multiword entrypoint. It also made `/shared/deposit-claims` read-only. The script now preserves effective process arguments, probes the matching published application port and keeps the claims registry writable. Named volumes remain named volumes.

The first rollout was interrupted and rolled back. The corrected rollout is recorded in `deployment-fixed.txt`. The final image is `modelmarket-hub:a2a-output-20261031`, derived from the exact live image with only the A2A module replaced. The original container is kept as `modelmarket-hub-prev`. `runtime-preservation.json` checks effective arguments, environment, mounts, write modes, ports, networks and health. Container entrypoint/Cmd representation changes, but their concatenated process argv is identical.

## Verification matrix

| Check | Evidence | Result |
|---|---|---|
| Original example on live Hub | `example-execution.json`, `example-task.json` | Exposed null-result false success before fix |
| Real USDC transfer and invoice nonce | `chain-transaction-receipt.json`, `payment-journal.json` | Verified |
| Independent receipt, tamper and wrong-key checks | `independent-verification.json`, `verify_receipt.py` | 10 checks passed |
| Original paid Task with fixed SDK | `original-paid-task-reverified.json` | Receipt verified; historical stored result remains null |
| Corrected example after deployment | `postfix-credit-example-execution.json`, `postfix-credit-example-task.json` | Exit 0, weather delivered, receipt verified; granted credit |
| MCP initialize, tools, search, invalid arguments and price cap | `live-initial-checks.json`, `mcp-*.json` | Passed |
| MCP credit delivery and receipt | `mcp-credit-delivery.json`, `live-replay-and-credit-checks.json` | Passed; exactly 0.001 service credit |
| A2A same-message replay | `a2a-credit-idempotent-replay.json`, account snapshots | Same Task; no second debit |
| Original x402 follow-up replay | `a2a-original-paid-idempotent-replay.json` | Same Task, verified receipt; no new transfer |
| Invalid A2A version / limit and invalid MCP key | `live-initial-checks.json`, `mcp-invalid-key.json` | Rejected |
| Hub channel tests | `hub-tests.txt` | 244 passed |
| SDK full suite | `agent-tests.txt` | 140 passed, 1 skipped |
| MCP full suite | `mcp-tests.txt` | 102 passed, 1 skipped |
| Example and oracle regressions | `regression-tests.txt` | 9 passed; 6 already included in Hub total |
| Deployment-script regressions | `deployment-script-tests.txt` | 2 passed |

Unique automated tests: **491 passed, 2 skipped**. Missing MCP, AWR and pytest-httpx test dependencies were supplied in a temporary environment; initial environment-only failures were resolved without changing production dependencies. The live audit consumed the available anonymous trials to reach the payment challenge. Three authenticated service calls spent 0.003 of the account's signup grant; those are kept separate from the three 0.001-USDC payments.

## Evidence scope and reproduction

`verify_receipt.py` runs offline with the workspace SDK and eth-utils. The other scripts describe the recorded live operations and require private state under `/private/tmp`; payment submission is guarded by an exclusive journal. Do not rerun them as if they were offline tests. Keys, payment secrets and raw unbroadcast signed transactions are excluded from this directory. MCP text blocks containing nested invoice JSON are redacted as well.

The execution host clock was approximately 58 minutes ahead of agreeing Hub, Coinbase and Base RPC timestamps. `clock-observations.json` records this. The one payment used agreeing HTTPS network time plus monotonic elapsed time, while retaining both RPC block/feed freshness checks. Host-recorded `at_utc` fields retain their original host timestamps; network timestamps and chain blocks establish event time. No system clock was changed.

Receipt verification here means **Ed25519** against the provider's HTTPS-advertised key captured before payment. It does not independently verify the attached ML-DSA signature. The v1 receipt signs accounting metadata, not the weather payload or transaction hash. The live Hub's Task associates payment and receipt; chain logs independently establish the actual USDC transfer. GAIA returned Open-Meteo relay data, not an independently verified physical sensor measurement. The signed device attestation was not independently pinned in this audit.
