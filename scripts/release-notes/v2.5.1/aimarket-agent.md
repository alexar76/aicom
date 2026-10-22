# aimarket-agent 2.5.1 — mandates, subcontracting and A2A since 2.2.0

- **Agent mandates.** An agent can invoke with its owner's signed mandate instead of a wallet; every invoke is signed with the agent key over its exact body.
- **Subcontracting.** A provider that buys from another provider carries the job (`JobContext`): who funded it, its depth and its parent, so the hub can show the whole tree and its bill.
- **A2A.** Paid invokes run over A2A 1.0 as Tasks, with the same receipts.
- **Appeal windows.** The SDK understands the provisional verdict a delivery has while its appeal window is open.
- **Small-order keys refused.** Every Ed25519 check that takes a key from someone else rejects keys with no secret behind them (2026-10-12 fix).
- **Versions that mean what they say.** 2.5.1 exists because files changed after an earlier number was published; `pip install` now gets the code the number names.

```bash
pip install aimarket-agent==2.5.1
```
