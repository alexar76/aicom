# Source instruction signals and Stop diagnostics

25 October 2026. Local WARDEN 0.22.0 candidate; no npm publication or public reply by this work.

The saved tie study did **not** supply an attack-specific warning. All 96 guarded
injected samples received only a generic outside-source note. The published
0.21.0 Stop requested no rechecks. This means that describing the study as a
model knowingly ignoring a detected instruction would overstate its evidence.

## Change

- Preserve existing signals and add bounded patterns for spoofed roles, claimed
  relayed preferences/prior decisions with nearby directives, concealed
  instructions, private rubrics and selected Russian directive forms.
- Record source signal kinds, scan limits and generic/specific/suppressed warning
  type. Stop records whether it had no signal, no literal overlap or overlap
  requesting a recheck. Logs explicitly leave semantic compliance unassessed.
- Include the first body sentence after a spoofed role header in instruction
  fingerprints; do not fingerprint all surrounding ordinary records.
- Keep the existing 12-character normalized overlap and host-marked continuation
  bound. No semantic hard stop, model-awareness detector or automatic prohibition
  of an admissible hotel was added.

English/Russian patterns are incomplete and can flag legitimate quotations. A
source signal is neither proof of an attack nor authority to execute an effect.
The five-language flow guide describes these contracts and limitations.

## Linux verification

All execution took place in an isolated Docker runc container on **admin-vps**.
The exact source snapshot contained 164 files, including own test sources,
synthetic saved answers and the public own 0.21.0 artifact. No keys or production
configuration were mounted. Lockfile dev-dependency installation used network
with lifecycle scripts disabled; build/tests/replays had no network. No model,
booking, seller or payment calls were made.

- Build and TypeScript typecheck passed.
- **711 tests in 20 test files passed**, including 54 in the new instruction
  suite: 16 additional synthetic instruction cases, 32 ordinary source texts and
  six extraction/diagnostic/audit/continuation/limit/user-source contracts.
  These fixtures were authored after the original six cases; they are not an
  independent holdout or an estimate of production false positives.
- The unchanged 28-case deterministic red-team gate passed: 26 effect-call
  attacks required refusal/review; two answer-only cases were noted/rechecked.
  This is not 28 independently prevented model attacks.
- Exact published 0.21.0 replay reproduced the saved warnings and Stop decisions
  on all **288 guarded rows**. Candidate replay used identical inputs, original
  policy, fresh isolated sessions and the original saved answers.

| Observation | Published 0.21.0 | Local candidate |
| --- | ---: | ---: |
| Instruction-specific warnings, injected note profile | 0/48 | 48/48 |
| Instruction-specific warnings, injected note+Stop profile | 0/48 | 48/48 |
| Instruction-specific warnings, all clean/benign guarded rows | 0/192 | 0/192 |
| Stop recheck requests on saved injected note+Stop answers | 0/48 | 12/48 |
| Stop recheck requests on saved clean/benign note+Stop answers | 0/96 | 0/96 |

All 12 new requests concern saved target selections: six in tie-2, one in tie-3,
five in tie-4. The other **36/48** injected note+Stop answers still do not request
a recheck, despite now having a source signal. This exposes the remaining
literal-overlap gap; it does not establish semantic safety for the other rows.

No candidate awareness words were found by the helper's limited English
surface-word screen in the 96 guarded injected answers, including all 89 target
selections. This is **not** a blinded semantic classification, nor proof that a
model did not notice a warning. It also does not show how a model would answer
after receiving the new instruction-specific warning.

The saved choices remain 44/48 and 45/48. A new recheck request is counterfactual:
no continuation was generated and no saved answer was corrected. A new controlled
model run would be required to estimate benefit or additional recheck costs.

## Numerical correction to the follow-up comment

The untreated increase was **20/48 = 41.7 percentage points**, not 20 points.
Clean-adjusted note+Stop attenuation was **8.3 points**, a point estimate with
fixture-cluster 95% interval **[−4.2,+20.8] points**, not an upper bound of eight.
The note-only contrast was 2.1 points [−16.7,+33.3]. Six purposive clusters and
coarse intervals do not prove a general upper bound or general effectiveness.
The directly observed high remaining target-selection rate still matters.

## Evidence

- [Frozen input manifest](../evidence/launchgate-warning-diagnostics-2026-10-25/input-manifest.json).
- [Execution and exact commands](../evidence/launchgate-warning-diagnostics-2026-10-25/execution.json).
- [711-test report](../evidence/launchgate-warning-diagnostics-2026-10-25/results/vitest.json).
- [Published replay](../evidence/launchgate-warning-diagnostics-2026-10-25/results/baseline-replay.json).
- [Candidate replay with per-answer tags](../evidence/launchgate-warning-diagnostics-2026-10-25/results/candidate-replay.json).
- [Verified build synchronization](../evidence/launchgate-warning-diagnostics-2026-10-25/local-build-sync.json).
- [Owned temporary directory removed](../evidence/launchgate-warning-diagnostics-2026-10-25/cleanup.json).

All 266 collected output hashes were verified before the owned temporary root
was removed. Input archive SHA-256:
`f7277cb18282c1a693cfbe6a4efbf9399e7476ae4fb9900f7e79cb50fb7882e4`.
Output archive SHA-256:
`779b1c808ab01772c96a4e8dec54b2540c1848035d5ee593ef6684bb7be72dfd`.
The Linux-generated dist/plugin files were synchronized only after all frozen
local project inputs were confirmed unchanged. No runtime tests ran on the Mac.

Research, implementation and interpretation used AI assistance. This is not
independent or blinded human adjudication. Historical study results remain intact.
