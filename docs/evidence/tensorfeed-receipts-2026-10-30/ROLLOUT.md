# Receipt binding rollout, 2026-10-30

The owner asked to fix the defects the TensorFeed comparison found, verify, redeploy, and make our receipts no worse than theirs.

## What changed (aimarket-hub)

- `aimarket_hub/receipt_binding.py` (new). Every delivered invoke answer carries a `receipt_binding`, signed by the hub that answered: request `input` digest, the answer's `result`/`output` digest, the buyer's `X-Client-Nonce` (or `X-Agent-Nonce`), and the receipt's nonce and signer key. A malformed nonce gets 400 before any work. The nonce is echoed in `X-Client-Nonce-Echo`. Spec §7.3.9, vector `aimarket-protocol/test-vectors/receipt-binding-signed.json` (deterministic, `generate_binding.py`).
- `hub_routes/invoke.py`: nonce check at entry; `_bind_receipt` after `finish()`, so the digest covers the answer exactly as sent.
- `hub_routes/verification.py`: `POST /receipts/verify` checks a peer's receipt against the key pinned for that active peer (never a key from the request), reports `signer`, and checks a `receipt_binding` (signature, hub, receipt, input, output, nonce). Receipt limit stays at 128 KiB, the whole request at 256 KiB.
- `api.py` passes `db` to the verification routes; `api_models.py` adds the optional request fields.
- `mcp_gateway.py` keeps `receipt_binding` in compact MCP answers.
- Provenance plugin (`receipt.py`, `plugin.py`): the signed subject says what `outputDigest` covers (`outputDigestOf`: `result` local, `output` routed). A routed call commits to the provider's receipt as `gatewayReceiptDigest`, and one serialization rule applies across all three digests. Before this, a routed credential digested the whole answer minus `provenance_receipt`, a rule nobody could know, which broke whenever more was added to the answer.
- Docs: `aimarket-hub/docs/receipts.{md,ru,es,fr,zh}.md`, README rows; spec §7.3.9.

## Tests

- New `tests/test_receipt_binding.py`: 12 tests. Every binding field is load-bearing, nonce format, local and routed answers, digests recomputed by the buyer, peer receipt verified by pinned key, unpinned key refused, a peer cannot sign a binding in another hub's name.
- Worktree suite (main + change): 3725 passed. The 4 failures were then resolved: 2 in `test_api.py::TestReceiptVerificationEndpoint` were caused by this change (exact-dict expectation; the receipt size limit), and both were fixed. 2 in `test_mcp_stdio.py` pass alone and depend on test order.
- **The deployed code is not main.** Prod runs the pre-split `invoke.py` monolith in two variants: V1 on UNI, lab, hunt, attested and Independent; V2 on apex. The change was ported onto each live file by anchored replacements (`port_patch.py` in the session kit; each anchor must match exactly once). A copy of the live UNI package with the ported files passed `test_receipt_binding`, `test_federated_invoke`, `test_mcp_stranger_path` and `TestReceiptVerificationEndpoint` (145 tests); the apex copy passed the same set plus `test_mcp_stranger_path` (186). Full main suite on the live V1 copy, before and after: 150 shared failures (test/live drift). The only differences are the 2 since-fixed `TestReceiptVerificationEndpoint` cases and `test_federated_success_runs_final_receipt_hook…`, which fails before (it now expects the new hook context) and passes after.

## Rollout (overlay images FROM the running `:dn2-20261030`, 8 files; kit `/root/rb-20261030` on each host)

| Hub | Live at (UTC) | Image | Rollback |
|---|---|---|---|
| UNI (uni.modelmarket.dev) | 06:31 | `modelmarket-hub-uni:rb-20261030` | container `modelmarket-hub-uni-security-prev-1793341920044248056`; DB `/app/data/hub-backup-pre-3160-20261030T063158Z.db` |
| lab (hub.modelmarket.dev) | 06:33 | `modelmarket-hub:rb-20261030` | `modelmarket-hub-security-prev-1793342034470279982`; `/app/data/hub-backup-pre-3160-20261030T063353Z.db` |
| hunt | 06:34 | `modelmarket-hub:rb-20261030` | `signal-hunt-hub-1-security-prev-1793342040642820878`; `/root/hub-backups/signal-hunt-hub-1-pre-3160-20261030T063359Z.dump` |
| attested | 06:35 | `attested-memory-hub:rb-20261030` (no provenance plugin there) | `attested-memory-hub-hub-1-security-prev-1793342117716184463`; `/root/hub-backups/attested-memory-hub-hub-1-pre-3160-20261030T063516Z.dump` |
| Independent | ~06:36 | venv `hub-3.16.0-rpc`, 6 files | copy `/root/rb-20261030/backup-venv/*` back, delete `aimarket_hub/receipt_binding.py`, `systemctl restart independentai-hub` |
| apex (modelmarket.dev) | 06:37 | `modelmarket-hub:rb-20261030` | `modelmarket-hub-security-prev-1793342193350011647` + borrower `themis-security-prev-1793342193350011647`; `/app/data/hub-backup-pre-3160-20261030T063632Z.db` |

`rollout_container.py` snapshots are under `/root/security-rollbacks/<container>-<stamp>/inspect.json`. Health checks after the swap: all six return 200, THEMIS 200. No `receipt binding failed` and no traceback in any hub's log for the first 15 minutes.

**Compose trap (memory):** hunt and attested are compose services; a `docker compose up` there recreates from the compose image and would drop this overlay, as with every overlay before.

## Live verification (`after_fix_check.py`, `after-fix/report.json`)

Routed free call `logos.federation.summary@v1` with our own `X-Client-Nonce` on apex, lab, hunt, attested and Independent. Every check is true on every hub: nonce echoed, binding signed by the hub's published key, nonce inside the signature, input and output digests recomputed, receipt named, the provider's (LOGOS) receipt verified by the hub against its pinned key, binding verified by the hub, and, where the provenance plugin runs (apex, lab, hunt), `outputDigestOf: output` with `outputDigest`, `gatewayReceiptDigest` and `inputDigest` all recomputed. UNI lists no free routed capability; there it was checked that a malformed nonce is refused with `client_nonce_invalid` (new code live). The apex baseline before the rollout is in `before-fix/` (no binding, no echo, peer receipt not verifiable, `outputDigest` not recomputable from `output`).

Not on Gitea or GitHub; worktree branch `claude/federation-hub-deployers-search-8b9411`, uncommitted at the time of writing.
