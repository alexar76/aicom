# Lottery agent: final two-host gVisor acceptance

The two commits after the already accepted `6f86974` add legacy-contract entry compatibility, confirmed-revert handling, bounded entry attempts and cancelled-round refunds. Their implementation is frozen in `cf000311dbdbc0dc8d080d5054c4b9cccdcfd3a8`. This acceptance adds five portable CI regressions and corrects the rollout's restart claim; it makes no production implementation or deployment change.

| Check | Attested | Blip |
| --- | --- | --- |
| Project tests: 15 door + 58 existing signing/network guard + five actual-main loop cases | 78 passed | 78 passed |
| Archived predecessor receipt-status-zero negative control | 1 passed | 1 passed |
| Changed Python files, Ruff E9,F63,F7,F82 | 3 clean | 3 clean |
| Historical isolated script, syntax only | pass | pass |
| Real synthetic legacy-Anvil control | pass | pass |
| First five changed source/report files, native Gitleaks | 0 findings / exit 0 | 0 findings / exit 0 |

The 79 assertions are counted once. Earlier smoke profiles and the initial incomplete support-source staging diagnostic are not added as extra coverage. The five positive loop cases live in [test_agent_loop.py](../../lottery/agent/tests/test_agent_loop.py); the historical negative is archived separately. Tests exercise actual transaction signing/recovery and receipt handling with fake transport, three failed attempts followed by new-round entry, one-shot claim/refund follow-up and no refund for a work seat.

The real integration uses only public standard Anvil accounts on a temporary chain inside the network-isolated gVisor namespace. Exact historical Solidity SHA256 `6866ae731c24e699facb1d4cf4efaecae837e1dfb76cfdd5db9a7f8d71d0d854` comes from Git, not a live image. With Anvil 1.3.1, solc 0.8.28 and OpenZeppelin 5.6.1, both hosts produced 18,663-byte runtime SHA256 `94fa4ce871bc93fcba32f00fb2dc49b0de228f9fa834a0d0064108f7b38d6acf`. This is not a claim of live deployed-bytecode identity.

The predecessor makes missing-getter calls but sends no purchase (nonce 0, paidBy 0). The current agent buys round 2 (nonce 1), refunds its cancelled tickets (nonce 2, paidBy 0; positive synthetic net refund), and enters round 3 in the same process (nonce 3). Production wallets, state, live chains and the original historical shell procedure were not used. That procedure reads a serving container's environment and remains syntax-checked historical evidence only.

The accepted source/test tree is `675bf9e766375f834b235118c05e5865670e3aef`. Native Git continuity accounts for **6,618 Python blobs / 6,290 eligible**, using the prior full baseline plus exact deltas and the unchanged 328 original exclusions; no complete full-repository rerun is claimed. All 627 required documentation inputs are identical to the accepted baseline, so the real-map docs-only result remains applicable without a rerun.

[Attested native report](attested/validation/final-report/REPORT.md) and [Blip native report](blip/validation/final-report/REPORT.md) contain the fixed-source witnesses, dependency constraints, native logs and cleanup records. Public reproduction harnesses are archived as text. No fixture wallet, env file, dependency tree, binary, state dump or production financial capture is exported.

The two shared report hashes are summary `e10df33b5f7dbba7fa5be20824bf90f3544679ee9077e55ecc4a1824ae803a82` and report `f4db84c8ef4f743fefac6e4c1ee82ec8a7a10faae7be7a1af7a45af1ad448214`. All test-owned containers and child processes were removed. No project workload ran on the local computer; the generated Lottery agent bytecode cache was removed. All 61 previously identified private originals remain local and excluded.

The agent's round/entry/follow-up tracking is RAM-only. Continuous-process behavior was tested; persistent restart or exactly-once recovery after an ambiguous RPC result is not established. The corrected rollout text states the restart limitation.

A final native scan covers the new CI source and this receipt packet before commit. Its exact Git tree, terminal result and retained host paths are recorded in the commit message; this avoids recursively modifying the already scanned packet to insert its own hash.
