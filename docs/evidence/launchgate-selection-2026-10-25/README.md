# Referential hotel-selection probe — completed evidence

25 October 2026. Local research material; no article, comment or GitHub write
was published by this work.

Read the [English report](../../growth/launchgate-selection-2026-10-25.en.md) or
[Russian report](../../growth/launchgate-selection-2026-10-25.ru.md) for the nine
condition cells, interpretation, limitations and AI provenance.

- **270/270 main selections correct**, including the untreated baseline;
  **0/90 injected target selections**; no incremental guard benefit established.
- Exact target names appear in **25/270** full answers, all comparisons or
  exclusions in internal AI review. Nine rating-wording issues are preserved;
  correct selected IDs do not establish perfect explanation facts.
- **0/90 Stop triggers**, no continuations. Historical AgentDojo **18/20** is
  unchanged; this is a separate six-fixture controlled probe.
- Linux/factory-vps, published `@aimarket/warden@0.21.0`, model requested/returned
  `deepseek-flash`, Docker runc guard without network. No real booking/payment.
- **73 offline tests** passed in the final freeze; **5,490 audit checks** passed.
- **282 total API attempts**: 9 preserved pilot + 3 repeat pilot + 270 main.
  Both pilots excluded. No hidden local retry/replacement; combined ceiling 372.

## Evidence layout

- `protocol.md`, `fixtures.json`, `experiment.py`, `analyze.py`,
  `guard_probe.mjs`, `host_relay.py` and their tests describe the frozen study.
- `linux-run/` preserves the original input archive and nine-call pilot. Its
  driver was replaced before main after a crash/resume accounting audit; the
  old bytes/results were not overwritten. There was no main run in that freeze.
- `linux-run-02/input-manifest.json` identifies the final eleven input files.
  `collection-01` holds tests, `collection-02` adds the three-call pilot,
  `collection-03` adds main answers, and **`collection-04` is the complete final
  copy**, adding the offline audit and selection export. Earlier copies remain
  as provenance, not additional model samples.
- [Final analysis](linux-run-02/collection-04/out/main/analysis.json),
  [full main answers/hooks](linux-run-02/collection-04/out/main/runs.jsonl),
  [audit](linux-run-02/collection-04/out/main/audit.json),
  [verification](linux-run-02/collection-04/verification.json).
- `audit_results.py` is a separate post-run offline audit, not a change to the
  frozen score. It ran on Linux; its SHA is recorded in `audit.json`.
- Qualitative reviews: [none](qualitative-none.md), [note](qualitative-note.md),
  [note_stop](qualitative-note-stop.md). Reviewers knew the conditions; these are
  internal AI interpretations, not blinded independent human adjudication.
- Cleanup receipts: [original pilot](linux-run/cleanup.json),
  [final study](linux-run-02/cleanup.json). Both owned temporary Linux roots were
  removed only after source/output hash verification. Existing services, API key
  files and Docker images were not modified or removed.

## Reproduction scope

The orchestrator exposes separate local-freeze, offline-test, paid pilot, paid
main, collection and cleanup stages. A fresh study requires a new state
directory. Do not reuse a previous ledger with a reset budget, overwrite failed
answers, or silently retry an uncertain paid attempt. Main calls require the
Linux tests and instrumentation pilot to pass. A rerun makes new paid model
calls; reading and scoring retained evidence does not.

The exact published archive used by the helper is the existing owned artifact
at `docs/evidence/auten-launcher-2026-10-25/artifacts/warden-0.21.0.tgz` in the
workspace, with SHA recorded in the protocol/manifests. No credential is included.
