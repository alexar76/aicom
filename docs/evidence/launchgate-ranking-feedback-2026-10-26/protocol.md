# Post-hoc feedback repair; no new model experiment

26 October 2026. Separate from the completed frozen prospective-fixture run. That run found five unresolved live trajectories, all ending in `not-optimal`; the original feedback carried a status code but no selected-vs-best numeric comparison. One originated from an omitted-list seed and then developed a ranking error.

Add bounded, fixed-template counterevidence for ranking (safe selected reference, field handle, actual value, direction, eligible best value and one attaining reference) and omitted eligible sets (expected/received counts and at most eight known missing references). Never repeat raw source IDs/field names, text or URLs. The schema, eligibility/ranking decisions, one-output boundary, two-correction limit and refusal behavior stay unchanged. No automatic provider retry or new API calls.

Build/typecheck, new gate regressions, affected 24 WARDEN suites and existing 28-scenario red-team gate run on Linux factory-vps. Only dev-dependency installation has network. Replay all retained 156 trajectories and every saved proposal through the changed build: decisions/codes and final frames must remain identical; deny feedback gains fact witnesses. This is offline replay, not evidence that a model now repairs unresolved cases.

Verify all input/output hashes and collect before deleting temporary server data. Preserve original model-study protocol, payload, outcomes, failed paths and collection amendment. Synchronize only this separately validated post-hoc build locally. No GitHub/npm publication, no version bump or model rerun. Existing local 0.22.0 remains unpublished.
