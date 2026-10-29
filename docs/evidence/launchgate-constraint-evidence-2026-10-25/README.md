# Constraint evidence and disclosure continuity — local follow-up

Started 25 October; continued 26 October 2026. This is a new runtime candidate following the saved-pair reason audit, not a new model result.

## Changes

- Optional host-owned `warden-answer-check/1` contract, exact answer/session/turn binding, bounded numeric/boolean constraint checking of the selected and explicitly eligible items.
- Fixed counterevidence templates with positional IDs and finite values; no source-controlled names or attack quotes in warnings.
- Guard-owned same-turn continuation receipt preserves instruction-disclosure notice in hook output without a second recheck. New turns reset it; audit stays observational.
- Closed-schema repository-only extraction for the synthetic hotel probe, separate from the generic runtime and semantic gold labels.
- New regressions cover stale contracts, missing facts, false eligibility, admissible ties, coercion, changed snapshots and disclosure loss.

## Current validation status

**Linux execution passed on 26 October 2026, 06:40–06:44 Moscow.** Automatic approval review initially rejected transfer to `factory-vps`: earlier permission covered a different payload and `admin-vps`. The user explicitly authorized this current 170-file, 499,574-byte payload; all eight execution stages passed, all 276 collected output hashes were verified and the temporary remote root was removed.

`payload-review/input-manifest.json` lists the prepared source/test/synthetic payload. `payload-review/inputs.tar.gz` is local only. No keys, server configuration or dependency trees are included. The manifest is regenerated as source review changes.

`run_linux.py` freezes inputs, verifies the transfer, installs npm dev dependencies with network, then builds/typechecks/tests/replays with Docker networking disabled. It collects hashed outputs and removes the temporary remote root even on failure. Failed attempts must be retained under distinct `run-NN` directories.

Passed: build/typecheck, **743 WARDEN tests in 21 affected files** (29 new, zero skipped), the existing **28-scenario deterministic gate**, **24 Python adapter/reason-audit tests**, claim extraction and replay of **12 unchanged saved initial/final pairs** through the actual compiled hooks. The gate is not 28 demonstrated prevented model attacks.

Replay: four known false eligibility lists detected; the same four contradictions remain in the unchanged historical final answers. Guard disclosure notices are emitted after continuation in 12/12 cases, including all three prior model-text disclosure losses. Second continuations: zero. New model calls and changed model outcomes: zero.

See [execution.json](run-01/execution.json), [replay.json](run-01/out/replay.json), [cases.json](run-01/out/cases.json), [vitest.json](run-01/out/vitest.json), [input manifest](run-01/input-manifest.json), [output manifest](run-01/manifest.json), [Linux build synchronization](build-sync.json), [Russian report](../../growth/launchgate-constraint-evidence-2026-10-26.ru.md), and [five-language product report](https://github.com/alexar76/warden/blob/main/docs/flow-guard-constraint-evidence.md).

## Interpretation boundaries

The prior reason audit marked four contradictory eligible lists and three model-text disclosure losses. The new adapter extracts claims without reading the gold labels at execution time; replay compares detections with that audit. Its grammar was developed after seeing the answers: this is post-hoc development-case replay, not independent semantic validation. Passing replay demonstrates hook behavior only, not model correction, model-prose disclosure preservation, native-client display or independent holdout performance.

The host adapter supplies rules from the actual user/policy and normalizes units/currencies. A lying record source remains a lying source. Unsupported prose is unexamined, not semantically validated. An optional contract is not automatically populated by native Stop integrations.

No model API calls, GitHub writes, npm publication, public blog/article changes or comment posting are part of this execution. All new changes remain local. Development and review used AI assistance.
